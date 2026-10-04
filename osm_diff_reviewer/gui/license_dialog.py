"""Dialog to record the licence of a reference source (spec 5.5)."""

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..data.license_gate import LICENSE_CONFIRMED, LICENSE_REJECTED, LICENSE_UNCONFIRMED, ReferenceSource
from ..i18n import tr

IMPORT_GUIDELINES_URL = "https://wiki.openstreetmap.org/wiki/Import/Guidelines"
_STATUS_LABELS = {
    LICENSE_UNCONFIRMED: "Not checked",
    LICENSE_CONFIRMED: "Confirmed: may be used in OSM",
    LICENSE_REJECTED: "Not compatible with OSM",
}


class LicenseDialog(QDialog):
    def __init__(self, source: ReferenceSource, parent=None) -> None:
        super().__init__(parent)
        self._source = source
        self.setWindowTitle(tr("Reference data licence"))

        self.name_label = QLabel(source.name)
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
        form.addRow(tr("Licence"), self.license_edit)
        form.addRow(tr("Attribution"), self.attribution_edit)
        form.addRow(tr("Use in OSM"), self.status_combo)
        form.addRow(tr("Evidence URL"), self.evidence_edit)

        notice = QLabel(
            tr(
                "Reference data can only be exported (JOSM reference layer, GeoJSON, MapRoulette) when its use in "
                "OSM is confirmed. Matching and reviewing work regardless. Adding external data to OSM may fall "
                'under the <a href="{}">Import Guidelines</a>; consult your local community before large changes.'
            ).format(IMPORT_GUIDELINES_URL)
        )
        notice.setWordWrap(True)
        notice.setOpenExternalLinks(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(notice)
        layout.addWidget(buttons)

    def source(self) -> ReferenceSource:
        return ReferenceSource(
            name=self._source.name,
            license_name=self.license_edit.text().strip(),
            attribution=self.attribution_edit.text().strip(),
            license_status=self.status_combo.currentData(),
            evidence_url=self.evidence_edit.text().strip(),
            key_field=self._source.key_field,
            source_uri=self._source.source_uri,
        )
