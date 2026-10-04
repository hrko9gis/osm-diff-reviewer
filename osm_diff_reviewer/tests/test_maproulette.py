import json
from dataclasses import replace

import pytest

from osm_diff_reviewer.core import review
from osm_diff_reviewer.data.http import HttpResponse
from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED, LICENSE_UNCONFIRMED, LicenseGateError, ReferenceSource
from osm_diff_reviewer.export import maproulette as mr
from osm_diff_reviewer.export.maproulette import ChallengeSpec, MapRouletteClient, MapRouletteError
from osm_diff_reviewer.tests.fakes import UNREACHABLE, FakeHttp
from osm_diff_reviewer.tests.test_review_model import _row

BASE = "https://mr.example/api/v2"
SOURCE = ReferenceSource("src", "CC BY 4.0", "○○市", LICENSE_CONFIRMED, "", "id", "u")


def _rows():
    attribute = replace(_row("R4"), osm_id=4, ref_attributes={"名称": "北公民館"}, osm_tags={"name": "北地区センター"})
    missing = replace(_row("R2", "missing"), osm_type=None, osm_id=None, osm_version=None, osm_wkt="",
                      ref_attributes={"名称": "東公園"})
    osm_only = replace(_row(None, "osm_only"), osm_type="node", osm_id=11, ref_wkt="", osm_wkt="POINT(139.71 35.69)")
    return [attribute, missing, osm_only]


# ----- task identity and status mapping -------------------------------------------------


@pytest.mark.parametrize(
    ("ref_key", "osm_type", "osm_id", "key"),
    [("R4", "node", 4, "R4|node/4"), ("R2", None, None, "R2|"), (None, "node", 11, "|node/11"), ("a|b", "way", 1, "a|b|way/1")],
)
def test_task_key_round_trip(ref_key, osm_type, osm_id, key):
    row = replace(_row("x"), ref_key=ref_key, osm_type=osm_type, osm_id=osm_id)
    assert mr.task_key(row) == key
    assert mr.parse_task_key(key) == (ref_key or "", osm_type or "", osm_id or 0)


@pytest.mark.parametrize(
    ("status", "classification", "expected"),
    [
        (0, "missing", None),
        (1, "missing", review.DONE),
        (5, "attribute_diff", review.DONE),
        (2, "missing", review.NOT_NEEDED_REFERENCE),
        (2, "attribute_diff", review.NOT_NEEDED_OSM),
        (3, "missing", review.ON_HOLD),
        (6, "geometry_diff", review.ON_HOLD),
        (4, "missing", None),
        (None, "missing", None),
    ],
)
def test_review_status_for_task_status(status, classification, expected):
    assert mr.review_status_for(status, classification) == expected


# ----- GeoJSON ---------------------------------------------------------------------------


def test_feature_has_key_osm_id_classification_and_reference_attributes(qgis_app):
    feature = mr.task_feature(_rows()[0], "{classification}: {ref:名称} ⇔ {@id}")
    assert feature["id"] == "R4|node/4"
    assert feature["geometry"]["type"] == "Point"
    properties = feature["properties"]
    assert properties["@id"] == "node/4"
    assert properties["classification"] == "attribute_diff"
    assert properties["ref:名称"] == "北公民館"
    assert properties["task_description"] == "attribute_diff: 北公民館 ⇔ node/4"


def test_missing_and_osm_only_features(qgis_app):
    _, missing, osm_only = (mr.task_feature(r, "") for r in _rows())
    assert "@id" not in missing["properties"] and missing["geometry"]["type"] == "Point"
    assert osm_only["properties"]["@id"] == "node/11"
    assert osm_only["geometry"]["coordinates"] == [139.71, 35.69]


def test_template_leaves_unknown_placeholders_empty():
    assert mr.render_template("{ref_key}-{nope}-{{x}}", {"ref_key": "R1"}) == "R1--{{x}}"


def test_line_by_line_geojson_uses_record_separator(qgis_app):
    text = mr.line_by_line_geojson(_rows(), "")
    lines = text.rstrip("\n").split("\n")  # not splitlines(): it treats \x1e as a line break
    assert len(lines) == 3 and all(line.startswith("\x1e") for line in lines)
    assert json.loads(lines[0][1:])["id"] == "R4|node/4"


def test_write_geojson_respects_licence_gate(qgis_app, tmp_path):
    path = tmp_path / "tasks.geojson"
    unconfirmed = replace(SOURCE, license_status=LICENSE_UNCONFIRMED)
    with pytest.raises(LicenseGateError):
        mr.write_geojson(path, _rows(), "", unconfirmed, line_by_line=False)
    assert not path.exists()
    mr.write_geojson(path, _rows(), "", SOURCE, line_by_line=False)
    collection = json.loads(path.read_text(encoding="utf-8"))
    assert collection["type"] == "FeatureCollection" and len(collection["features"]) == 3


def test_write_geojson_refuses_empty_selection(tmp_path):
    with pytest.raises(MapRouletteError):
        mr.write_geojson(tmp_path / "x.geojson", [], "", SOURCE, line_by_line=False)


