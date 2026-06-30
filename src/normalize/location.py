"""Location normalization — country string → ISO-3166 alpha-2."""

from __future__ import annotations

import pycountry

# Common aliases not handled by pycountry.lookup
_ALIASES: dict[str, str] = {
    "usa": "US", "united states": "US", "united states of america": "US", "us": "US",
    "uk": "GB", "britain": "GB", "great britain": "GB", "england": "GB", "united kingdom": "GB",
    "south korea": "KR", "korea": "KR",
    "russia": "RU",
    "taiwan": "TW",
    "vietnam": "VN", "viet nam": "VN",
    "iran": "IR",
    "syria": "SY",
    "uae": "AE", "emirates": "AE", "united arab emirates": "AE",
    "中国": "CN", "china": "CN",
    "日本": "JP", "japan": "JP",
    "法国": "FR", "france": "FR",
}


def normalize_country(raw: str) -> str | None:
    """
    Resolve a country name, alpha-2, or alpha-3 code to ISO-3166 alpha-2.

    Returns two-letter code (e.g. 'IN') or None if unresolvable.
    Never raises.
    """
    if not raw or not raw.strip():
        return None

    cleaned = raw.strip()

    # Alias map (case-insensitive)
    lower = cleaned.lower()
    if lower in _ALIASES:
        return _ALIASES[lower]

    # pycountry lookup (handles names, alpha-2, alpha-3)
    try:
        country = pycountry.countries.lookup(cleaned)
        return country.alpha_2
    except LookupError:
        pass

    return None


def parse_location_string(raw: str) -> dict[str, str | None]:
    """
    Heuristically parse a free-form location string into {city, region, country}.

    Examples:
        "Bangalore, Karnataka, India"  → {city: "Bangalore", region: "Karnataka", country: "IN"}
        "San Francisco, CA"            → {city: "San Francisco", region: "CA", country: None}
        "India"                        → {city: None, region: None, country: "IN"}
    """
    result: dict[str, str | None] = {"city": None, "region": None, "country": None}

    if not raw or not raw.strip():
        return result

    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if len(parts) == 1:
        country = normalize_country(parts[0])
        if country:
            result["country"] = country
        else:
            result["city"] = parts[0]

    elif len(parts) == 2:
        result["city"] = parts[0]
        country = normalize_country(parts[1])
        if country:
            result["country"] = country
        else:
            result["region"] = parts[1]

    elif len(parts) >= 3:
        result["city"] = parts[0]
        result["region"] = parts[1]
        result["country"] = normalize_country(parts[2])

    return result
