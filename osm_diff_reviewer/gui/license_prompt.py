"""One-click reconfirmation of a licence when the reference data comes from a new file."""

from qgis.PyQt.QtWidgets import QMessageBox

from ..data.license_gate import ReferenceSource
from ..i18n import tr


def ask_reconfirm(parent, source: ReferenceSource) -> bool:
    """Ask whether the licence confirmed for an earlier file also applies to the current one."""
    text = tr(
        "The licence of '{}' ({}) was confirmed on {} for:\n{}\n\nThe reference data now comes from:\n{}\n\n"
        "Do the same licence conditions apply to this file? Your answer is recorded in the licence history."
    ).format(source.name, source.license_name or "—", source.confirmed_at[:10], source.confirmed_uri, source.source_uri)
    answer = QMessageBox.question(
        parent,
        tr("Confirm the licence for the new file"),
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
