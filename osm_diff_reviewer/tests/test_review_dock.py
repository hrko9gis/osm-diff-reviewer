"""Smoke tests of the review dock against a real workspace (no QGIS main window)."""

import pytest
from qgis.gui import QgsMapCanvas

from osm_diff_reviewer.core import review
from osm_diff_reviewer.data.store import WorkspaceStore
from osm_diff_reviewer.gui.review_dock import ReviewDock
from osm_diff_reviewer.tests.test_store import _record


class _Iface:
    def __init__(self):
        self.canvas = QgsMapCanvas()

    def mapCanvas(self):
        return self.canvas


@pytest.fixture()
def dock(qgis_app, tmp_path):
    store = WorkspaceStore.create(tmp_path / "work.gpkg")
    store.record_run(
        "src", "{}", [_record("R1"), _record("R2", None, None, None, "missing"), _record("R3", "way", 3)]
    )
    widget = ReviewDock(_Iface())
    widget.set_workspace(str(store.path))
    yield widget
    widget.cleanup()
    widget.close()


def test_dock_lists_rows_of_latest_run(dock):
    assert dock.source_combo.currentText() == "src"
    assert dock.proxy.rowCount() == 3


def test_selecting_a_row_shows_details_and_highlights(dock):
    dock.select_proxy_row(0)
    assert dock.current_row().ref_key == "R1"
    texts = {dock.detail_table.item(r, 0).text() for r in range(dock.detail_table.rowCount())}
    assert {"名称", "name"} <= texts
    assert dock.reference_band.numberOfVertices() > 0
    assert dock.osm_band.numberOfVertices() > 0


def test_saving_a_review_persists_and_hides_row(dock):
    dock.select_proxy_row(0)
    dock.status_combo.setCurrentIndex(dock.status_combo.findData(review.NOT_NEEDED_OSM))
    dock.note_edit.setPlainText("OSM が正しい")
    dock.save_review()
    stored = WorkspaceStore.open(dock.workspace_path).load_rows(1)
    assert {r.ref_key: (r.status, r.note) for r in stored}["R1"] == (review.NOT_NEEDED_OSM, "OSM が正しい")
    assert dock.proxy.rowCount() == 2


def test_next_candidate_moves_selection(dock):
    dock.select_proxy_row(0)
    dock.select_next()
    assert dock.current_row().ref_key == "R2"


def test_invalid_workspace_shows_message_and_clears(dock, tmp_path):
    dock.set_workspace(str(tmp_path / "nothing.gpkg"))
    assert dock.proxy.rowCount() == 0
    assert dock.message_label.text() != ""


def test_detail_rows_put_mapped_pairs_first_and_flag_mismatch(qgis_app):
    from dataclasses import replace

    from osm_diff_reviewer.gui.review_dock import detail_rows
    from osm_diff_reviewer.tests.test_review_model import _row

    details = '[{"reference_field": "名称", "osm_tag": "name", "reference_value": "a", "osm_value": "b", "score": 0.0, "ok": false}]'
    row = replace(_row("A"), attribute_details=details, ref_attributes={"名称": "a", "住所": "x"}, osm_tags={"name": "b", "amenity": "y"})
    assert detail_rows(row) == [("名称 ⇔ name", "a", "b", True), ("住所", "x", "", False), ("amenity", "", "y", False)]


def test_license_dialog_returns_edited_source(qgis_app):
    from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED, LICENSE_UNCONFIRMED, ReferenceSource
    from osm_diff_reviewer.gui.license_dialog import LicenseDialog

    dialog = LicenseDialog(ReferenceSource("src", "", "", LICENSE_UNCONFIRMED, "", "id", "u"))
    dialog.license_edit.setText(" CC BY 4.0 ")
    dialog.attribution_edit.setText("○○市")
    dialog.status_combo.setCurrentIndex(dialog.status_combo.findData(LICENSE_CONFIRMED))
    assert dialog.source() == ReferenceSource("src", "CC BY 4.0", "○○市", LICENSE_CONFIRMED, "", "id", "u")


def test_hiding_the_dock_clears_highlights(dock):
    dock.select_proxy_row(0)
    dock.show()
    dock.hide()
    assert dock.reference_band.numberOfVertices() == 0
    assert dock.osm_band.numberOfVertices() == 0


def test_cleanup_removes_bands_from_canvas(dock):
    scene = dock.iface.mapCanvas().scene()
    bands = (dock.reference_band, dock.osm_band)
    assert all(band in scene.items() for band in bands)
    dock.cleanup()
    assert not any(band in scene.items() for band in bands)


def test_workspace_follows_the_project(dock, tmp_path):
    from qgis.core import QgsProject

    QgsProject.instance().clear()
    assert dock.store is None and dock.proxy.rowCount() == 0
    other = WorkspaceStore.create(tmp_path / "other.gpkg")
    other.record_run("other", "{}", [_record("X1")])
    QgsProject.instance().writeEntry("OsmDiffReviewer", "workspace", str(other.path))
    dock.on_project_read()
    assert dock.source_combo.currentText() == "other"
    QgsProject.instance().clear()


def test_reload_button_picks_up_new_runs(dock):
    WorkspaceStore.open(dock.workspace_path).record_run("src", "{}", [_record("R9")])
    dock.reload_button.click()
    assert [dock.proxy.row_at(dock.proxy.index(i, 0)).ref_key for i in range(dock.proxy.rowCount())] == ["R9"]


def test_license_dialog_shows_history_and_new_version_notice(qgis_app):
    from osm_diff_reviewer.data.license_gate import LICENSE_CONFIRMED, ReferenceSource
    from osm_diff_reviewer.data.store import LicenseRecord
    from osm_diff_reviewer.gui.license_dialog import LicenseDialog

    source = ReferenceSource("src", "CC BY 4.0", "○○市", LICENSE_CONFIRMED, "", "id", "/data/v2.gpkg", "/data/v1.gpkg", "2026-10-05T09:00:00+00:00")
    history = [
        LicenseRecord("2026-10-05T09:00:00+00:00", "recorded", LICENSE_CONFIRMED, "/data/v1.gpkg", "CC BY 4.0", "○○市", ""),
    ]
    dialog = LicenseDialog(source, history=history)
    assert dialog.history_table.rowCount() == 1
    assert "/data/v1.gpkg" in dialog.history_table.item(0, 3).text()
    assert "2026-10-05" in dialog.version_label.text() and not dialog.version_label.isHidden()
    # Saving with "confirmed" applies the confirmation to the current file.
    assert dialog.source().license_status == LICENSE_CONFIRMED
