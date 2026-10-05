"""M3 acceptance: from a candidate, JOSM opens the area with the object selected,
and the user is told what to do when JOSM is not running."""

import json
import time

import pytest
from qgis.PyQt.QtCore import QCoreApplication

from osm_diff_reviewer import settings
from osm_diff_reviewer.data.http import HttpResponse
from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.gui.review_dock import ReviewDock
from osm_diff_reviewer.tests.fakes import FakeHttp, FakeJosm, free_port_url
from osm_diff_reviewer.tests.test_review_dock import _Iface
from osm_diff_reviewer.tests.test_store import _record


@pytest.fixture()
def josm_url_setting():
    previous = settings.josm_url()
    yield
    settings.set_josm_url(previous)


@pytest.fixture()
def dock(qgis_app, tmp_path, josm_url_setting):
    store = WorkspaceStore.create(tmp_path / "work.gpkg")
    store.record_run(
        "src",
        json.dumps({"attribute_mappings": [{"reference_field": "名称", "osm_tag": "name"}]}),
        [_record("R1"), _record("R2", None, None, None, "missing")],
    )
    widget = ReviewDock(_Iface())
    widget.set_workspace(str(store.path))
    yield widget
    widget.cleanup()
    widget.close()


def _paths(server):
    return [path for path, _, _ in server.requests]


def _wait(dock, seconds=15):
    deadline = time.monotonic() + seconds
    while dock.task_running() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert not dock.task_running(), "background task did not finish"


def test_open_candidate_zooms_and_selects_in_josm(dock):
    with FakeJosm() as josm:
        settings.set_josm_url(josm.url)
        dock.select_proxy_row(0)
        dock.open_in_josm()
        _wait(dock)
    assert _paths(josm) == ["/version", "/load_and_zoom"]
    query = josm.requests[1][1]
    assert query["select"] == ["node1"]
    assert float(query["left"][0]) < 139.7 < float(query["right"][0])
    assert float(query["bottom"][0]) < 35.68 < float(query["top"][0])
    assert "JOSM" in dock.message_label.text()


def test_josm_not_running_shows_guidance(dock):
    settings.set_josm_url(free_port_url())
    dock.select_proxy_row(0)
    dock.open_in_josm()
    _wait(dock)
    assert "Remote Control" in dock.message_label.text()


def test_next_and_open_moves_on_and_opens(dock):
    with FakeJosm() as josm:
        settings.set_josm_url(josm.url)
        dock.select_proxy_row(0)
        dock.next_and_open()
        _wait(dock)
    assert dock.current_row().ref_key == "R2"
    assert _paths(josm) == ["/version", "/load_and_zoom"]
    assert "select" not in josm.requests[1][1]


def test_reference_layer_needs_confirmed_licence(dock):
    dock.select_proxy_row(1)
    dock.send_reference_check.setChecked(True)
    with FakeJosm() as josm:
        settings.set_josm_url(josm.url)
        dock.open_in_josm()
        _wait(dock)
        assert _paths(josm) == ["/version", "/load_and_zoom"]
        assert "licence" in dock.message_label.text().lower()
        josm.requests.clear()

        store = dock.store
        source, _ = store.ensure_reference_source("src", None, "")
        store.save_reference_source(source.__class__(**{**vars(source), "license_status": LICENSE_CONFIRMED}))
        dock.open_in_josm()
        _wait(dock)
    assert _paths(josm) == ["/version", "/load_and_zoom", "/load_data"]
    assert json.dumps(josm.requests[2][1]["upload_policy"]) == '["never"]'


def test_check_in_osm_reports_new_version(dock):
    dock.http = FakeHttp(HttpResponse(200, b'{"elements": [{"type": "node", "id": 1, "version": 2}]}'))
    dock.select_proxy_row(0)
    dock.check_in_osm()
    _wait(dock)
    assert "v1" in dock.message_label.text() and "v2" in dock.message_label.text()


def test_check_in_osm_reports_unchanged_and_deleted(dock):
    dock.select_proxy_row(0)
    dock.http = FakeHttp(HttpResponse(200, b'{"elements": [{"type": "node", "id": 1, "version": 1}]}'))
    dock.check_in_osm()
    _wait(dock)
    unchanged = dock.message_label.text()
    dock.http = FakeHttp(HttpResponse(200, b'{"elements": []}'))
    dock.check_in_osm()
    _wait(dock)
    assert unchanged != dock.message_label.text() and dock.message_label.text() != ""


def test_check_in_osm_without_osm_object_explains(dock):
    dock.http = FakeHttp()
    dock.select_proxy_row(1)
    dock.check_in_osm()
    _wait(dock)
    assert dock.http.requests == []
    assert dock.message_label.text() != ""


def test_buttons_are_disabled_while_a_request_runs(dock):
    import threading

    release = threading.Event()

    class SlowHttp(FakeHttp):
        def post_form(self, url, fields):
            release.wait(5)
            return HttpResponse(200, b'{"elements": []}')

    dock.http = SlowHttp()
    dock.select_proxy_row(0)
    dock.check_in_osm()
    assert dock.task_running() and not dock.open_button.isEnabled()
    release.set()
    _wait(dock)
    assert dock.open_button.isEnabled()


def test_reference_layer_after_new_version_asks_and_sends(dock):
    from dataclasses import replace

    store = dock.store
    source, _ = store.ensure_reference_source("src", None, "/data/v2.gpkg")
    store.save_reference_source(
        replace(source, license_status=LICENSE_CONFIRMED, confirmed_uri="/data/v1.gpkg", confirmed_at="2026-10-05")
    )
    dock.select_proxy_row(1)
    dock.send_reference_check.setChecked(True)
    dock.ask_reconfirm = lambda source: True
    with FakeJosm() as josm:
        settings.set_josm_url(josm.url)
        dock.open_in_josm()
        _wait(dock)
    assert _paths(josm) == ["/version", "/load_and_zoom", "/load_data"]
    assert store.license_history("src")[0].action == "reconfirmed"
