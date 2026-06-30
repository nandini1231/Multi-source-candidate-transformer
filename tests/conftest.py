"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models.engine_config import EngineConfig
from src.models.projection_config import ProjectionConfig
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType


@pytest.fixture
def engine_config() -> EngineConfig:
    return EngineConfig.default()


@pytest.fixture
def projection_config() -> ProjectionConfig:
    p = Path("config/projection_config.json")
    return ProjectionConfig.from_file(p) if p.exists() else ProjectionConfig()


@pytest.fixture
def csv_record_jane() -> SourceRecord:
    return SourceRecord(
        source_type=SourceType.RECRUITER_CSV,
        source_file="candidates.csv",
        full_name=RawField(value="Jane Doe", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
        emails=[RawField(value="jane.doe@example.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
        phones=[RawField(value="+919876543210", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
        current_company=RawField(value="Acme Corp", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
        current_title=RawField(value="Software Engineer", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
    )


@pytest.fixture
def resume_record_jane() -> SourceRecord:
    """Same person — overlapping email, name variant, extra skills."""
    return SourceRecord(
        source_type=SourceType.RESUME,
        source_file="jane.pdf",
        full_name=RawField(value="Jane A. Doe", source=SourceType.RESUME, extraction_method=ExtractionMethod.HEURISTIC),
        emails=[RawField(value="jane.doe@example.com", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX)],
        phones=[RawField(value="+919876543210", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX)],
        skills_raw=[
            RawField(value="Python", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX),
            RawField(value="ReactJS", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX),
        ],
    )


@pytest.fixture
def high_conflict_csv() -> SourceRecord:
    return SourceRecord(
        source_type=SourceType.RECRUITER_CSV,
        source_file="candidates.csv",
        full_name=RawField(value="John Smith", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
        emails=[RawField(value="john@gmail.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
        phones=[RawField(value="+14155552671", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
    )


@pytest.fixture
def high_conflict_resume() -> SourceRecord:
    """Same phone, completely different name + email — manual review trigger."""
    return SourceRecord(
        source_type=SourceType.RESUME,
        source_file="unknown.pdf",
        full_name=RawField(value="Rahul Sharma", source=SourceType.RESUME, extraction_method=ExtractionMethod.HEURISTIC),
        emails=[RawField(value="rahul@gmail.com", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX)],
        phones=[RawField(value="+14155552671", source=SourceType.RESUME, extraction_method=ExtractionMethod.REGEX)],
    )
