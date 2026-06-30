"""Decision Engine — single orchestrator for all merge decisions.

Fixed execution order (= deterministic output):
  1. Validate       → pre-merge gate
  2. Match          → group records by candidate identity
  3. Classify       → severity of each field conflict
  4. Resolve        → field-level winner selection
  5. Review         → escalate unresolvable conflicts
  6. Confidence     → per-field scores + explanations
  7. Quality score  → completeness measurement
  8. Provenance     → audit trail assembly
  9. Version        → snapshot metadata
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.decision.confidence import ConfidenceCalculator
from src.decision.matcher import CandidateMatcher, MatchDecision
from src.decision.quality_score import QualityScorer
from src.decision.resolver import FieldResolver, ReasonCode
from src.decision.review_queue import ReviewQueue
from src.decision.severity import ConflictSeverity, SeverityClassifier
from src.models.canonical import (
    CanonicalProfile,
    CandidateStatus,
    ConfidenceDetail,
    Education,
    Experience,
    FieldDecision,
    Links,
    Location,
    Project,
    ProvenanceEntry,
    Skill,
    VersionSnapshot,
)
from src.models.engine_config import EngineConfig
from src.models.source_record import SourceRecord, ExtractionMethod
from src.validate.validator import ValidationRejection, Validator
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DecisionResult:
    profile: CanonicalProfile
    match_score: float = 0.0
    source_files: list[str] = field(default_factory=list)
    match_keys_used: list[str] = field(default_factory=list)  # e.g. ["email", "phone"]


@dataclass
class RunSummary:
    total: int = 0
    active: int = 0
    manual_review: int = 0
    errors: int = 0
    # Populated by pipeline after processing — not computed by business logic
    total_conflicts: int = 0
    validation_failures: int = 0
    validation_rejections: list[dict[str, str]] = field(default_factory=list)
    normalized_phones: int = 0
    normalized_skills: list[str] = field(default_factory=list)  # ["ReactJS → React", ...]


@dataclass
class PipelineOutput:
    profiles: list[CanonicalProfile] = field(default_factory=list)
    projected: list[dict] = field(default_factory=list)
    summary: RunSummary = field(default_factory=RunSummary)
    decision_results: list[DecisionResult] = field(default_factory=list)


class DecisionEngine:
    """Orchestrates all merge decisions. Single entry point."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._validator = Validator(config)
        self._matcher = CandidateMatcher(config)
        self._resolver = FieldResolver(config)
        self._confidence = ConfidenceCalculator(config)
        self._quality = QualityScorer(config)
        self._review = ReviewQueue(config)
        self._severity = SeverityClassifier()
        self._last_validation_failures = 0
        self._last_validation_rejections: list[ValidationRejection] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, records: list[SourceRecord]) -> list[DecisionResult]:
        """
        Full decision pipeline on a flat list of SourceRecords.

        Steps 1–2: validate then group.
        Steps 3–9: _resolve_group per group.
        """
        # Step 1: Validate each record — count rejections for display
        validated: list[SourceRecord] = []
        self._last_validation_failures = 0
        self._last_validation_rejections: list[ValidationRejection] = []
        for rec in records:
            result = self._validator.validate(rec)
            self._last_validation_failures += len(result.rejections)
            self._last_validation_rejections.extend(result.rejections)
            validated.append(result.record)

        # Step 2: Group by candidate identity
        groups = self._matcher.group_records(validated)
        logger.info("Decision engine: %d record(s) → %d candidate group(s)", len(records), len(groups))

        results: list[DecisionResult] = []
        for group in groups:
            match_score = self._group_match_score(group)
            needs_review_from_match = self._group_needs_review(group)
            match_keys = self._group_match_keys(group)

            try:
                result = self._resolve_group(group, match_score, needs_review_from_match)
                result.match_keys_used = match_keys
                results.append(result)
            except Exception as exc:
                logger.error("Error resolving group (files: %s): %s",
                             [r.source_file for r in group], exc)

        return results

    # ------------------------------------------------------------------
    # Group resolution (steps 3–9)
    # ------------------------------------------------------------------

    def _resolve_group(
        self,
        group: list[SourceRecord],
        match_score: float,
        needs_review_from_match: bool,
    ) -> DecisionResult:
        """Resolve one group of same-candidate records into a CanonicalProfile."""
        region = self.config.validation.phone_default_region

        source_files = [r.source_file or r.source_type.value for r in group]
        candidate_id = self._generate_candidate_id(group)

        profile = CanonicalProfile(candidate_id=candidate_id)
        conflict_log = []
        field_decisions = []
        confidence_details = []
        conflict_severities: dict[str, ConflictSeverity] = {}

        # Build per-source base confidence lookup
        source_confidences = {
            st: self.config.confidence_weights.get(st, 0.7)
            for st in self.config.confidence_weights
        }

        # ---------------------------------------------------------------
        # Step 3+4: Resolve each field
        # ---------------------------------------------------------------

        # full_name
        name_vals = [
            (str(r.full_name.value), r.source_type.value, r.full_name.extraction_method.value)
            for r in group if r.full_name and r.full_name.value
        ]
        if name_vals:
            winner, dec, conflict = self._resolver.resolve_scalar("full_name", name_vals)
            profile.full_name = winner
            field_decisions.append(dec)
            if conflict:
                conflict_log.append(conflict)
                conflict_severities["full_name"] = ConflictSeverity(conflict.severity)

        # headline — CSV title (current_title) competes with resume SUMMARY/headline
        hl_vals: list[tuple[str, str, str]] = []
        for r in group:
            if r.headline and r.headline.value:
                hl_vals.append((
                    str(r.headline.value),
                    r.source_type.value,
                    r.headline.extraction_method.value,
                ))
            if r.current_title and r.current_title.value:
                hl_vals.append((
                    str(r.current_title.value),
                    r.source_type.value,
                    ExtractionMethod.DIRECT.value,
                ))
        if hl_vals:
            winner, dec, conflict = self._resolver.resolve_scalar("headline", hl_vals)
            profile.headline = winner
            field_decisions.append(dec)
            if conflict:
                conflict_log.append(conflict)

        # emails
        email_vals = [
            (str(rf.value), r.source_type.value)
            for r in group for rf in r.emails if rf.value
        ]
        if email_vals:
            emails, dec, conflict = self._resolver.resolve_emails(email_vals)
            profile.emails = emails
            field_decisions.append(dec)
            if conflict:
                conflict_log.append(conflict)
                if len(set(v for v, _ in email_vals)) > 1:
                    conflict_severities["emails"] = ConflictSeverity(conflict.severity)

        # phones
        phone_vals = [
            (str(rf.value), r.source_type.value)
            for r in group for rf in r.phones if rf.value
        ]
        if phone_vals:
            phones, dec, conflict = self._resolver.resolve_phones(phone_vals, region)
            profile.phones = phones
            field_decisions.append(dec)
            if conflict:
                conflict_log.append(conflict)

        # location — explicit from resume, else infer from current education
        for r in group:
            if r.location_raw and r.location_raw.value:
                from src.normalize.location import parse_location_string
                parsed = parse_location_string(str(r.location_raw.value))
                profile.location = Location(
                    city=parsed.get("city"),
                    region=parsed.get("region"),
                    country=parsed.get("country"),
                )
                break

        # links
        for r in group:
            if r.linkedin_url and r.linkedin_url.value:
                profile.links.linkedin = str(r.linkedin_url.value)
                break
        for r in group:
            if r.github_url and r.github_url.value:
                profile.links.github = str(r.github_url.value)
                break
        for r in group:
            if r.leetcode_url and r.leetcode_url.value:
                profile.links.leetcode = str(r.leetcode_url.value)
                break
        for r in group:
            if r.portfolio_url and r.portfolio_url.value:
                profile.links.portfolio = str(r.portfolio_url.value)
                break

        # years_experience
        for r in group:
            if r.years_experience and r.years_experience.value:
                try:
                    profile.years_experience = float(r.years_experience.value)
                    break
                except (ValueError, TypeError):
                    pass

        # skills
        skill_vals: list[tuple[str, str, float]] = []
        for r in group:
            base_conf = source_confidences.get(r.source_type.value, 0.7)
            for rf in r.skills_raw:
                if rf.value:
                    skill_vals.append((str(rf.value), r.source_type.value, base_conf))
        if skill_vals:
            merged_skills = self._resolver.resolve_skills(skill_vals)
            profile.skills = [
                Skill(
                    name=s["name"],
                    confidence=round(s["confidence"], 4),
                    sources=s["sources"],
                )
                for s in merged_skills
            ]

        # experience
        exp_list = self._resolver.resolve_experience(group, source_confidences)
        profile.experience = [
            Experience(
                company=e.get("company"),
                title=e.get("title"),
                start=e.get("start"),
                end=e.get("end"),
                summary=e.get("summary"),
                confidence=round(e.get("confidence", 0.7), 4),
                sources=e.get("sources", []),
            )
            for e in exp_list
        ]

        # projects
        project_list = self._resolver.resolve_projects(group, source_confidences)
        profile.projects = [
            Project(
                title=p.get("title"),
                summary=p.get("summary"),
                url=p.get("url"),
                tech_stack=p.get("tech_stack"),
                confidence=round(p.get("confidence", 0.7), 4),
                sources=p.get("sources", []),
            )
            for p in project_list
        ]

        # education
        edu_list = self._resolver.resolve_education(group, source_confidences)
        profile.education = []
        for e in edu_list:
            degree, field = self._split_degree_and_field(e.get("degree"), e.get("field"))
            profile.education.append(
                Education(
                    institution=e.get("institution"),
                    degree=degree,
                    field=field,
                    location=e.get("location"),
                    start_year=e.get("start_year"),
                    end_year=e.get("end_year"),
                    confidence=round(e.get("confidence", 0.7), 4),
                    sources=e.get("sources", []),
                )
            )

        # infer location from current education when not explicitly stated
        if not profile.location.city and not profile.location.country:
            from src.utils.location_inference import infer_location_from_education
            inferred = infer_location_from_education(profile.education)
            if inferred:
                profile.location = inferred

        # ---------------------------------------------------------------
        # Step 5: Review
        # ---------------------------------------------------------------
        same_phone_diff_identity = self._detect_phone_identity_mismatch(group)
        review_decision = self._review.evaluate(
            conflict_severities=conflict_severities,
            match_score=match_score,
            overall_confidence=0.0,  # computed below — use 0 for now
            same_phone_diff_identity=same_phone_diff_identity,
        )
        if needs_review_from_match:
            from src.decision.review_queue import ReviewTrigger
            review_decision.triggers.append(ReviewTrigger(
                trigger_code="NEAR_THRESHOLD_MATCH",
                description="Candidate match score was near threshold — match uncertain",
            ))
            review_decision.requires_review = True

        # ---------------------------------------------------------------
        # Step 6: Confidence scores
        # ---------------------------------------------------------------
        confidence_details = self._compute_confidence_details(group, profile, conflict_severities)
        profile.confidence_details = confidence_details
        profile.overall_confidence = self._confidence.overall_confidence(confidence_details)

        # Re-evaluate review with real confidence
        final_review = self._review.evaluate(
            conflict_severities=conflict_severities,
            match_score=match_score,
            overall_confidence=profile.overall_confidence,
            same_phone_diff_identity=same_phone_diff_identity,
        )
        if needs_review_from_match:
            from src.decision.review_queue import ReviewTrigger
            final_review.triggers.append(ReviewTrigger(
                trigger_code="NEAR_THRESHOLD_MATCH",
                description="Candidate match score was near threshold",
            ))
            final_review.requires_review = True

        if final_review.requires_review:
            profile.status = CandidateStatus.MANUAL_REVIEW
            profile.review_reasons = final_review.summary_reasons

        # ---------------------------------------------------------------
        # Step 7: Quality score
        # ---------------------------------------------------------------
        quality, breakdown = self._quality.score(profile)
        profile.data_quality_score = quality
        profile.data_quality_breakdown = breakdown

        # ---------------------------------------------------------------
        # Step 8: Provenance
        # ---------------------------------------------------------------
        profile.conflict_log = conflict_log
        profile.field_decisions = field_decisions
        profile.provenance = self._build_provenance(field_decisions)

        # ---------------------------------------------------------------
        # Step 9: Version snapshot
        # ---------------------------------------------------------------
        snapshot = VersionSnapshot(
            version=1,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            sources=list({r.source_type.value for r in group}),
            snapshot_hash=self._hash_profile(profile),
        )
        profile.current_version = 1
        profile.versions = [snapshot]

        return DecisionResult(
            profile=profile,
            match_score=match_score,
            source_files=source_files,
        )

    # ------------------------------------------------------------------
    # Confidence detail builder
    # ------------------------------------------------------------------

    def _compute_confidence_details(
        self,
        group: list[SourceRecord],
        profile: CanonicalProfile,
        conflict_severities: dict[str, ConflictSeverity],
    ) -> list[ConfidenceDetail]:
        details: list[ConfidenceDetail] = []

        def _primary_source(record_list: list[SourceRecord]) -> tuple[str, str]:
            """Return (source_type, extraction_method) of the highest-priority record."""
            best = max(
                record_list,
                key=lambda r: self.config.source_priority.get(r.source_type.value, 0),
            )
            return best.source_type.value, "direct"

        source, method = _primary_source(group)
        num_sources = len({r.source_type.value for r in group})
        agreement = "all_sources_agree" if num_sources == 1 else "single_source"

        scalar_fields = [
            ("full_name", profile.full_name),
            ("headline", profile.headline),
        ]
        for fname, fval in scalar_fields:
            if fval is None:
                continue
            sev = conflict_severities.get(fname, ConflictSeverity.LOW)
            ag = "conflict_penalty" if fname in conflict_severities else agreement
            details.append(self._confidence.field_confidence(fname, fval, source, method, sev, ag))

        if profile.emails:
            sev = conflict_severities.get("emails", ConflictSeverity.LOW)
            details.append(self._confidence.field_confidence(
                "emails", profile.emails, source, method, sev, agreement
            ))
        if profile.phones:
            details.append(self._confidence.field_confidence(
                "phones", profile.phones, source, method, ConflictSeverity.LOW, agreement
            ))
        if profile.skills:
            details.append(self._confidence.field_confidence(
                "skills", len(profile.skills), source, method, ConflictSeverity.LOW, agreement
            ))
        if profile.experience:
            details.append(self._confidence.field_confidence(
                "experience", len(profile.experience), source, "heuristic",
                ConflictSeverity.LOW, agreement
            ))
        if profile.projects:
            details.append(self._confidence.field_confidence(
                "projects", len(profile.projects), source, "heuristic",
                ConflictSeverity.LOW, agreement
            ))
        if profile.education:
            details.append(self._confidence.field_confidence(
                "education", len(profile.education), source, "heuristic",
                ConflictSeverity.LOW, agreement
            ))

        return details

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_degree_and_field(
        degree: str | None, field: str | None
    ) -> tuple[str | None, str | None]:
        """Split 'Master of Science - Computer Science' into degree + field."""
        if field or not degree:
            return degree, field
        text = str(degree).strip()
        for sep in (" - ", " – ", " — "):
            if sep in text:
                left, right = text.split(sep, 1)
                return left.strip(), right.strip()
        return degree, field

    def _build_provenance(self, decisions: list[FieldDecision]) -> list[ProvenanceEntry]:
        return [
            ProvenanceEntry(field=d.field, source=d.source, method=d.method)
            for d in decisions
            if d.source not in ("none", "unknown")
        ]

    def _generate_candidate_id(self, group: list[SourceRecord]) -> str:
        """Stable ID: hash of first email if available, else UUID."""
        for rec in group:
            for rf in rec.emails:
                if rf.value:
                    email = str(rf.value).strip().lower()
                    return "cand_" + hashlib.sha256(email.encode()).hexdigest()[:12]
        return "cand_" + uuid.uuid4().hex[:12]

    def _hash_profile(self, profile: CanonicalProfile) -> str:
        """SHA-256 hash of core profile fields (sorted keys, excludes audit)."""
        core = {
            "full_name": profile.full_name,
            "emails": profile.emails,
            "phones": profile.phones,
        }
        import json
        raw = json.dumps(core, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _group_match_score(self, group: list[SourceRecord]) -> float:
        """Max pairwise match score in a group (groups formed by the matcher)."""
        if len(group) <= 1:
            return 1.0
        best = 0.0
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                r = self._matcher.compare(group[i], group[j])
                best = max(best, r.score)
        return best

    def _group_needs_review(self, group: list[SourceRecord]) -> bool:
        """Return True if any pairwise comparison in the group flagged MANUAL_REVIEW."""
        if len(group) <= 1:
            return False
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                r = self._matcher.compare(group[i], group[j])
                if r.decision == MatchDecision.MANUAL_REVIEW:
                    return True
        return False

    def _group_match_keys(self, group: list[SourceRecord]) -> list[str]:
        """Return the union of match keys used across all pairwise comparisons in the group."""
        if len(group) <= 1:
            return ["single_source"]
        keys: set[str] = set()
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                r = self._matcher.compare(group[i], group[j])
                keys.update(r.match_keys_used)
        return sorted(keys) if keys else ["no_match"]

    def _detect_phone_identity_mismatch(self, group: list[SourceRecord]) -> bool:
        """
        Return True if phones overlap but both names AND emails are completely different
        across sources — classic false-merge indicator.
        """
        if len(group) <= 1:
            return False

        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                phone_match = self._matcher._phone_match_score(a, b) > 0
                email_match = self._matcher._email_match_score(a, b) > 0
                name_a = str(a.full_name.value) if a.full_name else ""
                name_b = str(b.full_name.value) if b.full_name else ""
                name_sev = self._severity.classify_name(name_a, name_b)

                if (phone_match and not email_match and
                        name_sev == ConflictSeverity.HIGH):
                    return True
        return False
