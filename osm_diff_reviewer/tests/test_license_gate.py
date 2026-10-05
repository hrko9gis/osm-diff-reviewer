import pytest

from osm_diff_reviewer.data.license_gate import (
    LICENSE_CONFIRMED,
    LICENSE_REJECTED,
    LICENSE_STATUSES,
    LICENSE_UNCONFIRMED,
    LicenseGateError,
    ReferenceSource,
    ensure_export_allowed,
    export_allowed,
)


def _source(status):
    return ReferenceSource("src", "CC BY 4.0", "○○市", status, "https://example.org", "id", "u")


def test_only_confirmed_sources_may_be_exported():
    assert export_allowed(_source(LICENSE_CONFIRMED)) is True
    assert export_allowed(_source(LICENSE_UNCONFIRMED)) is False
    assert export_allowed(_source(LICENSE_REJECTED)) is False
    assert export_allowed(None) is False


@pytest.mark.parametrize("status", [LICENSE_UNCONFIRMED, LICENSE_REJECTED])
def test_ensure_export_allowed_raises_with_reason(status):
    with pytest.raises(LicenseGateError, match="src"):
        ensure_export_allowed(_source(status))


def test_ensure_export_allowed_passes_confirmed():
    ensure_export_allowed(_source(LICENSE_CONFIRMED))


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        ReferenceSource("src", "", "", "maybe", "", None, "")
    assert set(LICENSE_STATUSES) == {LICENSE_CONFIRMED, LICENSE_UNCONFIRMED, LICENSE_REJECTED}


def _confirmed(source_uri="b.gpkg", confirmed_uri="a.gpkg"):
    return ReferenceSource(
        "src", "CC BY 4.0", "○○市", LICENSE_CONFIRMED, "", "id", source_uri, confirmed_uri, "2026-10-05T09:00:00+00:00"
    )


def test_confirmation_of_an_older_file_needs_reconfirmation():
    from osm_diff_reviewer.data.license_gate import LicenseReconfirmationRequired

    source = _confirmed()
    assert source.version_changed is True
    assert export_allowed(source) is False
    with pytest.raises(LicenseReconfirmationRequired, match="2026-10-05"):
        ensure_export_allowed(source)


def test_confirmation_of_the_current_file_or_legacy_record_is_enough():
    assert export_allowed(_confirmed(confirmed_uri="b.gpkg")) is True
    assert export_allowed(_confirmed(confirmed_uri="")) is True  # recorded before files were tracked
    assert _confirmed(confirmed_uri="").version_changed is False


def test_reconfirmation_is_only_for_confirmed_sources():
    unconfirmed = ReferenceSource("src", "", "", LICENSE_UNCONFIRMED, "", None, "b", "a", "")
    assert unconfirmed.version_changed is False
