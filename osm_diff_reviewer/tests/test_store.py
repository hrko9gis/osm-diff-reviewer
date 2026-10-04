import pytest
from osgeo import ogr

from osm_diff_reviewer.core import review
from osm_diff_reviewer.core.review import ReviewKey
from osm_diff_reviewer.data.license_gate import (
    LICENSE_CONFIRMED,
    LICENSE_UNCONFIRMED,
    ReferenceSource,
)
from osm_diff_reviewer.data.store import CandidateRecord, StoreError, WorkspaceStore


def _record(ref_key="R1", osm_type="node", osm_id=1, osm_version=1, classification="attribute_diff", ref_hash="h1"):
    return CandidateRecord(
        ref_key=ref_key,
        osm_type=osm_type,
        osm_id=osm_id,
        osm_version=osm_version,
        classification=classification,
        distance_m=3.0,
        shape_score=0.9,
        attribute_score=0.2,
        total_score=0.55,
        alternatives="",
        attribute_details="[]",
        ref_hash=ref_hash,
        ref_attributes='{"名称": "北公民館"}',
        osm_tags='{"name": "北地区センター"}',
        point_wkt="POINT(139.7 35.68)",
        ref_wkt="POINT(139.7 35.68)",
        osm_wkt="POINT(139.70003 35.68)",
    )


@pytest.fixture()
def store(tmp_path, qgis_app):
    return WorkspaceStore.create(tmp_path / "work.gpkg")


def test_create_makes_all_tables(store):
    dataset = ogr.Open(str(store.path))
    names = {dataset.GetLayer(i).GetName() for i in range(dataset.GetLayerCount())}
    assert {"reference_sources", "runs", "candidates", "reviews", "mr_tasks"} <= names


def test_open_rejects_non_workspace(tmp_path, qgis_app):
    with pytest.raises(StoreError):
        WorkspaceStore.open(tmp_path / "missing.gpkg")


def test_reference_source_round_trip(store):
    source = ReferenceSource("施設一覧", "CC BY 4.0", "○○市", LICENSE_CONFIRMED, "https://example.org/license", "id", "/data/a.gpkg")
    store.save_reference_source(source)
    store.save_reference_source(source)  # upsert, not duplicate
    assert store.reference_source("施設一覧") == source
    assert [s.name for s in store.reference_sources()] == ["施設一覧"]
    assert store.reference_source("unknown") is None


def test_ensure_reference_source_defaults_to_unconfirmed_and_keeps_existing(store):
    created, _ = store.ensure_reference_source("src", key_field="id", source_uri="u")
    assert created.license_status == LICENSE_UNCONFIRMED
    store.save_reference_source(ReferenceSource("src", "CC0", "", LICENSE_CONFIRMED, "", "id", "u"))
    assert store.ensure_reference_source("src", key_field="id", source_uri="u")[0].license_status == LICENSE_CONFIRMED


def test_record_run_and_load_rows(store):
    run_id = store.record_run("src", '{"version": 1}', [_record(), _record("R2", None, None, None, "missing")])
    assert store.latest_run_id("src") == run_id
    rows = store.load_rows(run_id)
    assert [(r.ref_key, r.classification, r.status) for r in rows] == [
        ("R1", "attribute_diff", review.UNREVIEWED),
        ("R2", "missing", review.UNREVIEWED),
    ]
    assert rows[0].ref_attributes == {"名称": "北公民館"}
    assert rows[0].osm_tags == {"name": "北地区センター"}


def test_save_review_and_rerun_carry_over(store):
    first = store.record_run("src", "{}", [_record(), _record("R2", None, None, None, "missing")])
    rows = {r.ref_key: r for r in store.load_rows(first)}
    store.save_review(rows["R1"], review.NOT_NEEDED_OSM, "OSM の名称が正しい")
    store.save_review(rows["R2"], review.NOT_NEEDED_REFERENCE, "")

    second = store.record_run("src", "{}", [_record(osm_version=2), _record("R2", None, None, None, "missing")])
    rows = {r.ref_key: r for r in store.load_rows(second)}
    assert (rows["R1"].status, rows["R1"].needs_recheck, rows["R1"].note) == (review.NOT_NEEDED_OSM, True, "OSM の名称が正しい")
    assert (rows["R2"].status, rows["R2"].needs_recheck) == (review.NOT_NEEDED_REFERENCE, False)
    assert store.review(ReviewKey.of("src", "R2", None, None)).status == review.NOT_NEEDED_REFERENCE


