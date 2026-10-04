import json

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)

from osm_diff_reviewer.core import matching
from osm_diff_reviewer.core.features import (
    OsmFeature,
    ReferenceFeature,
    osm_features_from_layer,
    reference_features_from_layer,
)
from osm_diff_reviewer.core.profile import AttributeMapping, Profile

WORKING_CRS = QgsCoordinateReferenceSystem("EPSG:32654")
NAME_MAPPING = (AttributeMapping("名称", "name", "similarity", 0.8),)


def _load(path):
    layer = QgsVectorLayer(str(path), path.stem, "ogr")
    assert layer.isValid(), path
    transform = QgsCoordinateTransform(layer.crs(), WORKING_CRS, QgsProject.instance())
    return layer, transform


@pytest.fixture(scope="module")
def m1_features(qgis_app, m1_dir):
    ref_layer, ref_transform = _load(m1_dir / "reference.geojson")
    osm_layer, osm_transform = _load(m1_dir / "osm.geojson")
    references = reference_features_from_layer(ref_layer, "ref_id", ref_transform)
    osm_features = osm_features_from_layer(osm_layer, transform=osm_transform)
    expected = {f["ref_id"]: f["expected"] for f in ref_layer.getFeatures()}
    return references, osm_features, expected


def _by_ref(result):
    return {c.ref_key: c for c in result.candidates if c.ref_key is not None}


def test_m1_fixture_is_classified_as_expected(m1_features):
    references, osm_features, expected = m1_features
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    actual = {key: c.classification for key, c in _by_ref(result).items()}
    assert actual == expected


def test_matched_pairs_point_to_the_right_osm_objects(m1_features):
    references, osm_features, _ = m1_features
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    pairs = {key: (c.osm_type, c.osm_id) for key, c in _by_ref(result).items() if c.osm_id is not None}
    assert pairs["R1"] == ("node", 1)
    assert pairs["R5"] == ("node", 5)
    assert pairs["R7"] == ("way", 7)
    assert pairs["R8"] == ("way", 8)
    assert pairs["R9"] == ("way", 9)


def test_scores_are_recorded(m1_features):
    references, osm_features, _ = m1_features
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    by_ref = _by_ref(result)
    assert by_ref["R1"].distance_m == pytest.approx(5.0, abs=0.2)
    assert by_ref["R1"].attribute_score == 1.0
    assert by_ref["R8"].shape_score == pytest.approx(19 / 21, abs=0.02)
    assert by_ref["R4"].attribute_score < 0.5
    assert by_ref["R2"].osm_id is None and by_ref["R2"].total_score is None
    details = json.loads(by_ref["R4"].attribute_details)
    assert details[0]["reference_field"] == "名称" and details[0]["ok"] is False


def test_ambiguous_candidate_lists_alternatives(m1_features):
    references, osm_features, _ = m1_features
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    ambiguous = _by_ref(result)["R6"]
    assert {ambiguous.osm_id, *[int(a.split("/")[1]) for a in ambiguous.alternatives]} == {61, 62}


def test_osm_only_is_off_by_default(m1_features):
    references, osm_features, _ = m1_features
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    assert not [c for c in result.candidates if c.classification == matching.OSM_ONLY]


def test_osm_only_reported_when_reference_is_exhaustive(m1_features):
    references, osm_features, _ = m1_features
    profile = Profile(attribute_mappings=NAME_MAPPING, reference_is_exhaustive=True)
    result = matching.match(references, osm_features, profile)
    osm_only = [(c.osm_type, c.osm_id) for c in result.candidates if c.classification == matching.OSM_ONLY]
    # node/62 is an alternative of the ambiguous R6, so it must not be reported as OSM-only.
    assert osm_only == [("node", 11)]


def _ref(key, wkt, name):
    return ReferenceFeature(key, QgsGeometry.fromWkt(wkt), {"名称": name})


def _osm(osm_id, wkt, name):
    return OsmFeature("node", osm_id, 1, QgsGeometry.fromWkt(wkt), {"name": name})


def test_two_references_competing_for_one_osm_object_never_both_match(qgis_app):
    references = [_ref("A", "POINT(0 0)", "中央図書館"), _ref("B", "POINT(20 0)", "中央図書館分館")]
    osm_features = [_osm(1, "POINT(1 0)", "中央図書館")]
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    by_ref = _by_ref(result)
    assert by_ref["A"].classification == matching.MATCH
    assert by_ref["B"].classification == matching.AMBIGUOUS


