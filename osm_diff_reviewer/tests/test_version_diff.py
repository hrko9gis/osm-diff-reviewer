import json
import sys
from pathlib import Path

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)

from osm_diff_reviewer.core import matching, version_diff
from osm_diff_reviewer.core.features import ReferenceFeature, osm_features_from_layer, reference_features_from_layer
from osm_diff_reviewer.core.profile import AttributeMapping, Profile

sys.path.insert(0, str(Path(__file__).parent / "data"))
from make_m5_data import EXPECTED  # noqa: E402

WORKING_CRS = QgsCoordinateReferenceSystem("EPSG:32654")
PROFILE = Profile(attribute_mappings=(AttributeMapping("名称", "name", "similarity", 0.8),))


def _ref(key, wkt="POINT(0 0)", **attributes):
    return ReferenceFeature(key, QgsGeometry.fromWkt(wkt), attributes)


def _load(path, reader, **kwargs):
    layer = QgsVectorLayer(str(path), path.stem, "ogr")
    transform = QgsCoordinateTransform(layer.crs(), WORKING_CRS, QgsProject.instance())
    return reader(layer, transform=transform, **kwargs)


# ----- version comparison ----------------------------------------------------------------


def test_diff_versions_finds_added_removed_and_changed(qgis_app):
    old = [_ref("A", 名称="a"), _ref("B", 名称="b"), _ref("C", 名称="c")]
    new = [_ref("A", 名称="a"), _ref("C", 名称="c2"), _ref("D", 名称="d")]
    changes = {c.key: c for c in version_diff.diff_versions(old, new)}
    assert {k: c.kind for k, c in changes.items()} == {
        "B": version_diff.REMOVED, "C": version_diff.CHANGED, "D": version_diff.ADDED
    }
    assert changes["C"].changed_fields == ("名称",) and changes["C"].geometry_changed is False


def test_geometry_change_is_detected_with_tolerance(qgis_app):
    old = [_ref("A", "POINT(0 0)"), _ref("B", "POINT(0 0)")]
    new = [_ref("A", "POINT(0.001 0)"), _ref("B", "POINT(3 0)")]
    changes = version_diff.diff_versions(old, new)
    assert [(c.key, c.geometry_changed) for c in changes] == [("B", True)]


def test_fields_present_in_one_version_only_are_ignored(qgis_app):
    old = [_ref("A", 名称="a")]
    new = [_ref("A", 名称="a", 新しい列="x")]
    assert version_diff.diff_versions(old, new) == []


def test_null_and_missing_values_are_equal(qgis_app):
    old = [_ref("A", 名称="a", 備考=None)]
    new = [_ref("A", 名称="a", 備考=None)]
    assert version_diff.diff_versions(old, new) == []


def test_duplicate_keys_are_rejected(qgis_app):
    with pytest.raises(version_diff.VersionDiffError, match="A"):
        version_diff.diff_versions([_ref("A"), _ref("A")], [_ref("A")])


def test_empty_id_values_are_reported_as_such(qgis_app):
    with pytest.raises(version_diff.VersionDiffError, match="empty ID"):
        version_diff.diff_versions([_ref("A"), _ref("hash:abc")], [_ref("A")])


# ----- evaluation against OSM ---------------------------------------------------------------


@pytest.fixture(scope="module")
def m5(qgis_app):
    base = Path(__file__).parent / "data" / "m5"
    old = _load(base / "reference_old.geojson", reference_features_from_layer, key_field="id")
    new = _load(base / "reference_new.geojson", reference_features_from_layer, key_field="id")
    osm = _load(base / "osm.geojson", osm_features_from_layer)
    return old, new, osm


def test_m5_fixture_verdicts(m5):
    old, new, osm = m5
    candidates = version_diff.evaluate(old, new, osm, PROFILE).candidates
    assert {c.ref_key: (c.change_kind, c.verdict) for c in candidates} == EXPECTED


def test_changed_candidate_points_at_osm_object_and_lists_fields(m5):
    old, new, osm = m5
    by_key = {c.ref_key: c for c in version_diff.evaluate(old, new, osm, PROFILE).candidates}
    assert (by_key["V6"].osm_type, by_key["V6"].osm_id) == ("node", 6)
    assert json.loads(by_key["V6"].change_detail) == {"fields": ["名称"], "geometry": False}
    assert by_key["V4"].osm_id == 4  # removed: the OSM object that is still there
    assert by_key["V3"].classification == matching.MISSING


def test_unchanged_features_still_compete_for_osm_objects(qgis_app):
    # An added feature next to an unchanged one must not take the unchanged one's OSM object.
    old = [_ref("A", "POINT(0 0)", 名称="公園")]
    new = [_ref("A", "POINT(0 0)", 名称="公園"), _ref("B", "POINT(8 0)", 名称="公園")]
    osm = [matching.OsmFeature("node", 1, 1, QgsGeometry.fromWkt("POINT(1 0)"), {"name": "公園"})]
    (candidate,) = version_diff.evaluate(old, new, osm, PROFILE).candidates
    assert candidate.ref_key == "B" and candidate.verdict != version_diff.IN_OSM


def test_reordered_geopackage_rows_are_not_changes(qgis_app, tmp_path):
    from qgis.core import QgsFeature, QgsVectorFileWriter, QgsVectorLayer

    def gpkg(name, rows):
        memory = QgsVectorLayer("Point?crs=EPSG:32654&field=id:string&field=名称:string", name, "memory")
        features = []
        for key, label, x in rows:
            feature = QgsFeature(memory.fields())
            feature.setAttributes([key, label])
            feature.setGeometry(QgsGeometry.fromWkt(f"POINT({x} 0)"))
            features.append(feature)
        memory.dataProvider().addFeatures(features)
        path = str(tmp_path / f"{name}.gpkg")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        QgsVectorFileWriter.writeAsVectorFormatV3(memory, path, QgsProject.instance().transformContext(), options)
        return QgsVectorLayer(path, name, "ogr")

    old = reference_features_from_layer(gpkg("old", [("a", "A", 0), ("b", "B", 100)]), "id")
    new = reference_features_from_layer(gpkg("new", [("b", "B", 100), ("a", "A", 0)]), "id")
    assert version_diff.diff_versions(old, new) == []


def test_changed_feature_does_not_claim_an_osm_object_taken_by_another(qgis_app):
    # K moved 200 m away; a new L now sits where K was, next to way/1.
    old = [_ref("K", "POINT(0 0)", 名称="公園")]
    new = [_ref("K", "POINT(200 0)", 名称="公園"), _ref("L", "POINT(1 0)", 名称="公園")]
    osm = [matching.OsmFeature("node", 1, 1, QgsGeometry.fromWkt("POINT(0 1)"), {"name": "公園"})]
    by_key = {c.ref_key: c for c in version_diff.evaluate(old, new, osm, PROFILE).candidates}
    assert by_key["L"].verdict == version_diff.IN_OSM
    assert by_key["K"].verdict == version_diff.VERDICT_AMBIGUOUS


def test_unsupported_geometry_changes_are_reported_as_skipped(qgis_app):
    collection = "GEOMETRYCOLLECTION(POINT(0 0), LINESTRING(0 0, 1 1))"
    result = version_diff.evaluate([], [_ref("G", collection, 名称="x")], [], PROFILE)
    assert result.candidates == () and result.skipped_keys == ("G",)
