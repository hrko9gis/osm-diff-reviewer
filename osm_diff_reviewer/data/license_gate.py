"""Licence record of a reference source and the gate in front of every export.

Matching and reviewing are never blocked. Anything that sends reference
attributes or geometry outside QGIS (JOSM reference layer, GeoJSON export,
MapRoulette) must call ``ensure_export_allowed`` first.
"""

from dataclasses import dataclass

LICENSE_CONFIRMED = "confirmed"
LICENSE_UNCONFIRMED = "unconfirmed"
LICENSE_REJECTED = "rejected"
LICENSE_STATUSES = (LICENSE_UNCONFIRMED, LICENSE_CONFIRMED, LICENSE_REJECTED)


class LicenseGateError(PermissionError):
    """Export refused because the licence of the reference source is not confirmed."""


@dataclass(frozen=True)
class ReferenceSource:
    name: str
    license_name: str
    attribution: str
    license_status: str
    evidence_url: str
    key_field: str | None
    source_uri: str = ""  # where the data came from; a different dataset must be confirmed again

    def __post_init__(self) -> None:
        if self.license_status not in LICENSE_STATUSES:
            raise ValueError(f"unknown licence status: {self.license_status!r}")


def export_allowed(source: ReferenceSource | None) -> bool:
    return source is not None and source.license_status == LICENSE_CONFIRMED


def ensure_export_allowed(source: ReferenceSource | None) -> None:
    if export_allowed(source):
        return
    if source is None:
        raise LicenseGateError("No licence record for this reference source; record and confirm it first.")
    raise LicenseGateError(
        f"Licence of reference source '{source.name}' is {source.license_status}; "
        "confirm that it may be used in OSM before exporting reference data."
    )
