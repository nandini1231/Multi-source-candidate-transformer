"""Pydantic model for engine_config.json."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class MatchingConfig(BaseModel):
    email_match_weight: float = 1.0
    phone_match_weight: float = 0.9
    name_company_match_weight: float = 0.5
    merge_decision_threshold: float = 0.75
    fuzzy_name_min_ratio: int = 85


class ReviewConfig(BaseModel):
    auto_merge_max_high_severity_conflicts: int = 0
    min_confidence_without_review: float = 0.60
    flag_near_threshold_margin: float = 0.05


class QualityFieldsConfig(BaseModel):
    required: list[str] = Field(default_factory=lambda: ["full_name", "emails", "phones"])
    important: list[str] = Field(
        default_factory=lambda: ["skills", "experience", "education", "headline", "location"]
    )
    required_weight: float = 0.5
    important_weight: float = 0.5


class ValidationConfig(BaseModel):
    email_max_length: int = 254
    phone_default_region: str = "IN"
    date_min_year: int = 1950
    date_max_year: int = 2030


class EngineConfig(BaseModel):
    source_priority: dict[str, int] = Field(
        default_factory=lambda: {"recruiter_csv": 100, "ats_json": 90, "resume": 70}
    )
    confidence_weights: dict[str, float] = Field(
        default_factory=lambda: {"recruiter_csv": 0.95, "ats_json": 0.90, "resume": 0.70}
    )
    extraction_certainty: dict[str, float] = Field(
        default_factory=lambda: {"direct": 1.0, "regex": 0.70, "heuristic": 0.50}
    )
    severity_factors: dict[str, float] = Field(
        default_factory=lambda: {"LOW": 1.0, "MEDIUM": 0.85, "HIGH": 0.40}
    )
    agreement_factors: dict[str, float] = Field(
        default_factory=lambda: {
            "all_sources_agree": 1.0,
            "single_source": 0.95,
            "conflict_penalty": 0.80,
        }
    )
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    quality_fields: QualityFieldsConfig = Field(default_factory=QualityFieldsConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)

    @classmethod
    def from_file(cls, path: Path) -> "EngineConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})

    @classmethod
    def default(cls) -> "EngineConfig":
        return cls()
