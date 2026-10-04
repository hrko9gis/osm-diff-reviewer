"""Line matching (spec 8): buffer coverage, Hausdorff distance, split segmentation → ambiguous."""

import pytest
from qgis.core import QgsGeometry

from osm_diff_reviewer.core import matching
from osm_diff_reviewer.core.features import OsmFeature, ReferenceFeature
from osm_diff_reviewer.core.profile import AttributeMapping, Profile

NAME = (AttributeMapping("名称", "name", "similarity", 0.8),)
PROFILE = Profile(attribute_mappings=NAME)


def _ref(key, wkt, name="通り"):
    return ReferenceFeature(key, QgsGeometry.fromWkt(wkt), {"名称": name})


def _osm(osm_id, wkt, name="通り"):
    return OsmFeature("way", osm_id, 1, QgsGeometry.fromWkt(wkt), {"name": name})


def _by_ref(result):
    return {c.ref_key: c for c in result.candidates if c.ref_key is not None}


def test_parallel_line_close_by_matches(qgis_app):
    result = matching.match([_ref("A", "LINESTRING(0 0, 100 0)")], [_osm(1, "LINESTRING(0 2, 100 2)")], PROFILE)
    (candidate,) = result.candidates
    assert candidate.classification == matching.MATCH
    assert candidate.distance_m == pytest.approx(2.0, abs=0.01)  # Hausdorff
    assert candidate.shape_score == pytest.approx(1.0)


def test_line_outside_buffer_is_geometry_diff(qgis_app):
    result = matching.match([_ref("A", "LINESTRING(0 0, 100 0)")], [_osm(1, "LINESTRING(0 12, 100 12)")], PROFILE)
    assert result.candidates[0].classification == matching.GEOMETRY_DIFF


def test_line_with_same_shape_but_different_name_is_attribute_diff(qgis_app):
    result = matching.match([_ref("A", "LINESTRING(0 0, 100 0)")], [_osm(1, "LINESTRING(0 1, 100 1)", "別の道")], PROFILE)
    assert result.candidates[0].classification == matching.ATTRIBUTE_DIFF


def test_osm_split_into_segments_is_ambiguous(qgis_app):
    references = [_ref("A", "LINESTRING(0 0, 100 0)")]
    osm = [_osm(1, "LINESTRING(0 1, 50 1)"), _osm(2, "LINESTRING(50 1, 100 1)")]
    (candidate,) = matching.match(references, osm, PROFILE).candidates
    assert candidate.classification == matching.AMBIGUOUS
    assert {candidate.osm_id, *(int(a.split("/")[1]) for a in candidate.alternatives)} == {1, 2}


def test_osm_split_unevenly_is_still_ambiguous(qgis_app):
    references = [_ref("A", "LINESTRING(0 0, 100 0)")]
    osm = [_osm(1, "LINESTRING(0 1, 30 1)"), _osm(2, "LINESTRING(30 1, 100 1)")]
    (candidate,) = matching.match(references, osm, PROFILE).candidates
    assert candidate.classification == matching.AMBIGUOUS


def test_reference_split_into_segments_is_ambiguous(qgis_app):
    references = [_ref("A", "LINESTRING(0 0, 50 0)"), _ref("B", "LINESTRING(50 0, 100 0)")]
    osm = [_osm(1, "LINESTRING(0 1, 100 1)")]
    classes = {c.ref_key: c.classification for c in matching.match(references, osm, PROFILE).candidates}
    assert classes == {"A": matching.AMBIGUOUS, "B": matching.AMBIGUOUS}


def test_lines_and_points_do_not_pair(qgis_app):
    references = [_ref("L", "LINESTRING(0 0, 100 0)"), _ref("P", "POINT(50 0)")]
    osm = [OsmFeature("node", 5, 1, QgsGeometry.fromWkt("POINT(50 1)"), {"name": "通り"}), _osm(6, "LINESTRING(0 300, 100 300)")]
    classes = {c.ref_key: c.classification for c in matching.match(references, osm, PROFILE).candidates}
    assert classes == {"L": matching.MISSING, "P": matching.MATCH}


def test_unknown_geometry_kinds_are_still_skipped(qgis_app):
    collection = ReferenceFeature("G", QgsGeometry.fromWkt("GEOMETRYCOLLECTION(POINT(0 0), LINESTRING(0 0, 1 1))"), {})
    result = matching.match([collection], [], Profile())
    assert result.skipped_reference_keys == ("G",)


def test_short_neighbouring_segments_do_not_spoil_an_exact_match(qgis_app):
    references = [_ref("A", "LINESTRING(0 0, 100 0)")]
    osm = [_osm(1, "LINESTRING(0 0, 100 0)"), _osm(2, "LINESTRING(-6 0, 0 0)"), _osm(3, "LINESTRING(100 0, 106 0)")]
    (candidate,) = [c for c in matching.match(references, osm, PROFILE).candidates if c.ref_key == "A"]
    assert (candidate.classification, candidate.osm_id) == (matching.MATCH, 1)
