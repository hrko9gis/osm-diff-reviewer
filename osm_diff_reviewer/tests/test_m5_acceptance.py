"""M5 acceptance: from old and new versions of the reference data, additions, removals and
changes are extracted and matched against OSM; lines are matched too."""

import json
import sys
from pathlib import Path

import processing
import pytest
from qgis.core import QgsApplication

from osm_diff_reviewer.core import review
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.gui.review_model import ReviewFilterProxy, ReviewTableModel
from osm_diff_reviewer.processing.provider import OsmDiffReviewerProvider

sys.path.insert(0, str(Path(__file__).parent / "data"))
from make_m5_data import EXPECTED  # noqa: E402

M5 = Path(__file__).parent / "data" / "m5"
PROFILE = {"attribute_mappings": [{"reference_field": "名称", "osm_tag": "name", "method": "similarity"}]}


@pytest.fixture(scope="module")
def provider(qgis_app):
    registry = QgsApplication.processingRegistry()
    provider = OsmDiffReviewerProvider()
    registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


def _run(tmp_path, **extra):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
    params = {
        "OLD_REFERENCE": str(M5 / "reference_old.geojson"),
        "NEW_REFERENCE": str(M5 / "reference_new.geojson"),
        "REFERENCE_KEY": "id",
        "OSM": str(M5 / "osm.geojson"),
        "PROFILE": str(profile),
        "OUTPUT": "memory:changes",
        **extra,
    }
    return processing.run("osmdiffreviewer:version_diff", params)


def test_version_diff_algorithm_reports_changes_and_verdicts(provider, tmp_path):
    layer = _run(tmp_path)["OUTPUT"]
    actual = {f["ref_key"]: (f["change_kind"], f["verdict"]) for f in layer.getFeatures()}
    assert actual == EXPECTED


def test_version_diff_runs_are_reviewable_and_not_hidden(provider, tmp_path):
    workspace = tmp_path / "work.gpkg"
    result = _run(tmp_path, WORKSPACE=str(workspace), SOURCE_NAME="施設一覧")
    rows = WorkspaceStore.open(workspace).load_rows(result["RUN_ID"])
    assert {r.ref_key: (r.change_kind, r.verdict) for r in rows} == EXPECTED

    model = ReviewTableModel()
    model.set_rows(rows)
    proxy = ReviewFilterProxy()
    proxy.setSourceModel(model)
    # V2 (added, already in OSM) is classified "match" but belongs to the change set: it stays visible.
    assert proxy.rowCount() == len(EXPECTED)

    store = WorkspaceStore.open(workspace)
    store.save_review({r.ref_key: r for r in rows}["V4"], review.NEEDS_EDIT, "閉館済み")
    again = _run(tmp_path, WORKSPACE=str(workspace), SOURCE_NAME="施設一覧")
    assert {r.ref_key: r.status for r in store.load_rows(again["RUN_ID"])}["V4"] == review.NEEDS_EDIT


def test_key_field_is_required(provider, tmp_path):
    from qgis.core import QgsProcessingException

    with pytest.raises(QgsProcessingException):
        _run(tmp_path, REFERENCE_KEY="")


def test_match_algorithm_now_accepts_lines(provider, tmp_path):
    layer = processing.run(
        "osmdiffreviewer:match",
        {
            "REFERENCE": str(M5 / "reference_new.geojson"),
            "REFERENCE_KEY": "id",
            "OSM": str(M5 / "osm.geojson"),
            "OUTPUT": "memory:candidates",
        },
    )["OUTPUT"]
    classes = {f["ref_key"]: f["classification"] for f in layer.getFeatures()}
    assert classes["L1"] == "match" and classes["L2"] == "ambiguous"


def test_empty_osm_layer_is_allowed(provider, tmp_path):
    from qgis.core import QgsVectorLayer

    empty = QgsVectorLayer("Point?crs=EPSG:4326&field=osm_id:integer", "osm", "memory")
    layer = _run(tmp_path, OSM=empty)["OUTPUT"]
    verdicts = {f["ref_key"]: f["verdict"] for f in layer.getFeatures()}
    assert verdicts["V3"] == "not_in_osm" and verdicts["V4"] == "gone_from_osm"
