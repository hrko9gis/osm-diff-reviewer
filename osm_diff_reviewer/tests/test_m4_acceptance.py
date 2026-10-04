"""M4 acceptance: a challenge is created from the exported GeoJSON, task states flow back
into review states, and nothing is sent for a reference source whose licence is not confirmed."""

from dataclasses import replace

import pytest

from osm_diff_reviewer.core import review
from osm_diff_reviewer.core.review import ReviewKey
from osm_diff_reviewer.data.http import QgisHttpClient
from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED, LicenseGateError
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.export import maproulette as mr
from osm_diff_reviewer.export.maproulette import ChallengeSpec, MapRouletteClient
from osm_diff_reviewer.tests.fakes import FakeMapRoulette
from osm_diff_reviewer.tests.test_store import _record

SPEC = ChallengeSpec(project_id=3, name="試験チャレンジ", description="", instruction="確認してください", checkin_comment="#odr")


@pytest.fixture()
def store(qgis_app, tmp_path):
    store = WorkspaceStore.create(tmp_path / "work.gpkg")
    store.record_run(
        "src",
        "{}",
        [_record("R1"), _record("R2", None, None, None, "missing"), _record("R3", "way", 3, classification="geometry_diff")],
    )
    return store


def _confirm(store):
    source, _ = store.ensure_reference_source("src", None, "")
    store.save_reference_source(replace(source, license_status=LICENSE_CONFIRMED))
    return store.reference_source("src")


def _rows(store):
    return store.load_rows(store.latest_run_id("src"))


def test_challenge_created_and_task_states_flow_back(store):
    source = _confirm(store)
    with FakeMapRoulette() as server:
        client = MapRouletteClient(QgisHttpClient(), server.url, server.api_key)
        challenge_id = mr.create_challenge_for_rows(client, store, SPEC, _rows(store), "{ref_key}", source)
        assert challenge_id == 77
        assert [f["id"] for f in server.created[0]["localGeoJSON"]["features"]] == ["R1|node/1", "R2|", "R3|way/3"]

        # Mappers work on MapRoulette: R1 fixed, R2 "not an issue", R3 skipped.
        server.task_status.update({"R1|node/1": 1, "R2|": 2, "R3|way/3": 3})
        report = mr.sync_challenge(client, store, "src", challenge_id)

    assert (report.updated, report.not_in_run, report.unknown_tasks) == (3, 0, 0)
    statuses = {r.ref_key: r.status for r in _rows(store)}
    assert statuses == {"R1": review.DONE, "R2": review.NOT_NEEDED_REFERENCE, "R3": review.ON_HOLD}
    assert store.mr_task_states(77)[ReviewKey.of("src", "R1", "node", 1)] == (1000, 1)


def test_unchanged_task_status_does_not_override_local_decision(store):
    source = _confirm(store)
    with FakeMapRoulette() as server:
        client = MapRouletteClient(QgisHttpClient(), server.url, server.api_key)
        challenge_id = mr.create_challenge_for_rows(client, store, SPEC, _rows(store), "", source)
        server.task_status["R1|node/1"] = 3
        mr.sync_challenge(client, store, "src", challenge_id)
        row = {r.ref_key: r for r in _rows(store)}["R1"]
        store.save_review(row, review.NEEDS_EDIT, "local decision")  # decided again in QGIS
        report = mr.sync_challenge(client, store, "src", challenge_id)  # MapRoulette still says skipped
    assert report.updated == 0
    assert {r.ref_key: r.status for r in _rows(store)}["R1"] == review.NEEDS_EDIT


def test_unconfirmed_licence_sends_nothing(store):
    source = store.ensure_reference_source("src", None, "")[0]
    with FakeMapRoulette() as server:
        client = MapRouletteClient(QgisHttpClient(), server.url, server.api_key)
        with pytest.raises(LicenseGateError):
            mr.create_challenge_for_rows(client, store, SPEC, _rows(store), "", source)
    assert server.requests == []
    assert store.challenge_ids("src") == []


def test_wrong_api_key_is_reported(store):
    source = _confirm(store)
    with FakeMapRoulette() as server:
        client = MapRouletteClient(QgisHttpClient(), server.url, "wrong")
        with pytest.raises(mr.MapRouletteError, match="401"):
            mr.create_challenge_for_rows(client, store, SPEC, _rows(store), "", source)
    assert store.challenge_ids("src") == []


def test_status_change_is_kept_for_a_candidate_missing_from_the_latest_run(store):
    source = _confirm(store)
    with FakeMapRoulette() as server:
        client = MapRouletteClient(QgisHttpClient(), server.url, server.api_key)
        challenge_id = mr.create_challenge_for_rows(client, store, SPEC, _rows(store), "", source)
        # A narrower re-run no longer contains R1 while its task gets fixed on MapRoulette.
        store.record_run("src", "{}", [_record("R2", None, None, None, "missing")])
        server.task_status["R1|node/1"] = 1
        first = mr.sync_challenge(client, store, "src", challenge_id)
        # R1 is back in the next run: the pending "fixed" must now be applied.
        store.record_run("src", "{}", [_record("R1"), _record("R2", None, None, None, "missing")])
        second = mr.sync_challenge(client, store, "src", challenge_id)
    assert first.not_in_run == 1 and second.updated == 1
    assert {r.ref_key: r.status for r in _rows(store)}["R1"] == review.DONE
