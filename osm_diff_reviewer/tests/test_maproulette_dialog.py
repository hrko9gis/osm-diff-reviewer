"""The MapRoulette dialog end to end: API key from the QGIS auth DB, QGIS networking, fake server."""

import json
import time
from dataclasses import replace

import pytest
from qgis.PyQt.QtCore import QCoreApplication

from osm_diff_reviewer import settings
from osm_diff_reviewer.core import review
from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.gui.maproulette_dialog import MapRouletteDialog
from osm_diff_reviewer.tests.conftest import store_auth_config
from osm_diff_reviewer.tests.fakes import FakeMapRoulette
from osm_diff_reviewer.tests.test_store import _record


def _wait(dialog, seconds=15):
    deadline = time.monotonic() + seconds
    while dialog.runner.running() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert not dialog.runner.running()


@pytest.fixture()
def server():
    with FakeMapRoulette() as fake:
        yield fake


@pytest.fixture()
def store(qgis_app, tmp_path):
    store = WorkspaceStore.create(tmp_path / "work.gpkg")
    store.record_run("src", "{}", [_record("R1"), _record("R2", None, None, None, "missing")])
    source, _ = store.ensure_reference_source("src", None, "")
    store.save_reference_source(replace(source, license_status=LICENSE_CONFIRMED, attribution="○○市"))
    return store


@pytest.fixture()
def configured(auth_manager, server):
    saved = settings.maproulette_url(), settings.maproulette_authcfg()
    settings.set_maproulette_url(server.url)
    settings.set_maproulette_authcfg(store_auth_config(auth_manager, "Basic", {"username": "u", "password": server.api_key}))
    yield
    settings.set_maproulette_url(saved[0])
    settings.set_maproulette_authcfg(saved[1])


def _dialog(store):
    rows = store.load_rows(store.latest_run_id("src"))
    return MapRouletteDialog(store, "src", rows)


def test_export_geojson(store, tmp_path, configured):
    dialog = _dialog(store)
    path = tmp_path / "tasks.geojson"
    dialog.export_geojson(str(path))
    assert len(json.loads(path.read_text(encoding="utf-8"))["features"]) == 2
    assert str(path) in dialog.message_label.text()


def test_unconfirmed_licence_disables_sending(store, tmp_path, configured, server):
    source = store.reference_source("src")
    store.save_reference_source(replace(source, license_status="unconfirmed"))
    dialog = _dialog(store)
    assert not dialog.export_button.isEnabled() and not dialog.create_button.isEnabled()
    assert "licence" in dialog.licence_label.text().lower()
    dialog.export_geojson(str(tmp_path / "x.geojson"))
    assert not (tmp_path / "x.geojson").exists()
    assert server.requests == []


def test_load_projects_create_and_sync(store, configured, server):
    dialog = _dialog(store)
    dialog.load_projects()
    _wait(dialog)
    assert dialog.project_combo.currentData() == 3

    dialog.name_edit.setText("試験チャレンジ")
    dialog.instruction_edit.setPlainText("確認してください")
    dialog.create_challenge()
    _wait(dialog)
    assert server.created[0]["enabled"] is False
    assert dialog.challenge_combo.currentData() == 77

    server.task_status.update({"R1|node/1": 1, "R2|": 2})
    dialog.sync()
    _wait(dialog)
    assert "2" in dialog.message_label.text()
    statuses = {r.ref_key: r.status for r in store.load_rows(store.latest_run_id("src"))}
    assert statuses == {"R1": review.DONE, "R2": review.NOT_NEEDED_REFERENCE}


def test_missing_api_key_is_explained(store, configured, server):
    settings.set_maproulette_authcfg("")
    dialog = _dialog(store)
    dialog.auth_select.setConfigId("")
    dialog.load_projects()
    _wait(dialog)
    assert "API key" in dialog.message_label.text()
    assert server.requests == []


def test_dialog_stays_open_while_a_request_runs(store, configured):
    import threading

    from osm_diff_reviewer.gui.background import BackgroundRunner  # noqa: F401 - documents the mechanism

    dialog = _dialog(store)
    release = threading.Event()
    dialog.runner.run("slow", lambda: release.wait(5) and "done")
    dialog.reject()
    assert dialog.runner.running()
    assert dialog.message_label.text() != ""
    release.set()
    _wait(dialog)
    dialog.reject()
