"""Candidate matcher — determines whether SourceRecords belong to the same person.

Match key priority (deterministic):
  1. Exact email match (case-insensitive)       weight = email_match_weight (default 1.0)
  2. Exact phone match (E.164 normalized)        weight = phone_match_weight (default 0.9)
  3. Fuzzy name + company match                  weight = name_company_match_weight (default 0.5)

Decision:
  score >= threshold                    → MERGE
  threshold - margin <= score < threshold → MANUAL_REVIEW
  score < threshold - margin            → SEPARATE

Principle: false merge is worse than a duplicate profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

from src.models.engine_config import EngineConfig
from src.models.source_record import SourceRecord
from src.normalize.phones import normalize_phone
from src.utils.helpers import normalize_company_key, normalize_name_key
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MatchDecision(str, Enum):
    MERGE = "merge"
    SEPARATE = "separate"
    MANUAL_REVIEW = "manual_review"


@dataclass
class MatchResult:
    decision: MatchDecision
    score: float
    match_keys_used: list[str]
    reasons: list[str]


class CandidateMatcher:
    """Groups SourceRecords by candidate identity."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._threshold = config.matching.merge_decision_threshold
        self._margin = config.review.flag_near_threshold_margin
        self._region = config.validation.phone_default_region

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def group_records(self, records: list[SourceRecord]) -> list[list[SourceRecord]]:
        """
        Partition records into groups of same-candidate records.
        Uses union-find so transitive matches (A=B, B=C → same group) are respected.
        """
        n = len(records)
        if n == 0:
            return []

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                result = self.compare(records[i], records[j])
                if result.decision in (MatchDecision.MERGE, MatchDecision.MANUAL_REVIEW):
                    union(i, j)

        # Build groups
        groups: dict[int, list[SourceRecord]] = {}
        for i, rec in enumerate(records):
            root = find(i)
            groups.setdefault(root, []).append(rec)

        return list(groups.values())

    def compare(self, a: SourceRecord, b: SourceRecord) -> MatchResult:
        """Compare two SourceRecords and return a MatchResult."""
        match_keys: list[str] = []
        reasons: list[str] = []
        score = 0.0

        cfg = self.config.matching

        # --- 1. Email ---
        email_score = self._email_match_score(a, b)
        if email_score > 0:
            match_keys.append("email")
            score += email_score * cfg.email_match_weight
            reasons.append(f"email match (score={email_score:.2f})")

        # --- 2. Phone ---
        phone_score = self._phone_match_score(a, b)
        if phone_score > 0:
            match_keys.append("phone")
            score += phone_score * cfg.phone_match_weight
            reasons.append(f"phone match (score={phone_score:.2f})")

        # --- 3. Name + Company ---
        name_score = self._name_company_match_score(a, b)
        if name_score > 0:
            match_keys.append("name_company")
            score += name_score * cfg.name_company_match_weight
            reasons.append(f"name+company match (score={name_score:.2f})")

        # Cap at 1.0
        score = min(score, 1.0)

        decision = self._decide(score)
        logger.debug("Match %s vs %s: score=%.3f → %s", a.source_file, b.source_file, score, decision)
        return MatchResult(decision=decision, score=score, match_keys_used=match_keys, reasons=reasons)

    # ------------------------------------------------------------------
    # Score components
    # ------------------------------------------------------------------

    def _email_match_score(self, a: SourceRecord, b: SourceRecord) -> float:
        """Return 1.0 if any email pair matches exactly (case-insensitive), else 0."""
        emails_a = {str(rf.value).strip().lower() for rf in a.emails if rf.value}
        emails_b = {str(rf.value).strip().lower() for rf in b.emails if rf.value}
        return 1.0 if emails_a & emails_b else 0.0

    def _phone_match_score(self, a: SourceRecord, b: SourceRecord) -> float:
        """Return 1.0 if any E.164 phone pair matches, else 0."""
        region = self._region

        def e164_set(record: SourceRecord) -> set[str]:
            result: set[str] = set()
            for rf in record.phones:
                raw = str(rf.value).strip() if rf.value else ""
                if raw:
                    norm = normalize_phone(raw, region)
                    if norm:
                        result.add(norm)
            return result

        phones_a = e164_set(a)
        phones_b = e164_set(b)
        return 1.0 if phones_a & phones_b else 0.0

    def _name_company_match_score(self, a: SourceRecord, b: SourceRecord) -> float:
        """Return fuzzy name match × company match factor (0–1)."""
        name_a = normalize_name_key(a.full_name.value if a.full_name else None)
        name_b = normalize_name_key(b.full_name.value if b.full_name else None)

        if not name_a or not name_b:
            return 0.0

        name_ratio = fuzz.token_set_ratio(name_a, name_b) / 100.0
        if name_ratio < self.config.matching.fuzzy_name_min_ratio / 100.0:
            return 0.0

        # Boost if company also matches
        co_a = normalize_company_key(a.current_company.value if a.current_company else None)
        co_b = normalize_company_key(b.current_company.value if b.current_company else None)

        if co_a and co_b:
            co_ratio = fuzz.token_set_ratio(co_a, co_b) / 100.0
            return name_ratio * (0.7 + 0.3 * co_ratio)

        return name_ratio * 0.7  # name-only match is weaker

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    def _decide(self, score: float) -> MatchDecision:
        if score >= self._threshold:
            return MatchDecision.MERGE
        if score >= self._threshold - self._margin:
            return MatchDecision.MANUAL_REVIEW
        return MatchDecision.SEPARATE
