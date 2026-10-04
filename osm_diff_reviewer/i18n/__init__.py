"""Translation helper. Qt .ts/.qm files for Japanese live in this folder (M6)."""

from qgis.PyQt.QtCore import QCoreApplication

CONTEXT = "OsmDiffReviewer"


def tr(text: str) -> str:
    return QCoreApplication.translate(CONTEXT, text)
