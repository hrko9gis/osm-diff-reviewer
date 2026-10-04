from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsVectorLayer
from qgis.PyQt.QtCore import QMetaType

from osm_diff_reviewer.core.features import (
    osm_features_from_layer,
    parse_other_tags,
    reference_features_from_layer,
    reference_hash_key,
)


def _layer(geometry_type, fields, rows):
    layer = QgsVectorLayer(f"{geometry_type}?crs=EPSG:4326", "t", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, QMetaType.Type.QString) for name in fields])
    layer.updateFields()
    features = []
    for wkt, values in rows:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttributes(values)
        features.append(feature)
    provider.addFeatures(features)
    return layer


def test_reference_key_uses_id_field(qgis_app):
    layer = _layer("Point", ["id", "名称"], [("POINT(139.7 35.68)", ["A-1", "図書館"])])
    (feature,) = reference_features_from_layer(layer, "id")
    assert feature.key == "A-1"
    assert feature.attributes == {"id": "A-1", "名称": "図書館"}


def test_reference_hash_key_is_stable_and_changes_with_geometry(qgis_app):
    attributes = {"名称": "図書館"}
    geometry = QgsGeometry.fromWkt("POINT(139.7 35.68)")
    moved = QgsGeometry.fromWkt("POINT(139.7001 35.68)")
    assert reference_hash_key(geometry, attributes) == reference_hash_key(QgsGeometry(geometry), dict(attributes))
    assert reference_hash_key(geometry, attributes) != reference_hash_key(moved, attributes)
    assert reference_hash_key(geometry, attributes) != reference_hash_key(geometry, {"名称": "公園"})


def test_reference_without_key_field_gets_hash_key(qgis_app):
    layer = _layer("Point", ["名称"], [("POINT(139.7 35.68)", ["図書館"])])
    (feature,) = reference_features_from_layer(layer, None)
    assert feature.key.startswith("hash:")


def test_parse_other_tags_reads_hstore_string():
    raw = '"amenity"=>"library","name:en"=>"Central \\"Library\\"","opening_hours"=>"Mo-Fr 09:00-17:00"'
    assert parse_other_tags(raw) == {
        "amenity": "library",
        "name:en": 'Central "Library"',
        "opening_hours": "Mo-Fr 09:00-17:00",
    }


def test_parse_other_tags_handles_empty():
    assert parse_other_tags(None) == {}
    assert parse_other_tags("") == {}


def test_osm_features_read_type_id_version_and_tags(qgis_app):
    layer = _layer(
        "Point",
        ["osm_type", "osm_id", "osm_version", "name", "other_tags"],
        [("POINT(139.7 35.68)", ["node", "42", "7", "図書館", '"amenity"=>"library"'])],
    )
    (feature,) = osm_features_from_layer(layer)
    assert (feature.osm_type, feature.osm_id, feature.version) == ("node", 42, 7)
    assert feature.tags == {"name": "図書館", "amenity": "library"}


def test_osm_type_is_inferred_and_version_may_be_missing(qgis_app):
    layer = _layer("Polygon", ["osm_id", "name"], [("POLYGON((0 0,1 0,1 1,0 0))", ["9", "x"])])
    (feature,) = osm_features_from_layer(layer)
    assert (feature.osm_type, feature.osm_id, feature.version) == ("way", 9, None)


def test_osm_features_without_valid_id_are_skipped(qgis_app):
    layer = _layer("Point", ["osm_id"], [("POINT(0 0)", [None]), ("POINT(1 1)", ["abc"])])
    assert osm_features_from_layer(layer) == []


def test_identical_unkeyed_references_get_distinct_hash_keys(qgis_app):
    layer = _layer("Point", ["名称"], [("POINT(139.7 35.68)", ["図書館"]), ("POINT(139.7 35.68)", ["図書館"])])
    first, second = reference_features_from_layer(layer, None)
    assert first.key != second.key


def test_date_attributes_are_iso_text(qgis_app):
    from qgis.PyQt.QtCore import QDate

    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=opened:date", "t", "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromWkt("POINT(0 0)"))
    feature.setAttributes([QDate(2020, 1, 2)])
    layer.dataProvider().addFeatures([feature])
    (reference,) = reference_features_from_layer(layer, None)
    assert reference.attributes == {"opened": "2020-01-02"}
