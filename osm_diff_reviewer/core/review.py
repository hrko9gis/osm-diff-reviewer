"""Review states and the rules for carrying decisions over between runs.

Pure Python: no QGIS dependency. Labels are translated by the GUI.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple

UNREVIEWED = "unreviewed"
NEEDS_EDIT = "needs_edit"
DONE = "done"
NOT_NEEDED_REFERENCE = "not_needed_reference"  # the reference data is wrong
NOT_NEEDED_OSM = "not_needed_osm"  # OSM is right
ON_HOLD = "on_hold"
STATUSES = (UNREVIEWED, NEEDS_EDIT, DONE, NOT_NEEDED_REFERENCE, NOT_NEEDED_OSM, ON_HOLD)
NOT_NEEDED_STATUSES = frozenset({NOT_NEEDED_REFERENCE, NOT_NEEDED_OSM})

_STATUS_LABELS = {
    UNREVIEWED: "Unreviewed",
    NEEDS_EDIT: "Needs edit",
    DONE: "Done",
    NOT_NEEDED_REFERENCE: "Not needed (reference is wrong)",
    NOT_NEEDED_OSM: "Not needed (OSM is right)",
    ON_HOLD: "On hold",
}


def status_label(status: str, translate=lambda text: text) -> str:
    return translate(_STATUS_LABELS.get(status, status))


class ReviewKey(NamedTuple):
    """Identity of a reviewed pair: reference key + OSM object, per reference source."""

    source_name: str
    ref_key: str
    osm_type: str
    osm_id: int

    @classmethod
    def of(cls, source_name: str, ref_key: str | None, osm_type: str | None, osm_id: int | None) -> "ReviewKey":
        return cls(source_name, ref_key or "", osm_type or "", osm_id or 0)


@dataclass(frozen=True)
class PriorReview:
    status: str
    note: str
    ref_hash: str  # reference content when the decision was made
    osm_version: int | None  # OSM version when the decision was made
    needs_recheck: bool
    updated_at: str = ""


@dataclass(frozen=True)
class ReviewRow:
    """A candidate of one run joined with its review state."""

    run_id: int
    source_name: str
    ref_key: str | None
    osm_type: str | None
    osm_id: int | None
    osm_version: int | None
    classification: str
    distance_m: float | None
    shape_score: float | None
    attribute_score: float | None
    total_score: float | None
    alternatives: str
    attribute_details: str
    ref_hash: str
    ref_attributes: Mapping[str, Any] = field(default_factory=dict)
    osm_tags: Mapping[str, str] = field(default_factory=dict)
    ref_wkt: str = ""
    osm_wkt: str = ""
    status: str = UNREVIEWED
    note: str = ""
    needs_recheck: bool = False
    change_kind: str = ""  # version-diff runs only
    verdict: str = ""
    change_detail: str = ""

    @property
    def key(self) -> ReviewKey:
        return ReviewKey.of(self.source_name, self.ref_key, self.osm_type, self.osm_id)


def needs_recheck(prior: PriorReview, ref_hash: str, osm_version: int | None) -> bool:
    """A decided pair must be looked at again when either side changed since the decision."""
    if prior.status == UNREVIEWED:
        return False
    reference_changed = bool(prior.ref_hash) and prior.ref_hash != ref_hash
    osm_changed = osm_version is not None and prior.osm_version is not None and prior.osm_version != osm_version
    return reference_changed or osm_changed


def is_hidden_by_default(status: str, recheck: bool) -> bool:
    return status in NOT_NEEDED_STATUSES and not recheck
