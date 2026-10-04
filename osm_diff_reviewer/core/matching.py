"""Candidate search, scoring, one-to-one assignment and classification.

All geometries must already be in a projected CRS measured in metres.
No GUI dependency; this module is exercised directly by the unit tests.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from qgis.core import Qgis, QgsGeometry, QgsSpatialIndex

from .features import OsmFeature, ReferenceFeature
from .normalize import name_similarity, normalize_name
from .profile import AttributeMapping, Profile, Thresholds

MATCH = "match"
MISSING = "missing"
GEOMETRY_DIFF = "geometry_diff"
ATTRIBUTE_DIFF = "attribute_diff"
AMBIGUOUS = "ambiguous"
OSM_ONLY = "osm_only"
CLASSIFICATIONS = (MATCH, MISSING, GEOMETRY_DIFF, ATTRIBUTE_DIFF, AMBIGUOUS, OSM_ONLY)

_GEOMETRY_KINDS = {Qgis.GeometryType.Point: "point", Qgis.GeometryType.Polygon: "polygon"}


@dataclass(frozen=True)
class Candidate:
    ref_key: str | None
    osm_type: str | None
    osm_id: int | None
    osm_version: int | None
    classification: str
    distance_m: float | None
    shape_score: float | None
    attribute_score: float | None
    total_score: float | None
    geometry: QgsGeometry
    alternatives: tuple[str, ...] = ()
    attribute_details: str = "[]"


@dataclass(frozen=True)
class MatchResult:
    candidates: tuple[Candidate, ...]
    skipped_reference_keys: tuple[str, ...]


@dataclass(frozen=True)
class _Pair:
    ref_index: int
    ref: ReferenceFeature
    osm: OsmFeature
    distance_m: float
    shape_score: float
    shape_ok: bool
    attribute_score: float | None
    attribute_ok: bool
    attribute_details: tuple[dict, ...]
    total: float


def geometry_kind(geometry: QgsGeometry) -> str | None:
    """'point' or 'polygon'; None for kinds not matched yet (lines arrive in M5)."""
    return _GEOMETRY_KINDS.get(geometry.type())


def _compare_value(mapping: AttributeMapping, ref_value: object, osm_value: object) -> dict | None:
    ref_text = "" if ref_value is None else str(ref_value).strip()
    osm_text = "" if osm_value is None else str(osm_value).strip()
    if not ref_text and not osm_text:
        return None
    if mapping.method == "exact":
        score = 1.0 if ref_text == osm_text else 0.0
    elif mapping.method == "normalized":
        score = 1.0 if ref_text and normalize_name(ref_text) == normalize_name(osm_text) else 0.0
    else:
        score = name_similarity(ref_text, osm_text)
    ok = score >= mapping.threshold if mapping.method == "similarity" else score == 1.0
    return {
        "reference_field": mapping.reference_field,
        "osm_tag": mapping.osm_tag,
        "reference_value": ref_text,
        "osm_value": osm_text,
        "score": round(score, 4),
        "ok": ok,
    }


def compare_attributes(
    mappings: Sequence[AttributeMapping], ref: ReferenceFeature, osm: OsmFeature
) -> tuple[float | None, bool, tuple[dict, ...]]:
    """Mean score, whether every compared mapping passed, and per-mapping details."""
    details = tuple(
        d
        for m in mappings
        if (d := _compare_value(m, ref.attributes.get(m.reference_field), osm.tags.get(m.osm_tag))) is not None
    )
    if not details:
        return None, True, ()
    score = sum(d["score"] for d in details) / len(details)
    return score, all(d["ok"] for d in details), details


def _shape(ref: ReferenceFeature, osm: OsmFeature, thresholds: Thresholds) -> tuple[float, float, bool]:
    """Distance, shape score in [0, 1] and whether the shape is within thresholds."""
    if geometry_kind(ref.geometry) == "polygon" and geometry_kind(osm.geometry) == "polygon":
        union_area = ref.geometry.combine(osm.geometry).area()
        iou = ref.geometry.intersection(osm.geometry).area() / union_area if union_area > 0 else 0.0
        distance = ref.geometry.centroid().distance(osm.geometry.centroid())
        return distance, iou, iou >= thresholds.min_iou
    distance = ref.geometry.distance(osm.geometry)
    score = max(0.0, 1.0 - distance / thresholds.search_radius_m)
    return distance, score, distance <= thresholds.max_distance_m


def score_pair(ref_index: int, ref: ReferenceFeature, osm: OsmFeature, profile: Profile) -> _Pair:
    thresholds = profile.thresholds_for(geometry_kind(ref.geometry))
    distance, shape_score, shape_ok = _shape(ref, osm, thresholds)
    attribute_score, attribute_ok, details = compare_attributes(profile.attribute_mappings, ref, osm)
    total = shape_score if attribute_score is None else (shape_score + attribute_score) / 2
    return _Pair(ref_index, ref, osm, distance, shape_score, shape_ok, attribute_score, attribute_ok, details, total)


def _candidate_pairs(
    references: Sequence[ReferenceFeature], osm_features: Sequence[OsmFeature], profile: Profile
) -> list[list[_Pair]]:
    """Valid pairs per reference position, best first (keys need not be unique)."""
    index = QgsSpatialIndex()
    for position, feature in enumerate(osm_features):
        index.addFeature(position, feature.geometry.boundingBox())
    pairs_by_ref = []
    for ref_index, ref in enumerate(references):
        radius = profile.thresholds_for(geometry_kind(ref.geometry)).search_radius_m
        search_box = ref.geometry.boundingBox().buffered(radius)
        nearby = (osm_features[i] for i in index.intersects(search_box))
        pairs = [
            score_pair(ref_index, ref, osm, profile) for osm in nearby if ref.geometry.distance(osm.geometry) <= radius
        ]
        valid = sorted((p for p in pairs if p.total >= profile.min_match_score), key=lambda p: -p.total)
        pairs_by_ref.append(valid)
    return pairs_by_ref


def _assign(pairs_by_ref: list[list[_Pair]], margin: float) -> tuple[dict[int, _Pair], set[int]]:
    """Greedy one-to-one assignment by score; near ties and lost contests become ambiguous."""
    ambiguous = {
        index for index, pairs in enumerate(pairs_by_ref) if len(pairs) >= 2 and pairs[0].total - pairs[1].total < margin
    }
    # OSM objects an ambiguous reference might be paired with stay reserved for it,
    # so that a weaker reference cannot claim them as a confident match.
    holder: dict[str, _Pair] = {}
    for index in ambiguous:
        best = pairs_by_ref[index][0].total
        for pair in pairs_by_ref[index]:
            reserved = holder.get(pair.osm.ref)
            if best - pair.total < margin and (reserved is None or pair.total > reserved.total):
                holder[pair.osm.ref] = pair
    ordered = sorted(
        (p for index, pairs in enumerate(pairs_by_ref) if index not in ambiguous for p in pairs),
        key=lambda p: -p.total,
    )
    assigned: dict[int, _Pair] = {}
    for pair in ordered:
        if pair.ref_index in assigned or pair.ref_index in ambiguous:
            continue
        current = holder.get(pair.osm.ref)
        if current is None:
            holder[pair.osm.ref] = pair
            assigned[pair.ref_index] = pair
        elif current.total - pair.total < margin:
            ambiguous.add(pair.ref_index)
            if assigned.pop(current.ref_index, None) is not None:
                ambiguous.add(current.ref_index)
    # A reference whose every plausible partner went to someone else is not safely "missing".
    ambiguous |= {index for index, pairs in enumerate(pairs_by_ref) if pairs and index not in assigned}
    return assigned, ambiguous


def _classify(pair: _Pair) -> str:
    if not pair.shape_ok:
        return GEOMETRY_DIFF
    if not pair.attribute_ok:
        return ATTRIBUTE_DIFF
    return MATCH


def _pair_candidate(pair: _Pair, classification: str, alternatives: tuple[str, ...] = ()) -> Candidate:
    return Candidate(
        ref_key=pair.ref.key,
        osm_type=pair.osm.osm_type,
        osm_id=pair.osm.osm_id,
        osm_version=pair.osm.version,
        classification=classification,
        distance_m=pair.distance_m,
        shape_score=pair.shape_score,
        attribute_score=pair.attribute_score,
        total_score=pair.total,
        geometry=pair.ref.geometry,
        alternatives=alternatives,
        attribute_details=json.dumps(list(pair.attribute_details), ensure_ascii=False),
    )


def _missing_candidate(ref: ReferenceFeature) -> Candidate:
    return Candidate(ref.key, None, None, None, MISSING, None, None, None, None, ref.geometry)


def _osm_only_candidate(osm: OsmFeature) -> Candidate:
    return Candidate(None, osm.osm_type, osm.osm_id, osm.version, OSM_ONLY, None, None, None, None, osm.geometry)


def match(
    references: Iterable[ReferenceFeature], osm_features: Iterable[OsmFeature], profile: Profile
) -> MatchResult:
    all_references = list(references)
    supported = [r for r in all_references if geometry_kind(r.geometry) is not None]
    skipped = tuple(r.key for r in all_references if geometry_kind(r.geometry) is None)
    osm_list = [o for o in osm_features if geometry_kind(o.geometry) is not None]

    pairs_by_ref = _candidate_pairs(supported, osm_list, profile)
    assigned, ambiguous = _assign(pairs_by_ref, profile.ambiguity_margin)

    candidates = []
    involved_osm = {p.osm.ref for p in assigned.values()}
    for index, ref in enumerate(supported):
        pairs = pairs_by_ref[index]
        if index in assigned:
            candidates.append(_pair_candidate(assigned[index], _classify(assigned[index])))
        elif index in ambiguous:
            involved_osm |= {p.osm.ref for p in pairs}
            candidates.append(_pair_candidate(pairs[0], AMBIGUOUS, tuple(p.osm.ref for p in pairs[1:])))
        else:
            candidates.append(_missing_candidate(ref))

    if profile.reference_is_exhaustive:
        candidates.extend(_osm_only_candidate(o) for o in osm_list if o.ref not in involved_osm)
    return MatchResult(tuple(candidates), skipped)
