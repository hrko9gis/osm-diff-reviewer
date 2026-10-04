import pytest

from osm_diff_reviewer.core import review
from osm_diff_reviewer.core.review import PriorReview, ReviewKey


def _prior(status=review.NOT_NEEDED_OSM, ref_hash="h1", osm_version=3):
    return PriorReview(status=status, note="", ref_hash=ref_hash, osm_version=osm_version, needs_recheck=False)


def test_review_key_normalises_missing_parts():
    assert ReviewKey.of("src", None, None, None) == ReviewKey("src", "", "", 0)
    assert ReviewKey.of("src", "R1", "node", 5) == ReviewKey("src", "R1", "node", 5)


def test_unchanged_pair_needs_no_recheck():
    assert review.needs_recheck(_prior(), "h1", 3) is False


def test_changed_reference_needs_recheck():
    assert review.needs_recheck(_prior(), "h2", 3) is True


def test_changed_osm_version_needs_recheck():
    assert review.needs_recheck(_prior(), "h1", 4) is True


def test_unknown_osm_version_does_not_trigger_recheck():
    assert review.needs_recheck(_prior(osm_version=None), "h1", None) is False
    assert review.needs_recheck(_prior(osm_version=3), "h1", None) is False


def test_unreviewed_prior_never_needs_recheck():
    assert review.needs_recheck(_prior(status=review.UNREVIEWED), "h2", 9) is False


@pytest.mark.parametrize(
    ("status", "recheck", "hidden"),
    [
        (review.NOT_NEEDED_REFERENCE, False, True),
        (review.NOT_NEEDED_OSM, False, True),
        (review.NOT_NEEDED_OSM, True, False),
        (review.ON_HOLD, False, False),
        (review.UNREVIEWED, False, False),
        (review.DONE, False, False),
    ],
)
def test_hidden_by_default(status, recheck, hidden):
    assert review.is_hidden_by_default(status, recheck) is hidden


def test_all_statuses_are_listed_once():
    assert len(set(review.STATUSES)) == len(review.STATUSES) == 6
