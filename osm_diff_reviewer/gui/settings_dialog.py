"""Plugin settings: JOSM Remote Control address and Overpass endpoint."""

from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from .. import settings
from ..data.osm_fetch import OverpassError, validate_endpoint
from ..export.josm import JosmError, validate_base_url
from ..i18n import tr


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("OSM Diff Reviewer settings"))
        self.josm_edit = QLineEdit(settings.josm_url())
        self.josm_edit.setPlaceholderText(settings.DEFAULT_JOSM_URL)
        self.overpass_edit = QLineEdit(settings.overpass_url())
        self.overpass_edit.setPlaceholderText(settings.DEFAULT_OVERPASS_URL)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow(tr("JOSM Remote Control"), self.josm_edit)
        form.addRow(tr("Overpass API"), self.overpass_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: self.save() and self.accept())
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

    def save(self) -> bool:
        """Validate and store; on error show it and store nothing."""
        try:
            josm = validate_base_url(self.josm_edit.text().strip() or settings.DEFAULT_JOSM_URL)
            overpass = validate_endpoint(self.overpass_edit.text().strip() or settings.DEFAULT_OVERPASS_URL)
        except (JosmError, OverpassError) as error:
            self.error_label.setText(str(error))
            return False
        settings.set_josm_url(josm)
        settings.set_overpass_url(overpass)
        self.error_label.clear()
        return True
