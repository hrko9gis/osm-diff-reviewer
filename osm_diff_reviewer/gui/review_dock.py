"""Review dock: candidate list, side-by-side attributes, review status and note (spec 5.3)."""

import json
from dataclasses import replace
from pathlib import Path

from qgis.core import QgsProject
from qgis.gui import QgsDockWidget, QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import matching, review
from ..core.review import ReviewRow
from ..data.http import LocalHttpClient, QgisHttpClient
from ..data.store import StoreError, WorkspaceStore
from ..i18n import tr
from . import handover, highlight
from .background import BackgroundRunner
from .license_dialog import LicenseDialog
from .maproulette_dialog import MapRouletteDialog
from .settings_dialog import SettingsDialog
from .review_model import ReviewFilterProxy, ReviewTableModel, change_label, classification_label, osm_label

PROJECT_SCOPE = "OsmDiffReviewer"
PROJECT_WORKSPACE_KEY = "workspace"
MATCH_ALGORITHM = "osmdiffreviewer:match"
MISMATCH_BRUSH = QBrush(QColor(255, 220, 200))


def detail_rows(row: ReviewRow) -> list[tuple[str, str, str, bool]]:
    """(item, reference value, OSM value, mismatch) — mapped pairs first, then the rest of each side."""
    try:
        mapped = json.loads(row.attribute_details or "[]")
    except json.JSONDecodeError:
        mapped = []
    used_fields = {d["reference_field"] for d in mapped}
    used_tags = {d["osm_tag"] for d in mapped}
    rows = [(f"{d['reference_field']} ⇔ {d['osm_tag']}", d["reference_value"], d["osm_value"], not d["ok"]) for d in mapped]
    rows += [(k, "" if v is None else str(v), "", False) for k, v in row.ref_attributes.items() if k not in used_fields]
    rows += [(k, "", str(v), False) for k, v in sorted(row.osm_tags.items()) if k not in used_tags]
    return rows


