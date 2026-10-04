"""M0 acceptance: the empty plugin loads and its metadata targets the agreed QGIS range."""

import configparser
from pathlib import Path

from qgis.core import QgsApplication

import osm_diff_reviewer

METADATA = Path(osm_diff_reviewer.__file__).parent / "metadata.txt"


class _FakeIface:
    """Only what plugin.py touches; extend as the GUI grows."""

    def mainWindow(self):
        return None


def _provider_ids():
    return [p.id() for p in QgsApplication.processingRegistry().providers()]


def test_class_factory_loads_and_unloads(qgis_app):
    plugin = osm_diff_reviewer.classFactory(_FakeIface())
    plugin.initProcessing()
    plugin.initGui()
    assert "osmdiffreviewer" in _provider_ids()
    plugin.unload()
    assert "osmdiffreviewer" not in _provider_ids()


def test_metadata_targets_qgis_3_40_through_4():
    parser = configparser.ConfigParser()
    parser.read(METADATA, encoding="utf-8")
    general = parser["general"]
    assert general["name"] == "OSM Diff Reviewer"
    assert general["qgisMinimumVersion"] == "3.40"
    assert general["qgisMaximumVersion"].startswith("4.")
    assert general["supportsQt6"] == "True"
    assert general["hasProcessingProvider"] == "yes"
    for key in ("description", "about", "version", "author", "email", "repository"):
        assert general.get(key), key
