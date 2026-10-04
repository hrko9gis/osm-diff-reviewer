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
