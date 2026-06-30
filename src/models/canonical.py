"""Canonical profile — the internal merged truth for one candidate.

Never sent to output directly. The Projector reads this and produces output JSON.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CandidateStatus(str, Enum):
    ACTIVE = "active"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Profile sub-models
# ---------------------------------------------------------------------------


class Location(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None  # ISO-3166 alpha-2
    inferred: bool = False
    inference_note: str | None = None


class Links(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    leetcode: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str                              # canonical skill name
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: str | None = None
    title: str | None = None
    start: str | None = None               # YYYY-MM
    end: str | None = None                 # YYYY-MM or null (present)
    summary: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)


class Project(BaseModel):
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    tech_stack: str | None = None
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    location: str | None = None
    start_year: str | None = None          # YYYY
    end_year: str | None = None            # YYYY
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Audit trail sub-models
# ---------------------------------------------------------------------------


class ProvenanceEntry(BaseModel):
    field: str
    source: str
    method: str


class ConflictEntry(BaseModel):
    field: str
    severity: str                           # LOW | MEDIUM | HIGH
    values: list[dict[str, Any]] = Field(default_factory=list)
    selected: Any = None
    reason: str = ""
    explanation: str = ""


class ConfidenceDetail(BaseModel):
    field: str
    value: Any = None
    confidence: float = 0.0
    reason: list[str] = Field(default_factory=list)


class FieldDecision(BaseModel):
    field: str
    source: str
    method: str
    reason_code: str
    reason_human: str
    alternates_rejected: list[dict[str, Any]] = Field(default_factory=list)


class QualityBreakdown(BaseModel):
    required_filled: list[str] = Field(default_factory=list)
    required_missing: list[str] = Field(default_factory=list)
    important_filled: list[str] = Field(default_factory=list)
    important_missing: list[str] = Field(default_factory=list)


class VersionSnapshot(BaseModel):
    version: int
    created_at: str
    sources: list[str] = Field(default_factory=list)
    snapshot_hash: str = ""


# ---------------------------------------------------------------------------
# Root canonical profile
# ---------------------------------------------------------------------------


class CanonicalProfile(BaseModel):
    candidate_id: str
    status: CandidateStatus = CandidateStatus.ACTIVE
    review_reasons: list[str] = Field(default_factory=list)

    # Core identity
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)

    # Profile
    location: Location = Field(default_factory=Location)
    headline: str | None = None
    years_experience: float | None = None
    links: Links = Field(default_factory=Links)

    # Structured data
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    # Audit trail
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    conflict_log: list[ConflictEntry] = Field(default_factory=list)
    field_decisions: list[FieldDecision] = Field(default_factory=list)
    confidence_details: list[ConfidenceDetail] = Field(default_factory=list)

    # Scores
    overall_confidence: float = 0.0
    data_quality_score: float = 0.0
    data_quality_breakdown: QualityBreakdown = Field(default_factory=QualityBreakdown)

    # Versioning
    current_version: int = 1
    versions: list[VersionSnapshot] = Field(default_factory=list)