# ----- API client -----------------------------------------------------------------------


def _client(*responses):
    http = FakeHttp(*responses)
    return MapRouletteClient(http, BASE, "secret"), http


def test_requests_carry_api_key_header():
    client, http = _client(HttpResponse(200, b"[]"))
    client.managed_projects()
    method, url, body, headers = http.sent[0]
    assert (method, url) == ("GET", f"{BASE}/projects/managed?limit=50&page=0&onlyEnabled=false")
    assert headers["apiKey"] == "secret"


def test_managed_projects():
    client, _ = _client(HttpResponse(200, b'[{"id": 3, "displayName": "Tokyo", "name": "tokyo"}, {"id": 5, "name": "x"}]'))
    assert client.managed_projects() == [(3, "Tokyo"), (5, "x")]


def test_create_challenge_posts_disabled_challenge_with_tasks(qgis_app):
    client, http = _client(HttpResponse(201, b'{"id": 77, "name": "c"}'))
    spec = ChallengeSpec(project_id=3, name="公共施設", description="d", instruction="i", checkin_comment="#odr")
    challenge_id = client.create_challenge(spec, _rows(), "", SOURCE)
    assert challenge_id == 77
    method, url, body, headers = http.sent[0]
    assert (method, url) == ("POST", f"{BASE}/challenge")
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body)
    assert payload["parent"] == 3 and payload["name"] == "公共施設" and payload["enabled"] is False
    assert payload["checkinComment"] == "#odr" and payload["instruction"] == "i"
    assert [f["id"] for f in payload["localGeoJSON"]["features"]] == ["R4|node/4", "R2|", "|node/11"]


def test_create_challenge_is_blocked_by_licence_gate(qgis_app):
    client, http = _client()
    spec = ChallengeSpec(3, "c", "", "i", "")
    with pytest.raises(LicenseGateError):
        client.create_challenge(spec, _rows(), "", replace(SOURCE, license_status=LICENSE_UNCONFIRMED))
    assert http.sent == []


@pytest.mark.parametrize("spec", [ChallengeSpec(0, "c", "", "i", ""), ChallengeSpec(3, " ", "", "i", ""), ChallengeSpec(3, "c", "", "", "")])
def test_create_challenge_validates_input(qgis_app, spec):
    client, http = _client()
    with pytest.raises(MapRouletteError):
        client.create_challenge(spec, _rows(), "", SOURCE)
    assert http.sent == []


def test_task_statuses_are_paged():
    page0 = [{"id": i, "name": f"R{i}|", "status": 1} for i in range(mr.PAGE_SIZE)]
    page1 = [{"id": 9999, "name": "|node/11", "status": 2}]
    client, http = _client(HttpResponse(200, json.dumps(page0).encode()), HttpResponse(200, json.dumps(page1).encode()))
    statuses = client.task_statuses(77)
    assert len(statuses) == mr.PAGE_SIZE + 1
    assert statuses["|node/11"] == (9999, 2)
    assert [url for _, url, _, _ in http.sent] == [
        f"{BASE}/challenge/77/tasks?limit={mr.PAGE_SIZE}&page=0",
        f"{BASE}/challenge/77/tasks?limit={mr.PAGE_SIZE}&page=1",
    ]


@pytest.mark.parametrize(
    ("response", "message"),
    [(HttpResponse(401, b'{"status":"KO","message":"Not authorized"}'), "401"), (UNREACHABLE, "unreachable"), (HttpResponse(200, b"<html>"), "Unexpected")],
)
def test_errors_are_reported(response, message):
    client, _ = _client(response)
    with pytest.raises(MapRouletteError, match=message):
        client.managed_projects()


def test_api_key_is_not_in_error_messages():
    client, _ = _client(HttpResponse(500, b"boom secret"))
    with pytest.raises(MapRouletteError) as error:
        client.managed_projects()
    assert "apiKey" not in str(error.value)


@pytest.mark.parametrize(
    "url", ["", "ftp://mr.example/api/v2", "maproulette.org/api/v2", "http://maproulette.org/api/v2"]
)
def test_base_url_validation(url):
    with pytest.raises(MapRouletteError):
        MapRouletteClient(FakeHttp(), url, "k")


def test_missing_api_key_is_rejected():
    with pytest.raises(MapRouletteError):
        MapRouletteClient(FakeHttp(), BASE, "")


def test_plain_http_is_allowed_only_on_this_computer():
    assert MapRouletteClient(FakeHttp(), "http://127.0.0.1:9000/api/v2", "k").base_url == "http://127.0.0.1:9000/api/v2"


def test_managed_projects_are_paged():
    page0 = [{"id": i, "name": f"p{i}"} for i in range(mr.PROJECT_PAGE_SIZE)]
    page1 = [{"id": 999, "displayName": "last"}]
    client, http = _client(HttpResponse(200, json.dumps(page0).encode()), HttpResponse(200, json.dumps(page1).encode()))
    projects = client.managed_projects()
    assert len(projects) == mr.PROJECT_PAGE_SIZE + 1 and projects[-1] == (999, "last")
    assert "page=1" in http.sent[1][1]