def test_near_tie_between_two_references_makes_both_ambiguous(qgis_app):
    references = [_ref("A", "POINT(-5 0)", "公園"), _ref("B", "POINT(5 0)", "公園")]
    osm_features = [_osm(1, "POINT(0 0)", "公園")]
    result = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING))
    assert {c.classification for c in result.candidates} == {matching.AMBIGUOUS}


def test_without_attribute_mappings_matching_is_spatial_only(qgis_app):
    references = [_ref("A", "POINT(0 0)", "x")]
    osm_features = [_osm(1, "POINT(3 4)", "y")]
    (candidate,) = matching.match(references, osm_features, Profile()).candidates
    assert candidate.classification == matching.MATCH
    assert candidate.attribute_score is None
    assert candidate.total_score == candidate.shape_score


def test_line_references_are_skipped_and_reported(qgis_app):
    references = [ReferenceFeature("L", QgsGeometry.fromWkt("LINESTRING(0 0, 10 0)"), {})]
    result = matching.match(references, [], Profile())
    assert result.candidates == ()
    assert result.skipped_reference_keys == ("L",)


def test_reference_polygon_against_osm_node_inside(qgis_app):
    references = [_ref("A", "POLYGON((0 0, 20 0, 20 20, 0 20, 0 0))", "倉庫")]
    osm_features = [_osm(1, "POINT(10 10)", "倉庫")]
    (candidate,) = matching.match(references, osm_features, Profile(attribute_mappings=NAME_MAPPING)).candidates
    assert candidate.classification == matching.MATCH
    assert candidate.distance_m == 0.0


@pytest.mark.parametrize(
    ("method", "ref_value", "osm_value", "expected_score", "expected_ok"),
    [
        ("exact", "Tokyo", "Tokyo", 1.0, True),
        ("exact", "Tokyo", "tokyo", 0.0, False),
        ("normalized", "株式会社ﾃｽﾄ", "テスト", 1.0, True),
        ("normalized", "テスト", "テスト2", 0.0, False),
        ("similarity", "テスト商店", "テスト商会", 0.8, True),
        ("normalized", "", "テスト", 0.0, False),
    ],
)
def test_compare_attributes_methods(qgis_app, method, ref_value, osm_value, expected_score, expected_ok):
    profile_mapping = (AttributeMapping("名称", "name", method, 0.8),)
    ref = _ref("A", "POINT(0 0)", ref_value)
    osm = _osm(1, "POINT(0 0)", osm_value)
    score, ok, details = matching.compare_attributes(profile_mapping, ref, osm)
    assert score == pytest.approx(expected_score)
    assert ok is expected_ok
    assert len(details) == 1


def test_compare_attributes_skips_mappings_empty_on_both_sides(qgis_app):
    mappings = (AttributeMapping("名称", "name"), AttributeMapping("電話", "phone"))
    score, ok, details = matching.compare_attributes(mappings, _ref("A", "POINT(0 0)", "x"), _osm(1, "POINT(0 0)", "x"))
    assert (score, ok, len(details)) == (1.0, True, 1)


def test_duplicate_reference_keys_do_not_overwrite_each_other(qgis_app):
    references = [_ref("1", "POINT(0 0)", "公園"), _ref("1", "POINT(1000 0)", "公園")]
    osm_features = [_osm(1, "POINT(1 0)", "公園")]
    profile = Profile(attribute_mappings=NAME_MAPPING, reference_is_exhaustive=True)
    classes = sorted(c.classification for c in matching.match(references, osm_features, profile).candidates)
    assert classes == [matching.MATCH, matching.MISSING]


def test_osm_objects_of_an_ambiguous_reference_are_not_given_to_weaker_references(qgis_app):
    # B ties between node/1 and node/2; C reaches only node/1 (node/2 is outside its 30 m radius).
    references = [_ref("B", "POINT(0 0)", "公園"), _ref("C", "POINT(29.5 0)", "公園")]
    osm_features = [_osm(1, "POINT(1 0)", "公園"), _osm(2, "POINT(-1 0)", "公園")]
    profile = Profile.from_dict(
        {
            "thresholds": {"point": {"search_radius_m": 30}},
            "attribute_mappings": [{"reference_field": "名称", "osm_tag": "name", "method": "similarity"}],
        }
    )
    by_ref = _by_ref(matching.match(references, osm_features, profile))
    assert by_ref["B"].classification == matching.AMBIGUOUS
    assert by_ref["C"].classification == matching.AMBIGUOUS
