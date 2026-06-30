"""Raw parsed output from one adapter for one candidate.

All values here are pre-normalization, pre-validation, pre-merge.
Each field carries its source and extraction method for downstream trust scoring.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    RECRUITER_CSV = "recruiter_csv"
    ATS_JSON = "ats_json"
    RESUME = "resume"


class ExtractionMethod(str, Enum):
    DIRECT = "direct"        # direct column / structured field
    REGEX = "regex"          # extracted via regular expression
    HEURISTIC = "heuristic"  # section-based or positional heuristic


class RawField(BaseModel):
    """A single extracted field with its provenance metadata."""

    value: Any
    source: SourceType
    extraction_method: ExtractionMethod = ExtractionMethod.DIRECT
    raw_text: str | None = None


class SourceRecord(BaseModel):
    """
    Complete raw output for one candidate from one adapter.
    Produced by adapters; consumed by the normalize → validate → Decision Engine chain.
    """

    source_type: SourceType
    source_file: str | None = None

    # Identity fields
    full_name: RawField | None = None
    emails: list[RawField] = Field(default_factory=list)
    phones: list[RawField] = Field(default_factory=list)

    # Profile fields
    headline: RawField | None = None
    location_raw: RawField | None = None
    years_experience: RawField | None = None
    current_company: RawField | None = None
    current_title: RawField | None = None

    # Links
    linkedin_url: RawField | None = None
    github_url: RawField | None = None
    leetcode_url: RawField | None = None
    portfolio_url: RawField | None = None

    # Structured lists — value is a dict with field-specific keys
    skills_raw: list[RawField] = Field(default_factory=list)
    experience_raw: list[RawField] = Field(default_factory=list)
    projects_raw: list[RawField] = Field(default_factory=list)
    education_raw: list[RawField] = Field(default_factory=list)

    # Adapter diagnostics
    parse_errors: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
