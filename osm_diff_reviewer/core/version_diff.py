"""Version-diff mode (spec 5.4): compare two versions of the reference data by stable key and
match only the additions, removals and changes against OSM.

- added: is it already in OSM?
- removed: is it still in OSM?
- changed: is OSM closer to the old or the new version?

Each version is matched as a whole, so unchanged features keep competing for OSM objects
and an addition cannot take the OSM object of its unchanged neighbour.
"""

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace

from qgis.core import QgsGeometry

from .features import OsmFeature, ReferenceFeature
from .matching import AMBIGUOUS, MISSING, Candidate, classify_pair, match, pair_candidate, score_pair
from .profile import Profile

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"

IN_OSM = "in_osm"
NOT_IN_OSM = "not_in_osm"
STILL_IN_OSM = "still_in_osm"
GONE_FROM_OSM = "gone_from_osm"
OSM_HAS_OLD = "osm_has_old"
OSM_REFLECTS_NEW = "osm_reflects_new"
UNDECIDED = "undecided"
VERDICT_AMBIGUOUS = "ambiguous"

GEOMETRY_TOLERANCE_M = 0.01


class VersionDiffError(ValueError):
    """The versions cannot be compared; the message is meant for the user."""


@dataclass(frozen=True)
class VersionDiffResult:
    candidates: tuple[Candidate, ...]
    skipped_keys: tuple[str, ...]  # changes whose geometry kind is not matched


@dataclass(frozen=True)
class VersionChange:
    kind: str
    key: str
    old: ReferenceFeature | None
    new: ReferenceFeature | None
    changed_fields: tuple[str, ...] = ()
    geometry_changed: bool = False


def _index(features: Sequence[ReferenceFeature], label: str) -> dict[str, ReferenceFeature]:
    empty = [f for f in features if f.key.startswith("hash:")]  # no ID value: the key fell back to a hash
    if empty:
        raise VersionDiffError(
            f"{len(empty)} feature(s) of the {label} version have an empty ID field; every feature needs a stable ID."
        )
    duplicates = sorted(key for key, count in Counter(f.key for f in features).items() if count > 1)
    if duplicates:
        raise VersionDiffError(f"Keys are not unique in the {label} version: {', '.join(duplicates[:5])}")
    return {f.key: f for f in features}


def _changed_fields(old: ReferenceFeature, new: ReferenceFeature) -> tuple[str, ...]:
    """Fields present in both versions whose values differ (a column added in one version is ignored)."""
    common = old.attributes.keys() & new.attributes.keys()
    return tuple(sorted(name for name in common if old.attributes[name] != new.attributes[name]))


def _geometry_changed(old: QgsGeometry, new: QgsGeometry) -> bool:
    if old.type() != new.type():
        return True
    return old.hausdorffDistance(new) > GEOMETRY_TOLERANCE_M


def diff_versions(old: Sequence[ReferenceFeature], new: Sequence[ReferenceFeature]) -> list[VersionChange]:
    """Additions and changes in the order of the new version, then removals in the order of the old one."""
    old_by_key, new_by_key = _index(old, "old"), _index(new, "new")
    changes = []
    for key, feature in new_by_key.items():
        before = old_by_key.get(key)
        if before is None:
            changes.append(VersionChange(ADDED, key, None, feature))
            continue
        fields = _changed_fields(before, feature)
        moved = _geometry_changed(before.geometry, feature.geometry)
        if fields or moved:
            changes.append(VersionChange(CHANGED, key, before, feature, fields, moved))
    changes += [VersionChange(REMOVED, key, f, None) for key, f in old_by_key.items() if key not in new_by_key]
    return changes


def _presence(candidate: Candidate, present: str, absent: str) -> str:
    if candidate.classification == AMBIGUOUS:
        return VERDICT_AMBIGUOUS
    return absent if candidate.classification == MISSING else present


def _osm_object(candidate: Candidate) -> str | None:
    if candidate.classification == MISSING or not candidate.osm_type:
        return None
    return f"{candidate.osm_type}/{candidate.osm_id}"


def _evaluate_change(
    change: VersionChange,
    old_run: Candidate,
    new_run: Candidate,
    osm_by_ref: dict[str, OsmFeature],
    new_owner: dict[str, str],
    profile: Profile,
) -> Candidate:
    """The OSM object of the change (from the new run, else the old one) decides old vs new by score."""
    if new_run.classification == AMBIGUOUS or (old_run.classification == AMBIGUOUS and _osm_object(new_run) is None):
        return replace(new_run, verdict=VERDICT_AMBIGUOUS)
    osm_ref = _osm_object(new_run) or _osm_object(old_run)
    if osm_ref is None:
        return replace(new_run, verdict=NOT_IN_OSM)
    owner = new_owner.get(osm_ref)
    if owner is not None and owner != change.key:
        # In the new version another feature holds this OSM object: the two rows would contradict.
        return replace(new_run, verdict=VERDICT_AMBIGUOUS, alternatives=(osm_ref,))
    osm = osm_by_ref[osm_ref]
    old_pair, new_pair = score_pair(0, change.old, osm, profile), score_pair(0, change.new, osm, profile)
    if new_pair.total - old_pair.total >= profile.ambiguity_margin:
        verdict = OSM_REFLECTS_NEW
    elif old_pair.total - new_pair.total >= profile.ambiguity_margin:
        verdict = OSM_HAS_OLD
    else:
        verdict = UNDECIDED
    return replace(pair_candidate(new_pair, classify_pair(new_pair)), verdict=verdict)


def evaluate(
    old: Sequence[ReferenceFeature],
    new: Sequence[ReferenceFeature],
    osm_features: Sequence[OsmFeature],
    profile: Profile,
) -> VersionDiffResult:
    """One candidate per change, carrying ``change_kind``, ``verdict`` and ``change_detail``."""
    changes = diff_versions(old, new)
    profile = replace(profile, reference_is_exhaustive=False)
    osm_list = list(osm_features)
    old_run = {c.ref_key: c for c in match(old, osm_list, profile).candidates if c.ref_key is not None}
    new_run = {c.ref_key: c for c in match(new, osm_list, profile).candidates if c.ref_key is not None}
    osm_by_ref = {o.ref: o for o in osm_list}
    new_owner = {ref: key for key, c in new_run.items() if (ref := _osm_object(c)) is not None}

    candidates, skipped = [], []
    for change in changes:
        candidate = _candidate_for(change, old_run.get(change.key), new_run.get(change.key), osm_by_ref, new_owner, profile)
        if candidate is None:
            skipped.append(change.key)
            continue
        detail = {"fields": list(change.changed_fields), "geometry": change.geometry_changed}
        candidates.append(
            replace(candidate, change_kind=change.kind, change_detail=json.dumps(detail, ensure_ascii=False))
        )
    return VersionDiffResult(tuple(candidates), tuple(skipped))


def _candidate_for(change, old_candidate, new_candidate, osm_by_ref, new_owner, profile) -> Candidate | None:
    """None when neither version of the feature could be matched (unsupported geometry kind)."""
    if change.kind == CHANGED and old_candidate is not None and new_candidate is not None:
        return _evaluate_change(change, old_candidate, new_candidate, osm_by_ref, new_owner, profile)
    if change.kind in (ADDED, CHANGED) and new_candidate is not None:
        return replace(new_candidate, verdict=_presence(new_candidate, IN_OSM, NOT_IN_OSM))
    if change.kind in (REMOVED, CHANGED) and old_candidate is not None:
        return replace(old_candidate, verdict=_presence(old_candidate, STILL_IN_OSM, GONE_FROM_OSM))
    return None
