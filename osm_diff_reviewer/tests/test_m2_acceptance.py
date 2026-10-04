"""M2 acceptance: after reviewing, a re-run hides "not needed" candidates and
flags only the pairs that changed as needing a recheck."""

import json

import processing
import pytest
from qgis.core import QgsApplication

from osm_diff_reviewer.core import review
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.processing.provider import OsmDiffReviewerProvider

ALGORITHM_ID = "osmdiffreviewer:match"
PROFILE = {"attribute_mappings": [{"reference_field": "名称", "osm_tag": "name", "method": "similarity"}]}


@pytest.fixture(scope="module")
def provider(qgis_app):
    registry = QgsApplication.processingRegistry()
    provider = OsmDiffReviewerProvider()
    registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


def _edit(path, out, change):
    data = json.loads(path.read_text(encoding="utf-8"))
    for feature in data["features"]:
        change(feature["properties"])
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return out


def _run(workspace, reference, osm, profile):
    return processing.run(
        ALGORITHM_ID,
        {
            "REFERENCE": str(reference),
            "REFERENCE_KEY": "ref_id",
            "OSM": str(osm),
            "PROFILE": str(profile),
            "WORKSPACE": str(workspace),
            "SOURCE_NAME": "試験施設一覧",
            "OUTPUT": "memory:candidates",
        },
    )


def test_rerun_hides_not_needed_and_flags_only_changed_pairs(provider, m1_dir, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
    workspace = tmp_path / "work.gpkg"
    WorkspaceStore.create(workspace)

    first = _run(workspace, m1_dir / "reference.geojson", m1_dir / "osm.geojson", profile)
    store = WorkspaceStore.open(workspace)
    assert first["RUN_ID"] == store.latest_run_id("試験施設一覧")
    rows = {r.ref_key: r for r in store.load_rows(first["RUN_ID"])}
    store.save_review(rows["R2"], review.NOT_NEEDED_REFERENCE, "実在しない")
    store.save_review(rows["R3"], review.NOT_NEEDED_OSM, "OSM の位置が正しい")
    store.save_review(rows["R4"], review.NOT_NEEDED_OSM, "改称済み")
    store.save_review(rows["R9"], review.ON_HOLD, "")

    # Between runs: an unmapped attribute of R3 changes, and node/4 (paired with R4) gets a new version.
    reference_v2 = _edit(
        m1_dir / "reference.geojson",
        tmp_path / "reference_v2.geojson",
        lambda p: p.update({"備考": "改修"}) if p["ref_id"] == "R3" else None,
    )
    osm_v2 = _edit(
        m1_dir / "osm.geojson",
        tmp_path / "osm_v2.geojson",
        lambda p: p.update({"osm_version": p["osm_version"] + 1}) if p["osm_id"] == 4 else None,
    )
    second = _run(workspace, reference_v2, osm_v2, profile)
    rows = store.load_rows(second["RUN_ID"])

    visible = {r.ref_key for r in rows if not review.is_hidden_by_default(r.status, r.needs_recheck)}
    rechecks = {r.ref_key for r in rows if r.needs_recheck}
    assert "R2" not in visible
    assert rechecks == {"R3", "R4"}
    assert {"R3", "R4", "R9"} <= visible
    assert {r.ref_key: r.status for r in rows}["R9"] == review.ON_HOLD


def test_workspace_records_reference_source_and_run(provider, m1_dir, tmp_path):
    workspace = tmp_path / "work.gpkg"
    WorkspaceStore.create(workspace)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
    _run(workspace, m1_dir / "reference.geojson", m1_dir / "osm.geojson", profile)
    store = WorkspaceStore.open(workspace)
    source = store.reference_source("試験施設一覧")
    assert source.key_field == "ref_id"
    assert source.license_status == "unconfirmed"
    run = store.run(store.latest_run_id("試験施設一覧"))
    assert json.loads(run.profile_json)["attribute_mappings"][0]["osm_tag"] == "name"


def test_rerun_without_key_field_reuses_recorded_key(provider, m1_dir, tmp_path):
    workspace = tmp_path / "work.gpkg"
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
    _run(workspace, m1_dir / "reference.geojson", m1_dir / "osm.geojson", profile)
    second = processing.run(
        ALGORITHM_ID,
        {
            "REFERENCE": str(m1_dir / "reference.geojson"),
            "OSM": str(m1_dir / "osm.geojson"),
            "PROFILE": str(profile),
            "WORKSPACE": str(workspace),
            "SOURCE_NAME": "試験施設一覧",
            "OUTPUT": "memory:candidates",
        },
    )
    keys = {r.ref_key for r in WorkspaceStore.open(workspace).load_rows(second["RUN_ID"])}
    assert keys == {f"R{i}" for i in range(1, 11)}
