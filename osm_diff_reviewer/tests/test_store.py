from dataclasses import replace

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


def _confirm(store, name="src"):
    source = store.reference_source(name)
    store.record_license_decision(ReferenceSource(**{**vars(source), "license_status": LICENSE_CONFIRMED}))
    return store.reference_source(name)


def test_new_file_keeps_confirmation_but_asks_for_reconfirmation(store):
    from osm_diff_reviewer.data.store import LICENSE_NEEDS_RECONFIRMATION

    _, change = store.ensure_reference_source("src", key_field="id", source_uri="/data/v1.gpkg")
    assert change is None
    confirmed = _confirm(store)
    assert (confirmed.confirmed_uri, confirmed.version_changed) == ("/data/v1.gpkg", False)
    same, change = store.ensure_reference_source("src", key_field="id", source_uri="/data/v1.gpkg")
    assert (same.license_status, change) == (LICENSE_CONFIRMED, None)
    newer, change = store.ensure_reference_source("src", key_field="id", source_uri="/data/v2.gpkg")
    assert change == LICENSE_NEEDS_RECONFIRMATION
    assert (newer.license_status, newer.version_changed, newer.confirmed_uri) == (LICENSE_CONFIRMED, True, "/data/v1.gpkg")
    assert store.reference_source("src").source_uri == "/data/v2.gpkg"


def test_license_resets_when_key_field_changes(store):
    from osm_diff_reviewer.data.store import LICENSE_RESET

    store.ensure_reference_source("src", key_field="id", source_uri="u")
    _confirm(store)
    changed, change = store.ensure_reference_source("src", key_field="code", source_uri="u")
    assert (changed.license_status, changed.key_field, change) == (LICENSE_UNCONFIRMED, "code", LICENSE_RESET)


def test_legacy_confirmation_counts_for_the_file_it_was_recorded_with(store):
    from osm_diff_reviewer.data.store import LICENSE_NEEDS_RECONFIRMATION

    store.save_reference_source(ReferenceSource("src", "CC0", "", LICENSE_CONFIRMED, "", "id", "/data/v1.gpkg"))
    same, change = store.ensure_reference_source("src", key_field="id", source_uri="/data/v1.gpkg")
    assert (same.version_changed, change) == (False, None)
    _, change = store.ensure_reference_source("src", key_field="id", source_uri="/data/v2.gpkg")
    assert change == LICENSE_NEEDS_RECONFIRMATION


def test_reconfirmation_and_history(store):
    store.ensure_reference_source("src", key_field="id", source_uri="/data/v1.gpkg")
    _confirm(store)
    store.ensure_reference_source("src", key_field="id", source_uri="/data/v2.gpkg")
    reconfirmed = store.reconfirm_license("src")
    assert (reconfirmed.confirmed_uri, reconfirmed.version_changed) == ("/data/v2.gpkg", False)
    history = store.license_history("src")
    assert [(h.action, h.source_uri, h.license_status) for h in history] == [
        ("reconfirmed", "/data/v2.gpkg", LICENSE_CONFIRMED),
        ("recorded", "/data/v1.gpkg", LICENSE_CONFIRMED),
    ]
    assert history[0].decided_at >= history[1].decided_at
    assert store.license_history("other") == []


def test_reconfirmation_requires_a_confirmed_source(store):
    store.ensure_reference_source("src", key_field="id", source_uri="u")
    with pytest.raises(StoreError):
        store.reconfirm_license("src")


def test_recording_a_non_confirmed_decision_clears_the_confirmed_file(store):
    store.ensure_reference_source("src", key_field="id", source_uri="u")
    confirmed = _confirm(store)
    store.record_license_decision(ReferenceSource(**{**vars(confirmed), "license_status": "rejected"}))
    source = store.reference_source("src")
    assert (source.license_status, source.confirmed_uri) == ("rejected", "")
    assert [h.license_status for h in store.license_history("src")] == ["rejected", LICENSE_CONFIRMED]


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
    assert str(error.value) == "Run 999 not found"


def test_close_falls_back_to_flush_without_dataset_close():
    # GDAL < 3.8 has no DataSource.Close(); QGIS 3.40 may ship such a GDAL.
    from osm_diff_reviewer.data import store as store_module

    class OldDataset:
        flushed = False

        def FlushCache(self):  # noqa: N802 - GDAL API
            self.flushed = True

    dataset = OldDataset()
    store_module._close(dataset)
    assert dataset.flushed


