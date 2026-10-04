import pytest

from osm_diff_reviewer import settings
from osm_diff_reviewer.gui.settings_dialog import SettingsDialog


@pytest.fixture()
def restore_settings(qgis_app):
    saved = settings.josm_url(), settings.overpass_url()
    yield
    settings.set_josm_url(saved[0])
    settings.set_overpass_url(saved[1])


def test_defaults(restore_settings):
    settings.set_josm_url("")
    settings.set_overpass_url("")
    assert settings.josm_url() == settings.DEFAULT_JOSM_URL == "http://127.0.0.1:8111"
    assert settings.overpass_url() == settings.DEFAULT_OVERPASS_URL


def test_dialog_saves_valid_values(restore_settings):
    dialog = SettingsDialog()
    dialog.josm_edit.setText("http://localhost:8112/")
    dialog.overpass_edit.setText("https://overpass.kumi.systems/api/interpreter")
    assert dialog.save() is True
    assert settings.josm_url() == "http://localhost:8112"
    assert settings.overpass_url() == "https://overpass.kumi.systems/api/interpreter"


def test_dialog_rejects_non_local_josm(restore_settings):
    before = settings.josm_url()
    dialog = SettingsDialog()
    dialog.josm_edit.setText("http://example.com:8111")
    assert dialog.save() is False
    assert dialog.error_label.text() != ""
    assert settings.josm_url() == before
