"""General-purpose helpers used across the pipeline."""

from __future__ import annotations

import re
import unicodedata
from typing import TypeVar

T = TypeVar("T")

PRESENT_MARKERS = frozenset(
    {"present", "current", "now", "ongoing", "till date", "today", "todate", "-", ""}
)


def safe_lower(value: str | None) -> str:
    """Lowercase and strip a string safely. Returns '' for None."""
    if value is None:
        return ""
    return value.strip().lower()


def dedupe_preserve_order(items: list[T]) -> list[T]:
    """Remove duplicates while preserving first-occurrence order."""
    seen: set = set()
    result: list[T] = []
    for item in items:
        key = str(item).lower() if isinstance(item, str) else item
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def slugify(text: str) -> str:
    """Convert text to a lowercase hyphen-slug. Used for stable IDs."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def is_present_marker(text: str) -> bool:
    """Return True if text represents an open/present end date."""
    return safe_lower(text) in PRESENT_MARKERS


def truncate(text: str, max_len: int = 300) -> str:
    """Truncate a string to max_len with ellipsis."""
    return text if len(text) <= max_len else text[:max_len] + "…"


def normalize_person_name(name: str | None) -> str:
    """Strip and collapse internal whitespace in a display name."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip())


def normalize_company_key(name: str | None) -> str:
    """Normalize a company name for identity matching."""
    if not name:
        return ""
    text = safe_lower(name)
    # strip common suffixes
    text = re.sub(r"\b(inc|ltd|llc|pvt|corp|co|limited|private)\b\.?", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name_key(name: str | None) -> str:
    """Normalize a person name for fuzzy matching."""
    if not name:
        return ""
    return normalize_person_name(safe_lower(name))
