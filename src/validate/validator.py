"""Pre-merge validation gate.

Runs AFTER normalization, BEFORE candidate matching.
Rejects invalid field values so they never enter the Decision Engine.
Invalid values are removed from SourceRecord and logged as ValidationRejection.
Pipeline never crashes — errors are collected and surfaced in ValidationResult.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.engine_config import EngineConfig
from src.models.source_record import RawField, SourceRecord
from src.normalize.dates import normalize_date
from src.normalize.phones import normalize_phone
from src.utils.logging import get_logger

logger = get_logger(__name__)

# RFC-ish email pattern — good enough for production filtering
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


@dataclass
class ValidationRejection:
    field: str
    raw_value: str
    reason: str
    reason_code: str

    def to_dict(self) -> dict[str, str]:
        """Serialize for JSON output and console summary."""
        entry: dict[str, str] = {
            "field": self.field,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }
        if self.raw_value and self.raw_value != "<redacted>":
            entry["raw_value"] = self.raw_value
        return entry


@dataclass
class ValidationResult:
    record: SourceRecord
    rejections: list[ValidationRejection] = field(default_factory=list)

    @property
    def has_rejections(self) -> bool:
        return len(self.rejections) > 0


class Validator:
    """
    Validates and cleans a SourceRecord.
    Returns a new ValidationResult with a cleaned record copy and all rejections logged.
    """

    def __init__(self, config: EngineConfig) -> None:
        self.config = config

    def validate(self, record: SourceRecord) -> ValidationResult:
        """
        Run all validation checks on a SourceRecord.
        Returns ValidationResult with cleaned record and list of rejections.
        """
        rejections: list[ValidationRejection] = []

        valid_emails, email_rejections = self._validate_emails(record)
        rejections.extend(email_rejections)

        valid_phones, phone_rejections = self._validate_phones(record)
        rejections.extend(phone_rejections)

        valid_skills, skill_rejections = self._validate_skills(record)
        rejections.extend(skill_rejections)

        valid_experience, exp_rejections = self._validate_experience(record)
        rejections.extend(exp_rejections)

        # Mutate record fields with only the valid values
        record.emails = valid_emails
        record.phones = valid_phones
        record.skills_raw = valid_skills
        record.experience_raw = valid_experience

        if rejections:
            logger.debug(
                "Validation: %d rejection(s) in record from %s",
                len(rejections),
                record.source_file or record.source_type,
            )

        return ValidationResult(record=record, rejections=rejections)

    # ------------------------------------------------------------------
    # Email validation
    # ------------------------------------------------------------------

    def _validate_emails(
        self, record: SourceRecord
    ) -> tuple[list[RawField], list[ValidationRejection]]:
        valid: list[RawField] = []
        rejections: list[ValidationRejection] = []
        max_len = self.config.validation.email_max_length

        for rf in record.emails:
            raw_val = str(rf.value).strip() if rf.value else ""
            if not raw_val:
                rejections.append(ValidationRejection(
                    field="email", raw_value=raw_val,
                    reason="Empty email value", reason_code="INVALID_EMAIL_FORMAT",
                ))
                continue
            if len(raw_val) > max_len:
                rejections.append(ValidationRejection(
                    field="email", raw_value="<redacted>",
                    reason=f"Email exceeds {max_len} characters", reason_code="INVALID_EMAIL_FORMAT",
                ))
                continue
            if " " in raw_val:
                rejections.append(ValidationRejection(
                    field="email", raw_value=raw_val,
                    reason="Email contains spaces", reason_code="INVALID_EMAIL_FORMAT",
                ))
                continue
            if not _EMAIL_RE.match(raw_val):
                rejections.append(ValidationRejection(
                    field="email", raw_value=raw_val,
                    reason="Email does not match expected pattern", reason_code="INVALID_EMAIL_FORMAT",
                ))
                continue
            # Normalise to lowercase in place
            rf.value = raw_val.lower()
            valid.append(rf)

        return valid, rejections

    # ------------------------------------------------------------------
    # Phone validation
    # ------------------------------------------------------------------

    def _validate_phones(
        self, record: SourceRecord
    ) -> tuple[list[RawField], list[ValidationRejection]]:
        valid: list[RawField] = []
        rejections: list[ValidationRejection] = []
        region = self.config.validation.phone_default_region

        for rf in record.phones:
            raw_val = str(rf.value).strip() if rf.value else ""
            if not raw_val:
                continue
            normalized = normalize_phone(raw_val, region)
            if normalized is None:
                rejections.append(ValidationRejection(
                    field="phone", raw_value=raw_val,
                    reason="Phone number could not be parsed to E.164",
                    reason_code="INVALID_PHONE",
                ))
                continue
            rf.value = normalized
            valid.append(rf)

        return valid, rejections

    # ------------------------------------------------------------------
    # Skill validation
    # ------------------------------------------------------------------

    def _validate_skills(
        self, record: SourceRecord
    ) -> tuple[list[RawField], list[ValidationRejection]]:
        valid: list[RawField] = []
        rejections: list[ValidationRejection] = []

        for rf in record.skills_raw:
            raw_val = str(rf.value).strip() if rf.value else ""
            if not raw_val:
                rejections.append(ValidationRejection(
                    field="skill", raw_value="",
                    reason="Empty skill string", reason_code="EMPTY_SKILL",
                ))
                continue
            valid.append(rf)

        return valid, rejections

    # ------------------------------------------------------------------
    # Experience date validation
    # ------------------------------------------------------------------

    def _validate_experience(
        self, record: SourceRecord
    ) -> tuple[list[RawField], list[ValidationRejection]]:
        valid: list[RawField] = []
        rejections: list[ValidationRejection] = []
        min_y = self.config.validation.date_min_year
        max_y = self.config.validation.date_max_year

        for rf in record.experience_raw:
            entry: dict = rf.value if isinstance(rf.value, dict) else {}
            cleaned = dict(entry)
            entry_valid = True

            for date_key in ("start", "end"):
                raw_date = entry.get(date_key, "")
                if not raw_date:
                    continue
                nd = normalize_date(str(raw_date))
                if nd is None:
                    # "Present" for end is fine; otherwise reject
                    if date_key == "end":
                        cleaned[date_key] = None
                    else:
                        rejections.append(ValidationRejection(
                            field=f"experience.{date_key}",
                            raw_value=str(raw_date),
                            reason="Unparseable date in experience",
                            reason_code="INVALID_DATE",
                        ))
                        entry_valid = False
                        break
                else:
                    year = int(nd[:4])
                    if not (min_y <= year <= max_y):
                        rejections.append(ValidationRejection(
                            field=f"experience.{date_key}",
                            raw_value=str(raw_date),
                            reason=f"Year {year} out of range [{min_y}, {max_y}]",
                            reason_code="INVALID_DATE",
                        ))
                        entry_valid = False
                        break
                    cleaned[date_key] = nd

            if entry_valid:
                rf.value = cleaned
                valid.append(rf)

        return valid, rejections

    # ------------------------------------------------------------------
    # Convenience: validate a single date string
    # ------------------------------------------------------------------

    def validate_date_string(
        self, raw_value: str, field_name: str
    ) -> tuple[str | None, ValidationRejection | None]:
        """Validate a single date string. Returns (normalized, rejection_or_None)."""
        if not raw_value:
            return None, None
        min_y = self.config.validation.date_min_year
        max_y = self.config.validation.date_max_year
        nd = normalize_date(raw_value)
        if nd is None:
            return None, ValidationRejection(
                field=field_name, raw_value=raw_value,
                reason="Unparseable date", reason_code="INVALID_DATE",
            )
        year = int(nd[:4])
        if not (min_y <= year <= max_y):
            return None, ValidationRejection(
                field=field_name, raw_value=raw_value,
                reason=f"Year {year} out of [{min_y}, {max_y}]",
                reason_code="INVALID_DATE",
            )
        return nd, None
