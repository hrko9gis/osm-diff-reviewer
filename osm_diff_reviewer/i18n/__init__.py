"""Translations. ``osm_diff_reviewer_<lang>.ts`` are maintained with ``scripts/i18n.py``."""

from pathlib import Path

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator

CONTEXT = "OsmDiffReviewer"
_DIRECTORY = Path(__file__).resolve().parent


def tr(text: str) -> str:
    return QCoreApplication.translate(CONTEXT, text)


def install_translator() -> QTranslator | None:
    """Install the translation for the QGIS user interface language, if there is one."""
    # QgsApplication.locale() honours QGIS's language override (and --lang); settings are the fallback.
    locale = QgsApplication.locale() or QgsSettings().value("locale/userLocale", "", type=str) or QLocale().name()
    path = _DIRECTORY / f"osm_diff_reviewer_{locale[:2]}.qm"
    translator = QTranslator()
    if not path.exists() or not translator.load(str(path)):
        return None
    QCoreApplication.installTranslator(translator)
    return translator


def remove_translator(translator: QTranslator | None) -> None:
    if translator is not None:
        QCoreApplication.removeTranslator(translator)
