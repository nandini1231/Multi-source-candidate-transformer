"""Conflict severity classifier — LOW / MEDIUM / HIGH.

LOW    : same value, different representation (formatting only)
MEDIUM : related but not identical — resolvable by source priority
HIGH   : fundamentally different identity signals — must not auto-merge
"""

from __future__ import annotations

from enum import Enum

from rapidfuzz import fuzz

from src.normalize.phones import normalize_phone
from src.utils.helpers import safe_lower


class ConflictSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SeverityClassifier:
    """Classifies field conflicts as LOW / MEDIUM / HIGH."""

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def classify_email(self, a: str, b: str) -> ConflictSeverity:
        """
        LOW    : identical after lowercase + trim
        MEDIUM : same local-part OR same domain but different overall
        HIGH   : completely different
        """
        na, nb = safe_lower(a), safe_lower(b)
        if na == nb:
            return ConflictSeverity.LOW

        local_a = na.split("@")[0] if "@" in na else na
        local_b = nb.split("@")[0] if "@" in nb else nb
        domain_a = na.split("@")[1] if "@" in na else ""
        domain_b = nb.split("@")[1] if "@" in nb else ""

        if local_a == local_b or domain_a == domain_b:
            return ConflictSeverity.MEDIUM

        return ConflictSeverity.HIGH

    # ------------------------------------------------------------------
    # Phone
    # ------------------------------------------------------------------

    def classify_phone(self, a: str, b: str, default_region: str = "IN") -> ConflictSeverity:
        """
        LOW    : same number after E.164 normalization
        MEDIUM : same country code, different number
        HIGH   : different country code or completely different
        """
        na = normalize_phone(a, default_region)
        nb = normalize_phone(b, default_region)

        if na is not None and nb is not None:
            if na == nb:
                return ConflictSeverity.LOW
            # Compare country codes (first digits after '+')
            cc_a = self._country_code(na)
            cc_b = self._country_code(nb)
            if cc_a and cc_b and cc_a == cc_b:
                return ConflictSeverity.MEDIUM

        return ConflictSeverity.HIGH

    def _country_code(self, e164: str) -> str:
        """Extract country code from E.164 (e.g. '+1' from '+14155552671')."""
        import phonenumbers
        try:
            p = phonenumbers.parse(e164, None)
            return str(p.country_code)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Name
    # ------------------------------------------------------------------

    def classify_name(self, a: str, b: str) -> ConflictSeverity:
        """
        LOW    : identical after case-fold + whitespace normalize
        MEDIUM : token overlap ≥ 1 (subset or partial match)
        HIGH   : zero token overlap
        """
        na, nb = safe_lower(a), safe_lower(b)
        if na == nb:
            return ConflictSeverity.LOW

        ratio = fuzz.token_set_ratio(na, nb)
        if ratio >= 60:
            return ConflictSeverity.MEDIUM

        tokens_a = set(na.split())
        tokens_b = set(nb.split())
        if tokens_a & tokens_b:
            return ConflictSeverity.MEDIUM

        return ConflictSeverity.HIGH

    # ------------------------------------------------------------------
    # Generic scalar
    # ------------------------------------------------------------------

    def classify_scalar(self, a: str, b: str) -> ConflictSeverity:
        """
        LOW    : same after strip + lower
        MEDIUM : non-zero token overlap
        HIGH   : completely different
        """
        na, nb = safe_lower(a), safe_lower(b)
        if na == nb:
            return ConflictSeverity.LOW

        ratio = fuzz.token_set_ratio(na, nb)
        if ratio >= 50:
            return ConflictSeverity.MEDIUM

        return ConflictSeverity.HIGH

    # ------------------------------------------------------------------
    # Date
    # ------------------------------------------------------------------

    def classify_date(self, a: str | None, b: str | None) -> ConflictSeverity:
        """
        LOW    : same YYYY-MM
        MEDIUM : same year, month gap ≤ 3
        HIGH   : different year
        """
        if a == b:
            return ConflictSeverity.LOW
        if a is None or b is None:
            return ConflictSeverity.LOW  # one is missing — not a real conflict

        year_a, month_a = int(a[:4]), int(a[5:7]) if len(a) >= 7 else 1
        year_b, month_b = int(b[:4]), int(b[5:7]) if len(b) >= 7 else 1

        if year_a == year_b:
            if abs(month_a - month_b) <= 3:
                return ConflictSeverity.MEDIUM
            return ConflictSeverity.MEDIUM  # same year counts as medium regardless

        return ConflictSeverity.HIGH
