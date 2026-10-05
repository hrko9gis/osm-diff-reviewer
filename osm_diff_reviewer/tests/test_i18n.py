"""Japanese translation: complete, compiled, and installed according to the QGIS locale."""

import sys
from pathlib import Path

import pytest
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, QTranslator

import osm_diff_reviewer
from osm_diff_reviewer.i18n import CONTEXT, tr
from osm_diff_reviewer.tests.test_plugin import _FakeIface

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import i18n as i18n_tool  # noqa: E402


def test_every_string_has_a_japanese_translation():
    translations = i18n_tool.read_translations(i18n_tool.ts_path("ja"))
    missing = [s for s in i18n_tool.collect() if s not in translations]
    assert missing == [], "run: python scripts/i18n.py update, translate, then release"


def test_compiled_qm_matches_ts(qgis_app):
    translator = QTranslator()
    assert translator.load(str(i18n_tool.ts_path("ja").with_suffix(".qm")))
    translations = i18n_tool.read_translations(i18n_tool.ts_path("ja"))
    # Through QCoreApplication: PyQt5's QTranslator.translate() encodes its arguments as ASCII.
    QCoreApplication.installTranslator(translator)
    try:
        stale = [s for s, t in translations.items() if QCoreApplication.translate(CONTEXT, s) != t]
    finally:
        QCoreApplication.removeTranslator(translator)
    assert stale == [], "run: python scripts/i18n.py release"


def test_placeholders_are_kept_in_translations():
    import re

    placeholder = re.compile(r"\{[^}]*\}")
    for source, translation in i18n_tool.read_translations(i18n_tool.ts_path("ja")).items():
        expected = sorted(p.replace("{0}", "{}").replace("{1}", "{}") for p in placeholder.findall(source))
        actual = sorted(p.replace("{0}", "{}").replace("{1}", "{}") for p in placeholder.findall(translation))
        assert actual == expected, source


def _use_locale(monkeypatch, locale):
    """QGIS fixes its UI language at startup (QGIS 4 caches it), so tests stub QgsApplication.locale()."""
    from osm_diff_reviewer import i18n as i18n_module

    class _App:
        @staticmethod
        def locale():
            return locale

    monkeypatch.setattr(i18n_module, "QgsApplication", _App)


@pytest.fixture()
def japanese_locale(qgis_app, monkeypatch):
    _use_locale(monkeypatch, "ja")


def test_plugin_installs_and_removes_japanese_translator(japanese_locale):
    plugin = osm_diff_reviewer.classFactory(_FakeIface())
    try:
        assert tr("Save") == "保存"
        assert QCoreApplication.translate(CONTEXT, "Review panel") == "レビューパネル"
    finally:
        plugin.unload()
    assert tr("Save") == "Save"


def test_unknown_locale_keeps_english(qgis_app, monkeypatch):
    _use_locale(monkeypatch, "xx")
    plugin = osm_diff_reviewer.classFactory(_FakeIface())
    try:
        assert tr("Save") == "Save"
    finally:
        plugin.unload()


def test_settings_are_the_fallback_when_qgis_reports_no_locale(qgis_app, monkeypatch):
    _use_locale(monkeypatch, "")
    settings = QgsSettings()
    previous = settings.value("locale/userLocale", "")
    settings.setValue("locale/userLocale", "ja_JP")
    plugin = osm_diff_reviewer.classFactory(_FakeIface())
    try:
        assert tr("Save") == "保存"
    finally:
        plugin.unload()
        settings.setValue("locale/userLocale", previous)


def test_user_facing_errors_are_translated(japanese_locale):
    from osm_diff_reviewer.data.license_gate import LICENSE_UNCONFIRMED, LicenseGateError, ReferenceSource, ensure_export_allowed

    plugin = osm_diff_reviewer.classFactory(_FakeIface())
    try:
        with pytest.raises(LicenseGateError) as error:
            ensure_export_allowed(ReferenceSource("施設", "", "", LICENSE_UNCONFIRMED, "", None))
        assert "ライセンス" in str(error.value)
    finally:
        plugin.unload()
