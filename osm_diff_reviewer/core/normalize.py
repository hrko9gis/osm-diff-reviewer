"""Name normalisation and similarity used by attribute comparison.

Pure Python: no QGIS dependency.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Legal-entity designations that are often present on one side only.
# Applied after NFKC, so "（株）" and "㈱" have already become "(株)".
_CORPORATE_FORMS = (
    "株式会社",
    "有限会社",
    "合同会社",
    "合資会社",
    "合名会社",
    "一般社団法人",
    "公益社団法人",
    "一般財団法人",
    "公益財団法人",
    "社会福祉法人",
    "医療法人社団",
    "医療法人財団",
    "医療法人",
    "学校法人",
    "宗教法人",
    "特定非営利活動法人",
    "npo法人",
    "独立行政法人",
    "(株)",
    "(有)",
    "(合)",
    "(社)",
    "(財)",
    "(医)",
    "(学)",
)
_CORPORATE_PATTERN = re.compile("|".join(re.escape(form) for form in _CORPORATE_FORMS))
_WHITESPACE = re.compile(r"\s+")


def normalize_name(value: str | None) -> str:
    """Return a comparison key: NFKC, lower case, no whitespace, no legal-entity designations."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = _WHITESPACE.sub("", text)
    return _CORPORATE_PATTERN.sub("", text)


def name_similarity(left: str | None, right: str | None) -> float:
    """Similarity in [0, 1] of the normalised names; 0 when either side is empty."""
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()
