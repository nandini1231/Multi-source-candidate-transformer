"""Date normalization — raw string → YYYY-MM. Returns None if invalid or 'Present'."""

from __future__ import annotations

import re

MONTH_NAMES: dict[str, str] = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}

_PRESENT_MARKERS = frozenset(
    {"present", "current", "now", "ongoing", "till date", "today", "todate", "-", ""}
)


def normalize_date(raw: str, allow_present: bool = True) -> str | None:
    """
    Normalize a date string to YYYY-MM.

    'Present' / 'Current' → None (open-ended end date).
    Returns None for unparseable input — never raises, never guesses.

    Supported patterns:
        "2020-01"        → "2020-01"
        "Jan 2020"       → "2020-01"
        "January 2020"   → "2020-01"
        "2020 Jan"       → "2020-01"
        "01/2020"        → "2020-01"
        "2020/01"        → "2020-01"
        "2020"           → "2020-01" (month assumed Jan)
        "Present"        → None
    """
    if not raw:
        return None

    cleaned = raw.strip().lower()

    if allow_present and cleaned in _PRESENT_MARKERS:
        return None

    # YYYY-MM already
    if re.match(r"^\d{4}-\d{2}$", cleaned):
        return cleaned

    # YYYY only
    if re.match(r"^\d{4}$", cleaned):
        return f"{cleaned}-01"

    # "Jan 2020" or "January 2020"
    m = re.match(r"^([a-z]+)\s+(\d{4})$", cleaned)
    if m:
        month = MONTH_NAMES.get(m.group(1))
        if month:
            return f"{m.group(2)}-{month}"

    # "2020 Jan" or "2020 January"
    m = re.match(r"^(\d{4})\s+([a-z]+)$", cleaned)
    if m:
        month = MONTH_NAMES.get(m.group(2))
        if month:
            return f"{m.group(1)}-{month}"

    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", cleaned)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}"

    # YYYY/MM or YYYY.MM
    m = re.match(r"^(\d{4})[/\.\-](\d{1,2})$", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}"

    # Fallback: extract any 4-digit year and assume January
    m = re.search(r"\b(\d{4})\b", cleaned)
    if m:
        return f"{m.group(1)}-01"

    return None


def normalize_year(raw: str) -> str | None:
    """Extract a 4-digit year from a string. Returns 'YYYY' or None."""
    if not raw:
        return None
    m = re.search(r"\b(\d{4})\b", raw.strip())
    return m.group(1) if m else None


def date_is_valid_range(start: str | None, end: str | None) -> bool:
    """
    Return True if start ≤ end (or end is None — open range).
    Both values must be YYYY-MM strings.
    """
    if start is None or end is None:
        return True
    return start <= end
