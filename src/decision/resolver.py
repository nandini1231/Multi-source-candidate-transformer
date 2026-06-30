"""Field-level conflict resolver.

For each canonical field, picks the winner using source priority from EngineConfig.
Records every decision in a FieldDecision + ConflictEntry.

Policies:
  Scalar  : highest source_priority wins; lower source fills gaps only
  Emails  : union + dedupe; structured source ordering first
  Phones  : union + dedupe by E.164
  Skills  : union by canonical name; max confidence, merged sources
  Exp/Edu : merge by identity key; structured source preferred for dates
"""

from __future__ import annotations

from typing import Any

from src.decision.severity import ConflictSeverity, SeverityClassifier
from src.models.canonical import ConflictEntry, FieldDecision
from src.models.engine_config import EngineConfig
from src.models.source_record import SourceRecord
from src.normalize.phones import normalize_phone
from src.normalize.skills import normalize_skill
from src.utils.helpers import normalize_company_key, safe_lower
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReasonCode:
    HIGHER_SOURCE_PRIORITY = "HIGHER_SOURCE_PRIORITY"
    NORMALIZATION_MATCH = "NORMALIZATION_MATCH"
    UNION_DEDUPE = "UNION_DEDUPE"
    MERGED_DUPLICATE_SKILLS = "MERGED_DUPLICATE_SKILLS"
    GAP_FILL = "GAP_FILL"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class FieldResolver:
    """Resolves field-level conflicts for a group of same-candidate SourceRecords."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.classifier = SeverityClassifier()

    # ------------------------------------------------------------------
    # Scalar fields
    # ------------------------------------------------------------------

    def resolve_scalar(
        self,
        field_name: str,
        values: list[tuple[str, str, str]],  # (value, source_type, extraction_method)
    ) -> tuple[str | None, FieldDecision, ConflictEntry | None]:
        """
        Resolve a scalar field.

        Args:
            field_name: Canonical field name.
            values: Non-None extracted values as (value, source_type, extraction_method).

        Returns:
            (winner, FieldDecision, ConflictEntry|None)
        """
        if not values:
            return None, self._no_decision(field_name), None

        if len(values) == 1:
            val, source, method = values[0]
            return val, FieldDecision(
                field=field_name, source=source, method=method,
                reason_code=ReasonCode.SINGLE_SOURCE,
                reason_human=f"Only source: {source}",
            ), None

        # Multiple values — check if they all agree after normalisation
        normalised = [safe_lower(v[0]) for v in values]
        if len(set(normalised)) == 1:
            # LOW severity — all same after normalisation
            val, source, method = values[0]  # any would do; pick first
            return val, FieldDecision(
                field=field_name, source=source, method=method,
                reason_code=ReasonCode.NORMALIZATION_MATCH,
                reason_human="All sources agree after normalization",
            ), None

        # Sort by source priority (descending)
        sorted_values = sorted(
            values,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        )
        winner_val, winner_source, winner_method = sorted_values[0]
        alternates = sorted_values[1:]

        # Classify severity of the conflict
        severity = self.classifier.classify_scalar(winner_val, alternates[0][0])

        conflict = ConflictEntry(
            field=field_name,
            severity=severity.value,
            values=[{"value": v, "source": s} for v, s, _ in values],
            selected=winner_val,
            reason="Higher source priority",
            explanation=(
                f"{winner_source} (priority {self._source_priority(winner_source)}) "
                f"over {alternates[0][1]} (priority {self._source_priority(alternates[0][1])})"
            ),
        )
        decision = FieldDecision(
            field=field_name,
            source=winner_source,
            method=winner_method,
            reason_code=ReasonCode.HIGHER_SOURCE_PRIORITY,
            reason_human=f"Selected from {winner_source} — higher source priority",
            alternates_rejected=[
                {"value": v, "source": s, "severity": severity.value}
                for v, s, _ in alternates
            ],
        )
        return winner_val, decision, conflict

    # ------------------------------------------------------------------
    # Emails
    # ------------------------------------------------------------------

    def resolve_emails(
        self,
        values: list[tuple[str, str]],  # (email, source_type)
    ) -> tuple[list[str], FieldDecision, ConflictEntry | None]:
        """Union + dedupe; structured sources first in output order."""
        if not values:
            return [], self._no_decision("emails"), None

        # Sort by source priority so higher-priority sources appear first
        sorted_vals = sorted(
            values,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        )

        seen: set[str] = set()
        deduped: list[str] = []
        for email, _ in sorted_vals:
            key = email.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(email.lower().strip())

        conflict = None
        unique_sources = list(dict.fromkeys(s for _, s in values))
        if len(deduped) > 1:
            severity = (
                ConflictSeverity.MEDIUM.value
                if len(unique_sources) > 1
                else ConflictSeverity.LOW.value
            )
            conflict = ConflictEntry(
                field="emails",
                severity=severity,
                values=[{"value": v, "source": s} for v, s in values],
                selected=deduped,
                reason="Union of emails from all sources",
                explanation=(
                    f"Retained {len(deduped)} unique email(s); "
                    "none discarded during merge"
                ),
            )

        decision = FieldDecision(
            field="emails",
            source=sorted_vals[0][1] if sorted_vals else "unknown",
            method="direct",
            reason_code=ReasonCode.UNION_DEDUPE,
            reason_human="Union + deduplicate across sources",
        )
        return deduped, decision, conflict

    # ------------------------------------------------------------------
    # Phones
    # ------------------------------------------------------------------

    def resolve_phones(
        self,
        values: list[tuple[str, str]],  # (phone_raw_or_e164, source_type)
        default_region: str = "IN",
    ) -> tuple[list[str], FieldDecision, ConflictEntry | None]:
        """Union + dedupe by E.164; structured sources first."""
        if not values:
            return [], self._no_decision("phones"), None

        sorted_vals = sorted(
            values,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        )

        seen_e164: set[str] = set()
        deduped: list[str] = []
        for phone, _ in sorted_vals:
            e164 = normalize_phone(str(phone), default_region) if phone else None
            if e164 and e164 not in seen_e164:
                seen_e164.add(e164)
                deduped.append(e164)

        decision = FieldDecision(
            field="phones",
            source=sorted_vals[0][1] if sorted_vals else "unknown",
            method="direct",
            reason_code=ReasonCode.UNION_DEDUPE,
            reason_human="E.164 normalised + deduplicated across sources",
        )
        return deduped, decision, None

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def resolve_skills(
        self,
        values: list[tuple[str, str, float]],  # (skill_raw, source_type, base_confidence)
    ) -> list[dict[str, Any]]:
        """
        Union by canonical name; merge source lists; confidence = max.
        Returns list of {name, confidence, sources}.
        """
        skill_map: dict[str, dict[str, Any]] = {}

        for raw_skill, source, base_conf in values:
            canonical = normalize_skill(raw_skill)
            key = canonical.lower()
            if key not in skill_map:
                skill_map[key] = {"name": canonical, "confidence": base_conf, "sources": [source]}
            else:
                # Merge
                skill_map[key]["confidence"] = max(skill_map[key]["confidence"], base_conf)
                if source not in skill_map[key]["sources"]:
                    skill_map[key]["sources"].append(source)

        return list(skill_map.values())

    # ------------------------------------------------------------------
    # Experience
    # ------------------------------------------------------------------

    def resolve_experience(
        self,
        records: list[SourceRecord],
        source_confidences: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        Merge experience entries across records using identity key matching.
        Key = (company_normalized, title_normalized, start_year_or_None).
        Structured source preferred for dates/title; resume fills summary gaps.
        """
        # Collect all raw entries with their source
        all_entries: list[tuple[dict[str, Any], str, float]] = []
        for record in records:
            source = record.source_type.value
            conf = source_confidences.get(source, 0.7)
            for rf in record.experience_raw:
                if isinstance(rf.value, dict):
                    all_entries.append((rf.value, source, conf))

        if not all_entries:
            return []

        merged: dict[str, dict[str, Any]] = {}

        for entry, source, conf in sorted(
            all_entries,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        ):
            key = self._exp_key(entry)
            if key not in merged:
                merged[key] = {
                    "company": entry.get("company"),
                    "title": entry.get("title"),
                    "start": entry.get("start"),
                    "end": entry.get("end"),
                    "summary": entry.get("summary"),
                    "confidence": conf,
                    "sources": [source],
                }
            else:
                existing = merged[key]
                # Fill missing fields from lower-priority source
                for field in ("company", "title", "start", "end"):
                    if not existing.get(field) and entry.get(field):
                        existing[field] = entry[field]
                if not existing.get("summary") and entry.get("summary"):
                    existing["summary"] = entry["summary"]
                if source not in existing["sources"]:
                    existing["sources"].append(source)

        return list(merged.values())

    # ------------------------------------------------------------------
    # Education
    # ------------------------------------------------------------------

    def resolve_education(
        self,
        records: list[SourceRecord],
        source_confidences: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        Merge education entries using identity key matching.
        Key = (institution_normalized, degree_normalized).
        """
        all_entries: list[tuple[dict[str, Any], str, float]] = []
        for record in records:
            source = record.source_type.value
            conf = source_confidences.get(source, 0.7)
            for rf in record.education_raw:
                if isinstance(rf.value, dict):
                    all_entries.append((rf.value, source, conf))

        if not all_entries:
            return []

        merged: dict[str, dict[str, Any]] = {}

        for entry, source, conf in sorted(
            all_entries,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        ):
            key = self._edu_key(entry)
            if key not in merged:
                merged[key] = {
                    "institution": entry.get("institution"),
                    "degree": entry.get("degree"),
                    "field": entry.get("field"),
                    "location": entry.get("location"),
                    "start_year": entry.get("start_year"),
                    "end_year": entry.get("end_year"),
                    "confidence": conf,
                    "sources": [source],
                }
            else:
                existing = merged[key]
                for f in ("institution", "degree", "field", "location", "start_year", "end_year"):
                    if not existing.get(f) and entry.get(f):
                        existing[f] = entry[f]
                if source not in existing["sources"]:
                    existing["sources"].append(source)

        return list(merged.values())

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def resolve_projects(
        self,
        records: list[SourceRecord],
        source_confidences: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Merge project entries across records by normalized title."""
        all_entries: list[tuple[dict[str, Any], str, float]] = []
        for record in records:
            source = record.source_type.value
            conf = source_confidences.get(source, 0.7)
            for rf in record.projects_raw:
                if isinstance(rf.value, dict):
                    all_entries.append((rf.value, source, conf))

        if not all_entries:
            return []

        merged: dict[str, dict[str, Any]] = {}

        for entry, source, conf in sorted(
            all_entries,
            key=lambda x: self._source_priority(x[1]),
            reverse=True,
        ):
            key = safe_lower(entry.get("title", ""))
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "title": entry.get("title"),
                    "summary": entry.get("summary"),
                    "url": entry.get("url"),
                    "tech_stack": entry.get("tech_stack"),
                    "confidence": conf,
                    "sources": [source],
                }
            else:
                existing = merged[key]
                for f in ("title", "summary", "url", "tech_stack"):
                    if not existing.get(f) and entry.get(f):
                        existing[f] = entry[f]
                if source not in existing["sources"]:
                    existing["sources"].append(source)

        return list(merged.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _source_priority(self, source_type: str) -> int:
        return self.config.source_priority.get(source_type, 0)

    def _exp_key(self, entry: dict[str, Any]) -> str:
        co = normalize_company_key(entry.get("company", ""))
        title = safe_lower(entry.get("title", ""))
        start = (entry.get("start") or "")[:7]  # YYYY-MM
        return f"{co}|{title}|{start}"

    def _edu_key(self, entry: dict[str, Any]) -> str:
        inst = safe_lower(entry.get("institution", ""))
        deg = safe_lower(entry.get("degree", ""))
        return f"{inst}|{deg}"

    def _no_decision(self, field_name: str) -> FieldDecision:
        return FieldDecision(
            field=field_name, source="none", method="none",
            reason_code="NO_VALUE", reason_human="No value found",
        )
