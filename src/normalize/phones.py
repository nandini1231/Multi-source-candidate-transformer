"""Phone normalization — raw string → E.164. Returns None if invalid, never raises."""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, is_valid_number

# NANP: (415) 555-2671, 415-555-2671, etc.
_US_PAREN_RE = re.compile(r"^\(\d{3}\)\s*\d{3}[-\s.]?\d{4}$")
_US_DASH_RE = re.compile(r"^\d{3}[-\s.]\d{3}[-\s.]\d{4}$")


def _digits_only(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _candidate_regions(raw: str, default_region: str) -> list[str | None]:
    """
    Build an ordered list of regions to try when parsing a phone number.

    Explicit international prefixes and regional formatting cues are tried
    before falling back to the configured default region.
    """
    stripped = raw.strip()
    if not stripped:
        return [default_region]

    if stripped.startswith("+"):
        return [None]

    if stripped.startswith("00"):
        return [None]

    if _US_PAREN_RE.match(stripped) or _US_DASH_RE.match(stripped):
        return ["US", "CA", default_region]

    digits = _digits_only(stripped)

    if stripped.startswith("0") and len(digits) >= 10:
        return ["GB", default_region]

    if digits.startswith("44") and len(digits) >= 11:
        return ["GB", default_region]

    if digits.startswith("91") and len(digits) >= 12:
        return ["IN", default_region]

    if len(digits) == 10 and digits[0] in "23456789":
        # Ambiguous 10-digit — prefer default region, then NANP.
        return [default_region, "US", "GB"]

    return [default_region, "US", "GB"]


def _try_parse_e164(raw: str, region: str | None) -> str | None:
    try:
        parsed = phonenumbers.parse(raw.strip(), region)
        if is_valid_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException:
        pass
    return None


def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    """
    Normalize a phone string to E.164 format.

    Args:
        raw: Raw phone string from any source.
        default_region: ISO-3166 alpha-2 country code assumed when no country code present.

    Returns:
        E.164 string (e.g. "+919876543210") or None for invalid/unrecognisable input.

    Examples:
        "9876543210"         -> "+919876543210"  (default_region="IN")
        "(415) 555-2671"     -> "+14155552671"   (US formatting detected)
        "+1 415 555 2671"    -> "+14155552671"
        "+44 7911 123456"    -> "+447911123456"
        "call me"            -> None
    """
    if not raw or not raw.strip():
        return None

    seen: set[str | None] = set()
    for region in _candidate_regions(raw, default_region):
        if region in seen:
            continue
        seen.add(region)
        e164 = _try_parse_e164(raw, region)
        if e164:
            return e164

    return None


def phones_are_equivalent(a: str, b: str, default_region: str = "IN") -> bool:
    """Return True if two phone strings refer to the same E.164 number."""
    norm_a = normalize_phone(a, default_region)
    norm_b = normalize_phone(b, default_region)
    if norm_a is None or norm_b is None:
        return False
    return norm_a == norm_b
