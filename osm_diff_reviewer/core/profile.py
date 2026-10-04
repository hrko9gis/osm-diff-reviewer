"""Matching profile: thresholds per geometry kind and the attribute mapping table.

Stored as JSON so it can be shared and reused. Pure Python: no QGIS dependency.
Default values and their rationale are documented in docs/thresholds.md.
"""

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

PROFILE_VERSION = 1
GEOMETRY_KINDS = ("point", "polygon", "line")
COMPARISON_METHODS = ("exact", "normalized", "similarity")


class ProfileError(ValueError):
    """The profile is malformed; the message is meant for the user."""


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ProfileError(f"{name} must be a finite number")
    return number


@dataclass(frozen=True)
class Thresholds:
    search_radius_m: float
    max_distance_m: float  # points: distance; polygons: centroid distance (info only); lines: Hausdorff
    min_iou: float = 0.6  # polygons: IoU; lines: buffer coverage
    buffer_m: float = 5.0  # lines only: buffer width used to measure coverage

    def validate(self, kind: str) -> None:
        if self.search_radius_m <= 0 or self.max_distance_m < 0:
            raise ProfileError(f"{kind}: distances must be positive")
        if self.max_distance_m > self.search_radius_m:
            raise ProfileError(f"{kind}: max_distance_m must not exceed search_radius_m")
        if not 0 < self.min_iou <= 1:
            raise ProfileError(f"{kind}: min_iou must be in (0, 1]")
        if self.buffer_m <= 0:
            raise ProfileError(f"{kind}: buffer_m must be positive")


@dataclass(frozen=True)
class AttributeMapping:
    reference_field: str
    osm_tag: str
    method: str = "normalized"
    threshold: float = 0.8

    def validate(self) -> None:
        if not self.reference_field or not self.osm_tag:
            raise ProfileError("attribute mapping needs reference_field and osm_tag")
        if self.method not in COMPARISON_METHODS:
            raise ProfileError(f"unknown comparison method: {self.method!r}")
        if not 0 < self.threshold <= 1:
            raise ProfileError("attribute mapping threshold must be in (0, 1]")


DEFAULT_THRESHOLDS = {
    "point": Thresholds(search_radius_m=50.0, max_distance_m=15.0),
    "polygon": Thresholds(search_radius_m=30.0, max_distance_m=10.0, min_iou=0.6),
    "line": Thresholds(search_radius_m=20.0, max_distance_m=10.0, min_iou=0.6, buffer_m=5.0),
}


@dataclass(frozen=True)
class Profile:
    thresholds: tuple[tuple[str, Thresholds], ...] = field(default_factory=lambda: tuple(DEFAULT_THRESHOLDS.items()))
    attribute_mappings: tuple[AttributeMapping, ...] = ()
    reference_is_exhaustive: bool = False
    min_match_score: float = 0.4
    ambiguity_margin: float = 0.05

    def thresholds_for(self, kind: str) -> Thresholds:
        return dict(self.thresholds)[kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": PROFILE_VERSION,
            "reference_is_exhaustive": self.reference_is_exhaustive,
            "min_match_score": self.min_match_score,
            "ambiguity_margin": self.ambiguity_margin,
            "thresholds": {kind: vars(t).copy() for kind, t in self.thresholds},
            "attribute_mappings": [vars(m).copy() for m in self.attribute_mappings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        try:
            return _profile_from_dict(data)
        except (TypeError, ValueError, AttributeError) as error:
            if isinstance(error, ProfileError):
                raise
            raise ProfileError(f"invalid profile: {error}") from error


def _profile_from_dict(data: dict[str, Any]) -> Profile:
    version = data.get("version", PROFILE_VERSION)
    if version != PROFILE_VERSION:
        raise ProfileError(f"unsupported profile version: {version}")

    overrides = data.get("thresholds", {})
    unknown = set(overrides) - set(GEOMETRY_KINDS)
    if unknown:
        raise ProfileError(f"unsupported geometry kind(s): {', '.join(sorted(unknown))}")
    thresholds = []
    for kind, default in DEFAULT_THRESHOLDS.items():
        values = {key: _finite(value, f"{kind}.{key}") for key, value in overrides.get(kind, {}).items()}
        merged = replace(default, **values)
        merged.validate(kind)
        thresholds.append((kind, merged))

    mappings = []
    for raw in data.get("attribute_mappings", []):
        mapping = AttributeMapping(
            reference_field=raw.get("reference_field", ""),
            osm_tag=raw.get("osm_tag", ""),
            method=raw.get("method", "normalized"),
            threshold=_finite(raw.get("threshold", 0.8), "threshold"),
        )
        mapping.validate()
        mappings.append(mapping)

    exhaustive = data.get("reference_is_exhaustive", False)
    if not isinstance(exhaustive, bool):
        raise ProfileError("reference_is_exhaustive must be true or false")
    profile = Profile(
        thresholds=tuple(thresholds),
        attribute_mappings=tuple(mappings),
        reference_is_exhaustive=exhaustive,
        min_match_score=_finite(data.get("min_match_score", 0.4), "min_match_score"),
        ambiguity_margin=_finite(data.get("ambiguity_margin", 0.05), "ambiguity_margin"),
    )
    if not 0 <= profile.min_match_score <= 1 or not 0 <= profile.ambiguity_margin <= 1:
        raise ProfileError("min_match_score and ambiguity_margin must be in [0, 1]")
    return profile


def load_profile(path: str | Path) -> Profile:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot read profile {path}: {error}") from error
    if not isinstance(data, dict):
        raise ProfileError("profile must be a JSON object")
    return Profile.from_dict(data)


def save_profile(profile: Profile, path: str | Path) -> None:
    Path(path).write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
