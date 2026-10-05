"""Licence record of a reference source and the gate in front of every export.

Matching and reviewing are never blocked. Anything that sends reference
attributes or geometry outside QGIS (JOSM reference layer, GeoJSON export,
MapRoulette) must call ``ensure_export_allowed`` first.
"""

from dataclasses import dataclass

from ..i18n import tr

LICENSE_CONFIRMED = "confirmed"
LICENSE_UNCONFIRMED = "unconfirmed"
LICENSE_REJECTED = "rejected"
LICENSE_STATUSES = (LICENSE_UNCONFIRMED, LICENSE_CONFIRMED, LICENSE_REJECTED)


class LicenseGateError(PermissionError):
    """Export refused because the licence of the reference source is not confirmed."""


class LicenseReconfirmationRequired(LicenseGateError):
    """The licence was confirmed for an earlier file; a person must confirm it for the current one."""


@dataclass(frozen=True)
class ReferenceSource:
    name: str
    license_name: str
    attribution: str
    license_status: str
    evidence_url: str
    key_field: str | None
    source_uri: str = ""  # the file the reference data currently comes from
    confirmed_uri: str = ""  # the file the confirmation was given for ("" = recorded before files were tracked)
    confirmed_at: str = ""

    def __post_init__(self) -> None:
        if self.license_status not in LICENSE_STATUSES:
            raise ValueError(f"unknown licence status: {self.license_status!r}")

    @property
    def version_changed(self) -> bool:
        """Confirmed, but for an earlier file (typically a previous release of the data)."""
        return (
            self.license_status == LICENSE_CONFIRMED
            and bool(self.confirmed_uri)
            and self.confirmed_uri != self.source_uri
        )


def export_allowed(source: ReferenceSource | None) -> bool:
    return source is not None and source.license_status == LICENSE_CONFIRMED and not source.version_changed


def ensure_export_allowed(source: ReferenceSource | None) -> None:
    if export_allowed(source):
        return
    if source is None:
        raise LicenseGateError(tr("No licence record for this reference source; record and confirm it first."))
    if source.version_changed:
        raise LicenseReconfirmationRequired(
            tr(
                "The licence of '{}' was confirmed on {} for an earlier file ({}); confirm that the same "
                "conditions apply to the current file."
            ).format(source.name, source.confirmed_at[:10], source.confirmed_uri)
        )
    raise LicenseGateError(
        tr(
            "The licence of reference source '{}' is not confirmed; confirm that it may be used in OSM "
            "before exporting reference data."
        ).format(source.name)
    )
