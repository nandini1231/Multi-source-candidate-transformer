"""Infer candidate location from education when not explicitly stated."""

from __future__ import annotations

from datetime import datetime

from src.models.canonical import Education, Location
from src.normalize.location import normalize_country, parse_location_string

_INFERENCE_NOTE = (
    "(inferred from current education — not explicitly stated on resume)"
)


def infer_location_from_education(
    education: list[Education],
) -> Location | None:
    """
    Pick the current/most-recent education entry and derive city/country.
    Returns None if no usable location hint exists.
    """
    if not education:
        return None

    current_year = datetime.now().year
    ranked: list[tuple[int, Education]] = []

    for edu in education:
        end_y = _parse_year(edu.end_year)
        start_y = _parse_year(edu.start_year)
        priority = end_y or start_y or 0
        is_current = end_y is not None and end_y >= current_year
        is_ongoing = (
            start_y is not None
            and start_y <= current_year
            and (end_y is None or end_y >= current_year)
        )
        if is_current or is_ongoing:
            ranked.append((priority, edu))

    if not ranked:
        for edu in education:
            end_y = _parse_year(edu.end_year)
            if end_y:
                ranked.append((end_y, edu))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    edu = ranked[0][1]

    city, region, country = _location_hints_from_education(edu)
    if not city and not country:
        return None

    return Location(
        city=city,
        region=region,
        country=country,
        inferred=True,
        inference_note=_INFERENCE_NOTE,
    )


def _parse_year(value: str | None) -> int | None:
    if not value or not str(value).isdigit():
        return None
    return int(value)


def _location_hints_from_education(
    edu: Education,
) -> tuple[str | None, str | None, str | None]:
    """Extract city/region/country hints from one education entry."""
    if edu.location:
        parsed = parse_location_string(edu.location)
        if parsed.get("city") or parsed.get("country"):
            return parsed.get("city"), parsed.get("region"), parsed.get("country")

    if edu.field and "," in edu.field:
        parsed = parse_location_string(edu.field)
        if parsed.get("city") or parsed.get("country"):
            return parsed.get("city"), parsed.get("region"), parsed.get("country")

    institution = edu.institution or ""
    if not institution:
        return None, None, None

    if institution.count(",") >= 2:
        parsed = parse_location_string(institution)
        if parsed.get("city"):
            return parsed.get("city"), parsed.get("region"), parsed.get("country")

    if "," in institution:
        tail = institution.rsplit(",", 1)[-1].strip()
        if tail and len(tail.split()) <= 3 and not _DEGREE_WORD(tail):
            country = normalize_country("India") if _looks_indian(institution) else None
            return tail, None, country

    return None, None, None


def _looks_indian(text: str) -> bool:
    lower = text.lower()
    return any(
        hint in lower
        for hint in ("india", "nit", "iit", "iiit", "delhi", "mumbai", "bangalore", "chandigarh")
    )


def _DEGREE_WORD(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in ("bachelor", "master", "technology", "engineering", "science"))
