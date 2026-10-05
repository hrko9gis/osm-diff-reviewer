from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

import pytest

from osm_diff_reviewer.core.profile import AttributeMapping
from osm_diff_reviewer.data.http import HttpResponse
from osm_diff_reviewer.data.license_gate import (
    LICENSE_CONFIRMED,
    LICENSE_UNCONFIRMED,
    ReferenceSource,
)
from osm_diff_reviewer.export import josm
from osm_diff_reviewer.export.josm import JosmClient, JosmError, JosmNotRunning
from osm_diff_reviewer.tests.fakes import JOSM_VERSION_BODY, UNREACHABLE, FakeHttp
from osm_diff_reviewer.tests.test_review_model import _row

NAME = (AttributeMapping("名称", "name", "similarity", 0.8),)


def _query(url):
    parts = urlsplit(url)
    return parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}


def _source(status=LICENSE_CONFIRMED, attribution="○○市オープンデータ"):
    return ReferenceSource("src", "CC BY 4.0", attribution, status, "https://example.org", "id", "u")


def _missing_row(**changes):
    row = replace(
        _row("R2", "missing"), osm_type=None, osm_id=None, osm_version=None, osm_wkt="",
        ref_attributes={"名称": "東公園 & 広場", "住所": "x"},
    )
    return replace(row, **changes)


# ----- URL and selection -------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8111", "http://localhost:8111/", "http://[::1]:8111", "https://127.0.0.1:8112"]
)
def test_loopback_urls_are_accepted(url):
    assert josm.validate_base_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:8111",
        "ftp://127.0.0.1:8111",
        "127.0.0.1:8111",
        "",
        "http://127.0.0.1.evil.com:8111",
        "http://127.0.0.1:8111/x",
        "http://127.0.0.1:8111/?y=1",
        "http://127.0.0.1:8111/#z",
    ],
)
def test_non_local_urls_are_rejected(url):
    with pytest.raises(JosmError):
        josm.validate_base_url(url)


def test_select_ids():
    assert josm.select_ids(_row("A")) == ["node1"]
    assert josm.select_ids(replace(_row("A", "ambiguous"), alternatives="node/62;way/7")) == ["node1", "node62", "way7"]
    assert josm.select_ids(_missing_row()) == []


def test_candidate_bbox_covers_both_sides_with_margin(qgis_app):
    row = replace(_row("A"), ref_wkt="POINT(139.7 35.68)", osm_wkt="POINT(139.701 35.68)")
    left, bottom, right, top = josm.candidate_bbox(row, margin_m=50)
    assert left < 139.7 < 139.701 < right
    assert bottom < 35.68 < top
    assert (top - 35.68) * 111_320 == pytest.approx(50, rel=0.05)


def test_oversized_bbox_is_refused(qgis_app):
    row = replace(_row("A"), ref_wkt="POLYGON((139 35, 140 35, 140 36, 139 36, 139 35))", osm_wkt="")
    with pytest.raises(JosmError):
        josm.candidate_bbox(row, margin_m=50)


def test_load_and_zoom_url():
    url = josm.load_and_zoom_url("http://127.0.0.1:8111", (139.6, 35.6, 139.8, 35.7), ["node1", "way7"], "出典 X")
    path, query = _query(url)
    assert path == "/load_and_zoom"
    assert query == {
        "left": "139.6", "right": "139.8", "top": "35.7", "bottom": "35.6",
        "select": "node1,way7", "changeset_source": "出典 X",
    }


def test_load_and_zoom_url_without_selection_or_source():
    _, query = _query(josm.load_and_zoom_url("http://127.0.0.1:8111", (1, 2, 3, 4), [], ""))
    assert "select" not in query and "changeset_source" not in query


# ----- reference layer ---------------------------------------------------------------


def test_reference_point_becomes_node_with_proposed_tags(qgis_app):
    xml = josm.reference_osm_xml(_missing_row(ref_wkt="POINT(139.7 35.68)"), NAME)
    root = ElementTree.fromstring(xml)
    (node,) = root.findall("node")
    assert (node.get("id"), node.get("lat"), node.get("lon")) == ("-1", "35.68", "139.7")
    assert {t.get("k"): t.get("v") for t in node.findall("tag")} == {"name": "東公園 & 広場"}
    assert root.get("upload") == "never"


def test_reference_polygon_becomes_closed_way(qgis_app):
    xml = josm.reference_osm_xml(_missing_row(ref_wkt="POLYGON((0 0, 1 0, 1 1, 0 0))"), NAME)
    root = ElementTree.fromstring(xml)
    (way,) = root.findall("way")
    refs = [nd.get("ref") for nd in way.findall("nd")]
    assert len(root.findall("node")) == 3 and refs[0] == refs[-1] and len(refs) == 4
    assert {t.get("k") for t in way.findall("tag")} == {"name"}


