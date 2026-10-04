import json

import pytest

from osm_diff_reviewer.core.profile import (
    AttributeMapping,
    Profile,
    ProfileError,
    load_profile,
    save_profile,
)


def test_default_profile_has_point_and_polygon_thresholds():
    profile = Profile()
    assert profile.thresholds_for("point").search_radius_m > profile.thresholds_for("point").max_distance_m
    assert 0 < profile.thresholds_for("polygon").min_iou < 1
    assert profile.reference_is_exhaustive is False


def test_profile_round_trips_through_json(tmp_path):
    profile = Profile(
        reference_is_exhaustive=True,
        attribute_mappings=(AttributeMapping("名称", "name", "similarity", 0.85),),
    )
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    assert load_profile(path) == profile
    assert "名称" in path.read_text(encoding="utf-8")


def test_missing_keys_fall_back_to_defaults():
    profile = Profile.from_dict({"attribute_mappings": [{"reference_field": "名称", "osm_tag": "name"}]})
    assert profile.thresholds_for("point") == Profile().thresholds_for("point")
    assert profile.attribute_mappings[0].method == "normalized"


def test_partial_threshold_override_keeps_other_defaults():
    profile = Profile.from_dict({"thresholds": {"point": {"search_radius_m": 80}}})
    assert profile.thresholds_for("point").search_radius_m == 80
    assert profile.thresholds_for("point").max_distance_m == Profile().thresholds_for("point").max_distance_m


@pytest.mark.parametrize(
    "data",
    [
        {"attribute_mappings": [{"reference_field": "a", "osm_tag": "b", "method": "fuzzy"}]},
        {"attribute_mappings": [{"reference_field": "a"}]},
        {"thresholds": {"point": {"search_radius_m": -1}}},
        {"thresholds": {"polygon": {"min_iou": 1.5}}},
        {"thresholds": {"point": {"search_radius_m": 10, "max_distance_m": 20}}},
        {"thresholds": {"line": {}}},
        {"ambiguity_margin": "big"},
        {"version": 99},
    ],
)
def test_invalid_profiles_are_rejected(data):
    with pytest.raises(ProfileError):
        Profile.from_dict(data)


def test_load_profile_reports_broken_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(path)


def test_to_dict_is_json_serializable():
    json.dumps(Profile().to_dict())


@pytest.mark.parametrize(
    "data",
    [
        {"thresholds": {"point": {"search_radius_m": float("nan")}}},
        {"thresholds": {"point": {"search_radius_m": float("inf")}}},
        {"thresholds": {"point": {"max_distance_m": float("nan")}}},
        {"thresholds": {"polygon": {"min_iou": float("nan")}}},
        {"min_match_score": float("nan")},
        {"attribute_mappings": [{"reference_field": "a", "osm_tag": "b", "threshold": float("nan")}]},
        {"reference_is_exhaustive": "false"},
    ],
)
def test_non_finite_and_mistyped_values_are_rejected(data):
    with pytest.raises(ProfileError):
        Profile.from_dict(data)
