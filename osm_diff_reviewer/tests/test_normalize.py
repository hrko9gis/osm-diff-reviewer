import pytest

from osm_diff_reviewer.core.normalize import name_similarity, normalize_name


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ﾃｽﾄ　商店", "テスト商店"),  # half-width kana, full-width space
        ("ＡＢＣ１２３", "abc123"),  # full-width alphanumerics, case
        ("株式会社テスト", "テスト"),
        ("テスト株式会社", "テスト"),
        ("(株)テスト", "テスト"),
        ("（株）テスト", "テスト"),
        ("㈱テスト", "テスト"),
        ("有限会社テスト", "テスト"),
        ("一般社団法人テスト協会", "テスト協会"),
        (" Café  Tokyo ", "cafétokyo"),
    ],
)
def test_normalize_name_equates_variants(left, right):
    assert normalize_name(left) == normalize_name(right)


def test_normalize_name_keeps_long_vowel_mark():
    assert normalize_name("センター") == "センター"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_normalize_name_handles_empty(value):
    assert normalize_name(value) == ""


def test_name_similarity_is_one_for_normalized_equal_names():
    assert name_similarity("株式会社テスト商店", "ﾃｽﾄ商店") == 1.0


def test_name_similarity_is_low_for_different_names():
    assert name_similarity("北公民館", "北地区センター") < 0.5


def test_name_similarity_is_zero_when_one_side_empty():
    assert name_similarity("テスト", "") == 0.0
