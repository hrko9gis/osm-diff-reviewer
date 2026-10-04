"""Shared pytest setup: a headless QgsApplication with Processing initialised."""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile  # noqa: E402

from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QCoreApplication, QSettings  # noqa: E402

_APP = QgsApplication([], True)  # GUI enabled for widget tests (offscreen)
_APP.initQgis()

# Keep QgsSettings written by tests away from the developer's real QGIS profile.
_SETTINGS_DIR = tempfile.mkdtemp(prefix="osm_diff_reviewer_settings_")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
QCoreApplication.setOrganizationName("OsmDiffReviewerTests")
QCoreApplication.setApplicationName("tests")

_PLUGINS_DIR = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
if _PLUGINS_DIR not in sys.path:
    sys.path.append(_PLUGINS_DIR)

from processing.core.Processing import Processing  # noqa: E402

Processing.initialize()


@pytest.fixture(scope="session")
def qgis_app():
    return _APP


@pytest.fixture(scope="session")
def m1_dir():
    return DATA_DIR / "m1"
