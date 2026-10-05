"""Dialog to record the licence of a reference source (spec 5.5), with its decision history."""

from collections.abc import Sequence

from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..data.license_gate import LICENSE_CONFIRMED, LICENSE_REJECTED, LICENSE_UNCONFIRMED, ReferenceSource
from ..data.store import LicenseRecord
from ..i18n import tr

IMPORT_GUIDELINES_URL = "https://wiki.openstreetmap.org/wiki/Import/Guidelines"
_STATUS_LABELS = {
    LICENSE_UNCONFIRMED: "Not checked",
    LICENSE_CONFIRMED: "Confirmed: may be used in OSM",
    LICENSE_REJECTED: "Not compatible with OSM",
}
_ACTION_LABELS = {
    "recorded": "Recorded",
    "reconfirmed": "Reconfirmed for a new file",
    "reset": "Reset: the ID field changed",
}
_HISTORY_HEADERS = {
    "decided_at": "Date",
    "action": "Decision",
    "license_status": "Use in OSM",
    "source_uri": "File",
    "license_name": "Licence",
}


def _label(table: dict[str, str], key: str) -> str:
    return tr(table[key]) if key in table else key


class LicenseDialog(QDialog):
    def __init__(self, source: ReferenceSource, parent=None, history: Sequence[LicenseRecord] = ()) -> None:
        super().__init__(parent)
        self._source = source
        self.setWindowTitle(tr("Reference data licence"))

        self.name_label = QLabel(source.name)
        self.file_label = QLabel(source.source_uri or "—")
        self.file_label.setWordWrap(True)
        self.license_edit = QLineEdit(source.license_name)
        self.attribution_edit = QLineEdit(source.attribution)
        self.evidence_edit = QLineEdit(source.evidence_url)
        self.evidence_edit.setPlaceholderText("https://")
        self.status_combo = QComboBox()
        for status, label in _STATUS_LABELS.items():
            self.status_combo.addItem(tr(label), status)
        self.status_combo.setCurrentIndex(self.status_combo.findData(source.license_status))

        form = QFormLayout()
        form.addRow(tr("Reference source"), self.name_label)
        form.addRow(tr("Current file"), self.file_label)
        form.addRow(tr("Licence"), self.license_edit)
        form.addRow(tr("Attribution"), self.attribution_edit)
        form.addRow(tr("Use in OSM"), self.status_combo)
        form.addRow(tr("Evidence URL"), self.evidence_edit)

        self.version_label = QLabel(
            tr(
                "Confirmed on {} for an earlier file ({}). Save with \"Confirmed\" to confirm the licence for the "
                "current file, or answer the question shown before the next export."
            ).format(source.confirmed_at[:10], source.confirmed_uri)
        )
        self.version_label.setWordWrap(True)
        self.version_label.setVisible(source.version_changed)

        notice = QLabel(
            tr(
                "Reference data can only be exported (JOSM reference layer, GeoJSON, MapRoulette) when its use in "
                "OSM is confirmed. Matching and reviewing work regardless. Adding external data to OSM may fall "
                'under the <a href="{}">Import Guidelines</a>; consult your local community before large changes.'
            ).format(IMPORT_GUIDELINES_URL)
        )
        notice.setWordWrap(True)
        notice.setOpenExternalLinks(True)

        self.history_table = self._history_table(history)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.version_label)
        layout.addWidget(notice)
        layout.addWidget(QLabel(tr("History")))
        layout.addWidget(self.history_table)
        layout.addWidget(buttons)

    @staticmethod
    def _history_table(history: Sequence[LicenseRecord]) -> QTableWidget:
        columns = list(_HISTORY_HEADERS)
        table = QTableWidget(len(history), len(columns))
        table.setHorizontalHeaderLabels([tr(_HISTORY_HEADERS[c]) for c in columns])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for row, record in enumerate(history):
            texts = {
                "decided_at": record.decided_at.replace("T", " ")[:16],
                "action": _label(_ACTION_LABELS, record.action),
                "license_status": _label(_STATUS_LABELS, record.license_status),
                "source_uri": record.source_uri,
                "license_name": record.license_name,
            }
            for column, key in enumerate(columns):
                table.setItem(row, column, QTableWidgetItem(texts[key]))
        return table

    def source(self) -> ReferenceSource:
        return ReferenceSource(
            name=self._source.name,
            license_name=self.license_edit.text().strip(),
            attribution=self.attribution_edit.text().strip(),
            license_status=self.status_combo.currentData(),
            evidence_url=self.evidence_edit.text().strip(),
            key_field=self._source.key_field,
            source_uri=self._source.source_uri,
            confirmed_uri=self._source.confirmed_uri,
            confirmed_at=self._source.confirmed_at,
        )
