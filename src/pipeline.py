"""Top-level pipeline orchestrator — called by the CLI.

Execution order:
  1. Load configs
  2. Parse CSV + resumes (adapters)
  3. Normalize all SourceRecord fields
  4. Decision Engine (validate → match → resolve → score → audit → version)
  5. Project each CanonicalProfile via ProjectionConfig
  6. Build PipelineOutput + write JSON
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.adapters.recruiter_csv import RecruiterCSVAdapter
from src.adapters.resume import ResumeAdapter
from src.decision.engine import DecisionEngine, PipelineOutput, RunSummary
from src.models.canonical import CandidateStatus, CanonicalProfile
from src.models.engine_config import EngineConfig
from src.models.projection_config import ProjectionConfig
from src.models.source_record import SourceRecord
from src.normalize.location import parse_location_string
from src.normalize.phones import normalize_phone
from src.normalize.skills import normalize_skill
from src.utils.helpers import normalize_person_name
from src.project.projector import Projector
from src.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

_RESUME_EXTENSIONS = {".pdf", ".docx", ".doc"}


class Pipeline:
    """End-to-end transformation pipeline."""

    def __init__(
        self,
        engine_config_path: Path = Path("config/engine_config.json"),
        projection_config_path: Path = Path("config/projection_config.json"),
    ) -> None:
        configure_logging()

        self.engine_config = (
            EngineConfig.from_file(engine_config_path)
            if engine_config_path.exists()
            else EngineConfig.default()
        )
        self.projection_config = (
            ProjectionConfig.from_file(projection_config_path)
            if projection_config_path.exists()
            else ProjectionConfig.full_canonical()
        )

        self._csv_adapter = RecruiterCSVAdapter()
        self._resume_adapter = ResumeAdapter()
        self._engine = DecisionEngine(self.engine_config)
        self._projector = Projector(self.projection_config)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        csv_path: Path | None = None,
        resume_dir: Path | None = None,
        resume_files: list[Path] | None = None,
    ) -> PipelineOutput:
        """
        Execute the full pipeline. Returns PipelineOutput.

        Args:
            csv_path      : path to a recruiter CSV file
            resume_dir    : directory of resume files (all supported files processed)
            resume_files  : explicit list of individual resume files
        """
        all_records: list[SourceRecord] = []

        # Step 2: Parse
        if csv_path:
            logger.info("Parsing CSV: %s", csv_path)
            records = self._csv_adapter.safe_parse(csv_path)
            all_records.extend(records)
            logger.info("  → %d record(s) from CSV", len(records))

        if resume_dir:
            dir_files = self._collect_resume_files(resume_dir)
            logger.info("Found %d resume file(s) in %s", len(dir_files), resume_dir)
            for rf in dir_files:
                records = self._resume_adapter.safe_parse(rf)
                all_records.extend(records)

        if resume_files:
            for rf in resume_files:
                logger.info("Parsing resume: %s", rf)
                records = self._resume_adapter.safe_parse(rf)
                all_records.extend(records)

        if not all_records:
            logger.warning("No records parsed — returning empty output")
            return PipelineOutput(summary=RunSummary())

        # Step 3: Normalize — track stats for display
        all_records, norm_phones, norm_skills = self._normalize_records(all_records)

        # Step 4: Decision Engine
        results = self._engine.process(all_records)
        logger.info("Decision engine: produced %d profile(s)", len(results))

        # Step 5: Project + build summary
        profiles: list[CanonicalProfile] = []
        projected: list[dict[str, Any]] = []
        total_conflicts = sum(len(r.profile.conflict_log) for r in results)
        validation_failures = getattr(self._engine, "_last_validation_failures", 0)
        raw_rejections = getattr(self._engine, "_last_validation_rejections", [])
        validation_rejections = [r.to_dict() for r in raw_rejections]

        summary = RunSummary(
            total=len(results),
            total_conflicts=total_conflicts,
            validation_failures=validation_failures,
            validation_rejections=validation_rejections,
            normalized_phones=norm_phones,
            normalized_skills=norm_skills,
        )

        for result in results:
            profile = result.profile
            profiles.append(profile)

            try:
                out = self._projector.project(profile)
                errors = self._projector.validate_output(out)
                if errors:
                    logger.warning("Projection validation errors for %s: %s",
                                   profile.candidate_id, errors)
                projected.append(out)
            except Exception as exc:
                logger.error("Projection failed for %s: %s", profile.candidate_id, exc)
                projected.append({
                    "candidate_id": profile.candidate_id,
                    "error": str(exc),
                })

            if profile.status == CandidateStatus.ACTIVE:
                summary.active += 1
            elif profile.status == CandidateStatus.MANUAL_REVIEW:
                summary.manual_review += 1

        return PipelineOutput(
            profiles=profiles,
            projected=projected,
            summary=summary,
            decision_results=results,
        )

    # ------------------------------------------------------------------
    # Output writing
    # ------------------------------------------------------------------

    def write_output(
        self,
        output: PipelineOutput,
        output_path: Path,
        pretty: bool = True,
    ) -> None:
        """Write projected profiles + run summary to a JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "summary": {
                "total": output.summary.total,
                "active": output.summary.active,
                "manual_review": output.summary.manual_review,
                "errors": output.summary.errors,
                "validation_failures": output.summary.validation_failures,
                "validation_rejections": output.summary.validation_rejections,
            },
            "candidates": output.projected,
        }

        indent = 2 if pretty else None
        output_path.write_text(
            json.dumps(payload, indent=indent, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Output written to %s", output_path)

    # ------------------------------------------------------------------
    # Normalization pass
    # ------------------------------------------------------------------

    def _normalize_records(
        self, records: list[SourceRecord]
    ) -> tuple[list[SourceRecord], int, list[str]]:
        """
        Apply all normalizers to SourceRecord fields in-place.

        Returns:
            (records, phones_normalized_count, skill_mapping_examples)
        """
        region = self.engine_config.validation.phone_default_region
        phones_normalized = 0
        skill_examples: list[str] = []
        seen_skill_examples: set[str] = set()

        for record in records:
            # Phones
            for rf in record.phones:
                if rf.value:
                    raw = str(rf.value)
                    normalized = normalize_phone(raw, region)
                    if normalized and normalized != raw:
                        rf.value = normalized
                        phones_normalized += 1
                    elif normalized:
                        rf.value = normalized

            # Emails — lowercase
            for rf in record.emails:
                if rf.value:
                    rf.value = str(rf.value).strip().lower()

            # Names — collapse internal whitespace
            if record.full_name and record.full_name.value:
                record.full_name.value = normalize_person_name(str(record.full_name.value))

            # Location
            if record.location_raw and record.location_raw.value:
                raw_loc = str(record.location_raw.value)
                parse_location_string(raw_loc)
                record.location_raw.value = raw_loc  # keep raw string; engine parses again

            # Skills — track canonicalization examples
            for rf in record.skills_raw:
                if rf.value:
                    raw_skill = str(rf.value)
                    canonical = normalize_skill(raw_skill)
                    if canonical != raw_skill:
                        example = f"{raw_skill} → {canonical}"
                        if example not in seen_skill_examples:
                            seen_skill_examples.add(example)
                            skill_examples.append(example)
                    rf.value = canonical

            # Experience dates are validated in the Decision Engine — do not pre-strip here

        return records, phones_normalized, skill_examples

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_resume_files(self, resume_dir: Path) -> list[Path]:
        """Return all supported resume files in resume_dir (non-recursive)."""
        files = [
            f for f in resume_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _RESUME_EXTENSIONS
        ]
        logger.info("Collected %d resume file(s)", len(files))
        return sorted(files)
