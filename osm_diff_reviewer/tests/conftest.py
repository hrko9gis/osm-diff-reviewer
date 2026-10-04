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

# A throwaway QGIS profile: settings and the authentication database (API keys) used by
# tests never touch the developer's real profile.
TEST_PROFILE_DIR = tempfile.mkdtemp(prefix="osm_diff_reviewer_profile_")
os.environ["QGIS_CUSTOM_CONFIG_PATH"] = TEST_PROFILE_DIR

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


@pytest.fixture(scope="session")
def auth_manager(qgis_app):
    """QGIS auth database of the throwaway profile, unlocked with a test master password."""
    from qgis.core import QgsApplication

    settings_dir = QgsApplication.qgisSettingsDirPath().replace("\\", "/")
    assert settings_dir.startswith(TEST_PROFILE_DIR.replace("\\", "/")), "refusing to touch a real profile"
    manager = QgsApplication.authManager()
    if not manager.masterPasswordIsSet():
        assert manager.setMasterPassword("test-master-password", True)
    return manager


def store_auth_config(manager, method: str, values: dict) -> str:
    from qgis.core import QgsAuthMethodConfig

    config = QgsAuthMethodConfig(method)
    config.setName(f"test {method}")
    for key, value in values.items():
        config.setConfig(key, value)
    assert manager.storeAuthenticationConfig(config)[0]
    return config.id()