def test_mr_task_records(store):
    first, second = ReviewKey.of("src", "R1", "node", 1), ReviewKey.of("src", "R2", None, None)
    store.record_challenge("src", 77, [first, second])
    assert store.challenge_ids("src") == [77]
    assert store.mr_task_states(77) == {first: (None, None), second: (None, None)}
    store.update_mr_task(77, first, 1001, 1)
    store.update_mr_task(77, ReviewKey.of("src", "R9", None, None), 1009, 0)  # task we did not record
    states = store.mr_task_states(77)
    assert states[first] == (1001, 1) and states[ReviewKey.of("src", "R9", None, None)] == (1009, 0)
    assert store.challenge_ids("other") == []


def test_concurrent_use_from_threads_is_safe(store):
    import threading

    run_id = store.record_run("src", "{}", [_record(f"R{i}") for i in range(20)])
    rows = store.load_rows(run_id)
    errors = []

    def work(part):
        try:
            for row in part:
                store.save_review(row, review.ON_HOLD, "")
                store.load_rows(run_id)
        except Exception as error:  # noqa: BLE001 - collected for the assertion
            errors.append(error)

    threads = [threading.Thread(target=work, args=(rows[i::4],)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert {r.status for r in store.load_rows(run_id)} == {review.ON_HOLD}


def test_read_only_workspace_can_still_be_opened(store):
    import os
    import stat

    run_id = store.record_run("src", "{}", [_record()])
    os.chmod(store.path, stat.S_IREAD)
    try:
        reopened = WorkspaceStore.open(store.path)
        assert [r.ref_key for r in reopened.load_rows(run_id)] == ["R1"]
    finally:
        os.chmod(store.path, stat.S_IREAD | stat.S_IWRITE)


def test_open_adds_columns_missing_from_older_workspaces(store):
    dataset = ogr.Open(str(store.path), update=1)
    layer = dataset.GetLayerByName("candidates")
    layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("verdict"))
    dataset = None
    WorkspaceStore.open(store.path)
    dataset = ogr.Open(str(store.path))
    assert dataset.GetLayerByName("candidates").GetLayerDefn().GetFieldIndex("verdict") >= 0


def test_stale_dialog_save_is_refused_when_the_file_changed_meanwhile(store):
    store.ensure_reference_source("src", key_field="id", source_uri="/data/A.gpkg")
    shown = _confirm(store)  # the dialog was opened with this state (file A)
    store.ensure_reference_source("src", key_field="id", source_uri="/data/B.gpkg")  # a run switches to B
    with pytest.raises(StoreError):
        store.record_license_decision(shown, expected_uri=shown.source_uri)
    current = store.reference_source("src")
    assert (current.source_uri, current.confirmed_uri, current.version_changed) == ("/data/B.gpkg", "/data/A.gpkg", True)


def test_decision_takes_file_and_key_field_from_the_store(store):
    store.ensure_reference_source("src", key_field="id", source_uri="/data/A.gpkg")
    stale = replace(store.reference_source("src"), source_uri="/old.gpkg", key_field="old", license_status=LICENSE_CONFIRMED)
    decided = store.record_license_decision(stale)
    assert (decided.source_uri, decided.key_field, decided.confirmed_uri) == ("/data/A.gpkg", "id", "/data/A.gpkg")


def test_reconfirmation_only_for_the_file_that_was_shown(store):
    store.ensure_reference_source("src", key_field="id", source_uri="/data/A.gpkg")
    _confirm(store)
    store.ensure_reference_source("src", key_field="id", source_uri="/data/B.gpkg")
    shown = store.reference_source("src")  # the prompt shows B
    store.ensure_reference_source("src", key_field="id", source_uri="/data/C.gpkg")  # a run switches to C
    with pytest.raises(StoreError):
        store.reconfirm_license("src", expected_uri=shown.source_uri)
    assert store.reference_source("src").version_changed is True


def test_history_of_older_workspace_without_the_table_is_empty(store):
    dataset = ogr.Open(str(store.path), update=1)
    dataset.DeleteLayer(dataset.GetLayerByName("license_history").GetName())
    dataset = None
    reader = WorkspaceStore(store.path)  # no upgrade (as with a read-only file)
    assert reader.license_history("src") == []


def test_legacy_confirmation_gets_a_date(store):
    store.save_reference_source(ReferenceSource("src", "CC0", "", LICENSE_CONFIRMED, "", "id", "/data/v1.gpkg"))
    source, _ = store.ensure_reference_source("src", key_field="id", source_uri="/data/v2.gpkg")
    assert source.confirmed_at.startswith("20")


def test_key_field_reset_is_logged(store):
    store.ensure_reference_source("src", key_field="id", source_uri="u")
    _confirm(store)
    store.ensure_reference_source("src", key_field="code", source_uri="u")
    assert [(h.action, h.license_status) for h in store.license_history("src")][0] == ("reset", "unconfirmed")
