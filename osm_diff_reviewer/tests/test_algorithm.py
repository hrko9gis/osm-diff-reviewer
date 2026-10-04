"""M1 acceptance: the matching runs as a Processing algorithm without the GUI."""

import json

import processing
import pytest
from qgis.core import QgsApplication, QgsVectorLayer

from osm_diff_reviewer.processing.provider import OsmDiffReviewerProvider

ALGORITHM_ID = "osmdiffreviewer:match"


@pytest.fixture(scope="module")
def provider(qgis_app):
    registry = QgsApplication.processingRegistry()
    provider = OsmDiffReviewerProvider()
    registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


@pytest.fixture()
def profile_path(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {"attribute_mappings": [{"reference_field": "名称", "osm_tag": "name", "method": "similarity", "threshold": 0.8}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _run(m1_dir, profile_path, **extra):
    params = {
        "REFERENCE": str(m1_dir / "reference.geojson"),
        "REFERENCE_KEY": "ref_id",
        "OSM": str(m1_dir / "osm.geojson"),
        "PROFILE": str(profile_path),
        "OUTPUT": "memory:candidates",
        **extra,
    }
    result = processing.run(ALGORITHM_ID, params)
    layer = result["OUTPUT"]
    return layer if isinstance(layer, QgsVectorLayer) else QgsVectorLayer(layer)


def test_algorithm_is_registered(provider):
    assert QgsApplication.processingRegistry().algorithmById(ALGORITHM_ID) is not None


def test_algorithm_classifies_m1_fixture(provider, m1_dir, profile_path):
    layer = _run(m1_dir, profile_path)
    actual = {f["ref_key"]: f["classification"] for f in layer.getFeatures()}
    expected = {
        f["ref_id"]: f["expected"] for f in QgsVectorLayer(str(m1_dir / "reference.geojson")).getFeatures()
    }
    assert actual == expected


def test_output_has_candidate_fields_and_reference_crs(provider, m1_dir, profile_path):
    layer = _run(m1_dir, profile_path)
    names = set(layer.fields().names())
    assert {
        "ref_key",
        "osm_type",
        "osm_id",
        "osm_version",
        "classification",
        "distance_m",
        "shape_score",
        "attribute_score",
        "total_score",
        "alternatives",
        "attribute_details",
    } <= names
    assert layer.crs().authid() == "EPSG:4326"


def test_include_osm_only_overrides_profile(provider, m1_dir, profile_path):
    layer = _run(m1_dir, profile_path, INCLUDE_OSM_ONLY=True)
    osm_only = [f["osm_id"] for f in layer.getFeatures() if f["classification"] == "osm_only"]
    assert osm_only == [11]


def test_runs_without_profile_using_defaults(provider, m1_dir):
    params = {
        "REFERENCE": str(m1_dir / "reference.geojson"),
        "OSM": str(m1_dir / "osm.geojson"),
        "OUTPUT": "memory:candidates",
    }
    layer = processing.run(ALGORITHM_ID, params)["OUTPUT"]
    assert layer.featureCount() == 10


def test_broken_profile_is_reported_as_processing_error(provider, m1_dir, tmp_path):
    from qgis.core import QgsProcessingException

    broken = tmp_path / "broken.json"
    broken.write_text('{"attribute_mappings": [{"reference_field": "a", "osm_tag": "b", "method": "fuzzy"}]}')
    with pytest.raises(QgsProcessingException, match="fuzzy"):
        processing.run(
            ALGORITHM_ID,
            {
                "REFERENCE": str(m1_dir / "reference.geojson"),
                "OSM": str(m1_dir / "osm.geojson"),
                "PROFILE": str(broken),
                "OUTPUT": "memory:candidates",
            },
        )


def test_empty_reference_layer_is_reported_as_processing_error(provider, m1_dir):
    from qgis.core import QgsProcessingException

    empty = QgsVectorLayer("Point?crs=EPSG:4326", "empty", "memory")
    with pytest.raises(QgsProcessingException):
        processing.run(
            ALGORITHM_ID,
            {"REFERENCE": empty, "OSM": str(m1_dir / "osm.geojson"), "OUTPUT": "memory:candidates"},
        )