class ReviewDock(QgsDockWidget):
    def __init__(self, iface, parent=None) -> None:
        super().__init__(tr("OSM Diff Reviewer"), parent)
        self.setObjectName("OsmDiffReviewerDock")
        self.iface = iface
        self.workspace_path: str | None = None
        self.store: WorkspaceStore | None = None
        self._cleaned_up = False
        self.http = QgisHttpClient()  # Overpass: follows the QGIS proxy settings
        self.josm_http = LocalHttpClient()  # JOSM on this computer: never through a proxy
        self.runner = BackgroundRunner(lambda busy: self._update_buttons(), self._message)
        self.model =ReviewTableModel(self)
        self.proxy = ReviewFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        canvas = iface.mapCanvas()
        self.reference_band = highlight.make_band(canvas, highlight.REFERENCE_COLOR)
        self.osm_band = highlight.make_band(canvas, highlight.OSM_COLOR)
        self._build_ui()
        self.visibilityChanged.connect(lambda visible: visible or self._clear_highlight())
        project = QgsProject.instance()
        project.readProject.connect(self.on_project_read)
        project.cleared.connect(self.on_project_cleared)
        self.on_project_read()

    def cleanup(self) -> None:
        """Undo everything attached outside the dock; called when the plugin unloads. Idempotent."""
        if self._cleaned_up:
            return
        self._cleaned_up = True
        self.runner.close()
        project = QgsProject.instance()
        project.readProject.disconnect(self.on_project_read)
        project.cleared.disconnect(self.on_project_cleared)
        scene = self.iface.mapCanvas().scene()
        for band in (self.reference_band, self.osm_band):
            band.reset()
            scene.removeItem(band)

    def on_project_read(self, *_) -> None:
        """Each project remembers its workspace; follow it when a project is opened."""
        path, _ = QgsProject.instance().readEntry(PROJECT_SCOPE, PROJECT_WORKSPACE_KEY, "")
        if not path:
            self.on_project_cleared()
            return
        self.file_widget.blockSignals(True)
        self.file_widget.setFilePath(path)
        self.file_widget.blockSignals(False)
        self.set_workspace(path)

    def on_project_cleared(self) -> None:
        self.store = None
        self.workspace_path = None
        self.file_widget.blockSignals(True)
        self.file_widget.setFilePath("")
        self.file_widget.blockSignals(False)
        self._message("")
        self._set_sources([])

    # ----- layout ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.file_widget = QgsFileWidget()
        self.file_widget.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.file_widget.setFilter(tr("GeoPackage (*.gpkg)"))
        self.file_widget.setDialogTitle(tr("Workspace GeoPackage"))
        self.file_widget.fileChanged.connect(self._on_file_chosen)
        self.run_button = QPushButton(tr("Run matching…"))
        self.run_button.clicked.connect(self.run_matching)
        self.reload_button = QPushButton(tr("Reload"))
        self.reload_button.setToolTip(tr("Show the latest run, e.g. after running matching from the Processing toolbox"))
        self.reload_button.clicked.connect(lambda: self.workspace_path and self.set_workspace(self.workspace_path))

        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(lambda _: self.reload())
        self.license_button = QPushButton(tr("Licence…"))
        self.license_button.clicked.connect(self.edit_license)

        self.classification_filter = QComboBox()
        self.classification_filter.addItem(tr("All classifications"), None)
        for code in matching.CLASSIFICATIONS:
            self.classification_filter.addItem(classification_label(code), code)
        self.classification_filter.currentIndexChanged.connect(
            lambda _: self.proxy.set_classification(self.classification_filter.currentData())
        )
        self.status_filter = QComboBox()
        self.status_filter.addItem(tr("All statuses"), None)
        for status in review.STATUSES:
            self.status_filter.addItem(review.status_label(status, tr), status)
        self.status_filter.currentIndexChanged.connect(lambda _: self.proxy.set_status(self.status_filter.currentData()))
        self.show_matches_check = QCheckBox(tr("Show matches"))
        self.show_matches_check.toggled.connect(self.proxy.set_show_matches)
        self.show_hidden_check = QCheckBox(tr("Show 'not needed'"))
        self.show_hidden_check.toggled.connect(self.proxy.set_show_hidden)
        self.recheck_check = QCheckBox(tr("Recheck only"))
        self.recheck_check.toggled.connect(self.proxy.set_recheck_only)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(lambda current, _: self._show_current(current))

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.detail_table = QTableWidget(0, 3)
        self.detail_table.setHorizontalHeaderLabels([tr("Item"), tr("Reference"), tr("OSM")])
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_combo = QComboBox()
        for status in review.STATUSES:
            self.status_combo.addItem(review.status_label(status, tr), status)
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText(tr("Note"))
        self.note_edit.setMaximumHeight(60)
        self.save_button = QPushButton(tr("Save"))
        self.save_button.clicked.connect(self.save_review)
        self.next_button = QPushButton(tr("Next candidate"))
        self.next_button.clicked.connect(self.select_next)
        self.open_button = QPushButton(tr("Open in JOSM"))
        self.open_button.clicked.connect(self.open_in_josm)
        self.next_open_button = QPushButton(tr("Next && open"))
        self.next_open_button.clicked.connect(self.next_and_open)
        self.check_button = QPushButton(tr("Check in OSM"))
        self.check_button.setToolTip(tr("Re-read the OSM version via Overpass to see whether the object changed"))
        self.check_button.clicked.connect(self.check_in_osm)
        self.send_reference_check = QCheckBox(tr("Send reference as a JOSM layer (missing only)"))
        self.send_reference_check.setToolTip(
            tr("Never uploaded; needs a confirmed licence of the reference data")
        )
        self.maproulette_button = QPushButton(tr("MapRoulette…"))
        self.maproulette_button.setToolTip(tr("Export or send the candidates shown in the list as MapRoulette tasks"))
        self.maproulette_button.clicked.connect(self.open_maproulette)
        self.settings_button = QPushButton(tr("Settings…"))
        self.settings_button.clicked.connect(lambda: SettingsDialog(self).exec())
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.setWidget(self._compose())
        self._set_editing_enabled(False)

    def _compose(self) -> QWidget:
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.file_widget, 1)
        workspace_row.addWidget(self.run_button)
        workspace_row.addWidget(self.reload_button)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel(tr("Reference source")))
        source_row.addWidget(self.source_combo, 1)
        source_row.addWidget(self.license_button)
        source_row.addWidget(self.maproulette_button)
        filter_row = QHBoxLayout()
        for widget in (self.classification_filter, self.status_filter):
            filter_row.addWidget(widget, 1)
        check_row = QHBoxLayout()
        for widget in (self.show_matches_check, self.show_hidden_check, self.recheck_check):
            check_row.addWidget(widget)
        check_row.addStretch(1)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(self.summary_label)
        detail_layout.addWidget(self.detail_table, 1)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_combo, 1)
        status_row.addWidget(self.save_button)
        status_row.addWidget(self.next_button)
        detail_layout.addLayout(status_row)
        detail_layout.addWidget(self.note_edit)
        josm_row = QHBoxLayout()
        for widget in (self.open_button, self.next_open_button, self.check_button):
            josm_row.addWidget(widget)
        josm_row.addStretch(1)
        josm_row.addWidget(self.settings_button)
        detail_layout.addLayout(josm_row)
        detail_layout.addWidget(self.send_reference_check)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(detail)

        root = QWidget()
        layout = QVBoxLayout(root)
        for row in (workspace_row, source_row, filter_row, check_row):
            layout.addLayout(row)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.message_label)
        return root

    # ----- workspace and data ------------------------------------------------------

    def _on_file_chosen(self, path: str) -> None:
        if not path:
            return
        if not path.lower().endswith(".gpkg"):
            path += ".gpkg"
        try:
            if not Path(path).exists():
                WorkspaceStore.create(path)
        except StoreError as error:
            self._message(str(error))
            return
        QgsProject.instance().writeEntry(PROJECT_SCOPE, PROJECT_WORKSPACE_KEY, path)
        self.set_workspace(path)

    def set_workspace(self, path: str) -> None:
        self.workspace_path = path
        try:
            self.store = WorkspaceStore.open(path)
        except StoreError as error:
            self.store = None
            self._message(str(error))
            self._set_sources([])
            return
        self._message("")
        self._set_sources(self.store.source_names_with_runs())

    def _set_sources(self, names: list[str]) -> None:
        current = self.source_combo.currentText()
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(names)
        if current in names:
            self.source_combo.setCurrentText(current)
        self.source_combo.blockSignals(False)
        self.reload()

    def reload(self) -> None:
        rows: list[ReviewRow] = []
        source_name = self.source_combo.currentText()
        if self.store is not None and source_name:
            try:
                run_id = self.store.latest_run_id(source_name)
                rows = self.store.load_rows(run_id) if run_id is not None else []
            except StoreError as error:
                self._message(str(error))
        self.model.set_rows(rows)
        self._show_current(self.table.currentIndex())

    def run_matching(self) -> None:
        import processing  # QGIS Processing plugin; only needed when the user starts a run

        if self.store is None:
            self._message(tr("Choose or create a workspace GeoPackage first."))
            return
        processing.execAlgorithmDialog(MATCH_ALGORITHM, {"WORKSPACE": str(self.store.path)})
        self.set_workspace(str(self.store.path))

    def edit_license(self) -> None:
        source_name = self.source_combo.currentText()
        if self.store is None or not source_name:
            return
        try:
            source = self.store.reference_source(source_name) or self.store.ensure_reference_source(source_name, None, "")[0]
            dialog = LicenseDialog(source, self)
            if dialog.exec():
                self.store.save_reference_source(dialog.source())
        except StoreError as error:
            self._message(str(error))

    # ----- selection and review ----------------------------------------------------

    def current_row(self) -> ReviewRow | None:
        index = self.table.currentIndex()
        return self.proxy.row_at(index) if index.isValid() else None

    def select_proxy_row(self, proxy_row: int) -> None:
        if 0 <= proxy_row < self.proxy.rowCount():
            self.table.selectRow(proxy_row)
            self.table.setCurrentIndex(self.proxy.index(proxy_row, 0))

    def select_next(self) -> None:
        current = self.table.currentIndex()
        self.select_proxy_row(current.row() + 1 if current.isValid() else 0)

    def save_review(self) -> None:
        index = self.table.currentIndex()
        row = self.current_row()
        if row is None or self.store is None:
            return
        status, note = self.status_combo.currentData(), self.note_edit.toPlainText().strip()
        try:
            self.store.save_review(row, status, note)
        except StoreError as error:
            self._message(str(error))
            return
        source_row = self.proxy.mapToSource(index).row()
        self.model.replace_row(source_row, replace(row, status=status, note=note, needs_recheck=False))
        self.proxy.invalidate()
        self.select_proxy_row(min(index.row(), self.proxy.rowCount() - 1))
        self._message(tr("Saved."))

    def _show_current(self, index) -> None:
        row = self.proxy.row_at(index) if index is not None and index.isValid() else None
        self._set_editing_enabled(row is not None)
        self.detail_table.setRowCount(0)
        if row is None:
            self.summary_label.clear()
            self._clear_highlight()
            return
        self.summary_label.setText(self._summary(row))
        for item, ref_value, osm_value, mismatch in detail_rows(row):
            position = self.detail_table.rowCount()
            self.detail_table.insertRow(position)
            for column, text in enumerate((item, ref_value, osm_value)):
                cell = QTableWidgetItem(text)
                if mismatch:
                    cell.setBackground(MISMATCH_BRUSH)
                self.detail_table.setItem(position, column, cell)
        self.status_combo.setCurrentIndex(self.status_combo.findData(row.status))
        self.note_edit.setPlainText(row.note)
        shown = [g for g in (highlight.show(self.reference_band, row.ref_wkt), highlight.show(self.osm_band, row.osm_wkt)) if g]
        highlight.zoom_to(self.iface.mapCanvas(), shown)

    @staticmethod
    def _summary(row: ReviewRow) -> str:
        parts = [row.ref_key or "—", "⇔", osm_label(row) or "—", "·", classification_label(row.classification)]
        if row.change_kind:
            parts.append(f"· {change_label(row)}")
        if row.total_score is not None:
            parts.append(f"· {tr('score')} {row.total_score:.2f}")
        if row.distance_m is not None:
            parts.append(f"· {row.distance_m:.1f} m")
        if row.alternatives:
            parts.append(f"· {tr('alternatives')}: {row.alternatives}")
        if row.needs_recheck:
            parts.append(f"· {tr('Changed since the decision: recheck')}")
        return " ".join(parts)

    def task_running(self) -> bool:
        return self.runner.running()

    def visible_rows(self) -> list[ReviewRow]:
        return [self.proxy.row_at(self.proxy.index(i, 0)) for i in range(self.proxy.rowCount())]

    def open_maproulette(self) -> None:
        source_name = self.source_combo.currentText()
        if self.store is None or not source_name:
            self._message(tr("Run matching first."))
            return
        MapRouletteDialog(self.store, source_name, self.visible_rows(), self).exec()
        self.reload()

    def open_in_josm(self) -> None:
        row = self.current_row()
        if row is None or self.store is None:
            return
        store, http, send = self.store, self.josm_http, self.send_reference_check.isChecked()
        self.runner.run(tr("Open in JOSM"), lambda: handover.open_in_josm(row, store, http, send))

    def next_and_open(self) -> None:
        before = self.table.currentIndex().row()
        self.select_next()
        if self.table.currentIndex().row() != before:
            self.open_in_josm()

    def check_in_osm(self) -> None:
        row = self.current_row()
        if row is not None:
            http = self.http
            self.runner.run(tr("Check in OSM"), lambda: handover.check_in_osm(row, http))

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (self.status_combo, self.note_edit, self.save_button):
            widget.setEnabled(enabled)
        self._update_buttons()

    def _update_buttons(self) -> None:
        idle = not self.task_running()
        has_row = self.table.currentIndex().isValid()
        for widget in (self.open_button, self.check_button):
            widget.setEnabled(idle and has_row)
        self.next_open_button.setEnabled(idle)

    def _message(self, text: str) -> None:
        self.message_label.setText(text)

    def _clear_highlight(self) -> None:
        highlight.show(self.reference_band, "")
        highlight.show(self.osm_band, "")