def test_saving_again_clears_recheck(store):
    store.record_run("src", "{}", [_record()])
    store.save_review(store.load_rows(store.latest_run_id("src"))[0], review.NOT_NEEDED_OSM, "")
    run_id = store.record_run("src", "{}", [_record(ref_hash="h2")])
    (row,) = store.load_rows(run_id)
    assert row.needs_recheck is True
    store.save_review(row, review.NOT_NEEDED_OSM, "確認済み")
    (row,) = store.load_rows(run_id)
    assert (row.needs_recheck, row.ref_hash) == (False, "h2")


def test_reviews_are_separated_by_source(store):
    store.record_run("a", "{}", [_record()])
    store.save_review(store.load_rows(store.latest_run_id("a"))[0], review.ON_HOLD, "")
    run_b = store.record_run("b", "{}", [_record()])
    assert store.load_rows(run_b)[0].status == review.UNREVIEWED


def test_quotes_in_keys_are_safe(store):
    run_id = store.record_run("o'brien", "{}", [_record(ref_key="it's")])
    (row,) = store.load_rows(run_id)
    store.save_review(row, review.ON_HOLD, "")
    assert store.review(ReviewKey.of("o'brien", "it's", "node", 1)).status == review.ON_HOLD


def test_invalid_status_is_rejected(store):
    run_id = store.record_run("src", "{}", [_record()])
    with pytest.raises(StoreError):
        store.save_review(store.load_rows(run_id)[0], "bogus", "")


def test_latest_run_id_without_runs(store):
    assert store.latest_run_id("src") is None


def test_license_resets_when_source_identity_changes(store):
    source, reset = store.ensure_reference_source("src", key_field="id", source_uri="/data/a.gpkg")
    assert reset is False
    store.save_reference_source(ReferenceSource(**{**vars(source), "license_status": LICENSE_CONFIRMED}))
    same, reset = store.ensure_reference_source("src", key_field="id", source_uri="/data/a.gpkg")
    assert (same.license_status, reset) == (LICENSE_CONFIRMED, False)
    moved, reset = store.ensure_reference_source("src", key_field="id", source_uri="/data/other.gpkg")
    assert (moved.license_status, reset) == (LICENSE_UNCONFIRMED, True)
    assert store.reference_source("src").source_uri == "/data/other.gpkg"


def test_license_resets_when_key_field_changes(store):
    source, _ = store.ensure_reference_source("src", key_field="id", source_uri="u")
    store.save_reference_source(ReferenceSource(**{**vars(source), "license_status": LICENSE_CONFIRMED}))
    changed, reset = store.ensure_reference_source("src", key_field="code", source_uri="u")
    assert (changed.license_status, changed.key_field, reset) == (LICENSE_UNCONFIRMED, "code", True)


def test_unknown_license_status_in_file_reads_as_unconfirmed(store):
    store.ensure_reference_source("src", key_field=None, source_uri="u")
    dataset = ogr.Open(str(store.path), update=1)
    layer = dataset.GetLayerByName("reference_sources")
    feature = layer.GetNextFeature()
    feature.SetField("license_status", "maybe")
    layer.SetFeature(feature)
    dataset = None
    assert store.reference_source("src").license_status == LICENSE_UNCONFIRMED


def test_missing_run_error_is_not_double_wrapped(store):
    with pytest.raises(StoreError) as error:
        store.run(999)
    assert str(error.value) == "run 999 not found"


def test_store_works_without_dataset_close(store, monkeypatch):
    # GDAL < 3.8 has no DataSource.Close(); QGIS 3.40 may ship such a GDAL.
    from osm_diff_reviewer.data import store as store_module

    monkeypatch.setattr(store_module, "_HAS_CLOSE", False)
    store.record_run("src", "{}", [_record()])
    assert store.latest_run_id("src") is not None