def test_reference_polygon_with_hole_becomes_multipolygon(qgis_app):
    wkt = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 3 2, 3 3, 2 2))"
    root = ElementTree.fromstring(josm.reference_osm_xml(_missing_row(ref_wkt=wkt), NAME))
    (relation,) = root.findall("relation")
    tags = {t.get("k"): t.get("v") for t in relation.findall("tag")}
    assert tags["type"] == "multipolygon" and tags["name"] == "東公園 & 広場"
    assert [m.get("role") for m in relation.findall("member")] == ["outer", "inner"]


def test_load_data_url_marks_layer_not_uploadable():
    path, query = _query(josm.load_data_url("http://127.0.0.1:8111", "<osm/>", "参照: R2"))
    assert path == "/load_data"
    assert query == {
        "data": "<osm/>", "new_layer": "true", "layer_name": "参照: R2", "upload_policy": "never",
        "layer_locked": "true",
    }


# ----- client --------------------------------------------------------------------------


def test_version_reports_protocol():
    http = FakeHttp(HttpResponse(200, b'{"protocolversion": {"major": 1, "minor": 13}}'))
    assert JosmClient(http, "http://127.0.0.1:8111").version() == (1, 13)


def test_unreachable_josm_raises_not_running():
    with pytest.raises(JosmNotRunning, match="Remote Control"):
        JosmClient(FakeHttp(UNREACHABLE), "http://127.0.0.1:8111").version()


def test_error_response_is_reported():
    http = FakeHttp(HttpResponse(200, JOSM_VERSION_BODY), HttpResponse(403, b"Permission denied: load data"))
    client = JosmClient(http, "http://127.0.0.1:8111")
    with pytest.raises(JosmError, match="Permission denied"):
        client.open_candidate(_row("A"), NAME, _source(), send_reference=False)


def test_open_existing_candidate_selects_object(qgis_app):
    http = FakeHttp()
    JosmClient(http, "http://127.0.0.1:8111").open_candidate(_row("A"), NAME, _source(), send_reference=False)
    paths = [_query(url) for _, url, _ in http.requests]
    assert [p for p, _ in paths] == ["/version", "/load_and_zoom"]
    assert paths[1][1]["select"] == "node1"
    assert paths[1][1]["changeset_source"] == "○○市オープンデータ"


def test_open_missing_candidate_with_reference_layer(qgis_app):
    http = FakeHttp()
    row = _missing_row(ref_wkt="POINT(139.7 35.68)")
    JosmClient(http, "http://127.0.0.1:8111").open_candidate(row, NAME, _source(), send_reference=True)
    paths = [_query(url) for _, url, _ in http.requests]
    assert [p for p, _ in paths] == ["/version", "/load_and_zoom", "/load_data"]
    assert "select" not in paths[1][1]
    assert "東公園" in paths[2][1]["data"]


def test_unconfirmed_licence_skips_only_the_reference_layer(qgis_app):
    http = FakeHttp()
    client = JosmClient(http, "http://127.0.0.1:8111")
    note = client.open_candidate(_missing_row(), NAME, _source(LICENSE_UNCONFIRMED), send_reference=True)
    assert [_query(url)[0] for _, url, _ in http.requests] == ["/version", "/load_and_zoom"]
    assert "licence" in note.lower()
    assert not any("東公園" in url for _, url, _ in http.requests)


def test_reference_is_sent_without_note_when_confirmed(qgis_app):
    http = FakeHttp()
    note = JosmClient(http, "http://127.0.0.1:8111").open_candidate(_missing_row(), NAME, _source(), True)
    assert note is None


def test_unconfirmed_source_sends_no_attribution(qgis_app):
    http = FakeHttp()
    JosmClient(http, "http://127.0.0.1:8111").open_candidate(_row("A"), NAME, _source(LICENSE_UNCONFIRMED), False)
    assert "changeset_source" not in _query(http.requests[1][1])[1]


def test_userinfo_is_dropped_from_base_url():
    assert josm.validate_base_url("http://evil.com@127.0.0.1:8111") == "http://127.0.0.1:8111"


def test_reference_line_becomes_open_way(qgis_app):
    root = ElementTree.fromstring(josm.reference_osm_xml(_missing_row(ref_wkt="LINESTRING(0 0, 1 0, 2 1)"), NAME))
    (way,) = root.findall("way")
    refs = [nd.get("ref") for nd in way.findall("nd")]
    assert len(refs) == 3 and refs[0] != refs[-1]
    assert {t.get("k"): t.get("v") for t in way.findall("tag")} == {"name": "東公園 & 広場"}


def test_reference_multiline_becomes_one_way_per_part(qgis_app):
    root = ElementTree.fromstring(josm.reference_osm_xml(_missing_row(ref_wkt="MULTILINESTRING((0 0, 1 0), (5 5, 6 5))"), NAME))
    assert len(root.findall("way")) == 2
