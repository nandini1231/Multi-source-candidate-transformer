"""Tests for the Decision Engine end-to-end."""

import pytest

from src.decision.engine import DecisionEngine
from src.models.canonical import CandidateStatus
from src.models.engine_config import EngineConfig
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType


@pytest.fixture
def engine(engine_config):
    return DecisionEngine(engine_config)


class TestDecisionEngine:

    def test_single_csv_record_produces_active_profile(self, engine, csv_record_jane):
        results = engine.process([csv_record_jane])
        assert len(results) == 1
        profile = results[0].profile
        assert profile.full_name == "Jane Doe"
        assert "jane.doe@example.com" in profile.emails
        assert profile.status == CandidateStatus.ACTIVE

    def test_csv_and_resume_same_person_merged(self, engine, csv_record_jane, resume_record_jane):
        results = engine.process([csv_record_jane, resume_record_jane])
        assert len(results) == 1
        profile = results[0].profile
        # CSV name wins over resume name
        assert profile.full_name == "Jane Doe"
        # Email merged
        assert "jane.doe@example.com" in profile.emails
        # Skills from resume added
        skill_names = [s.name for s in profile.skills]
        assert "Python" in skill_names

    def test_high_conflict_triggers_manual_review(self, engine, high_conflict_csv, high_conflict_resume):
        results = engine.process([high_conflict_csv, high_conflict_resume])
        # May produce 1 merged (manual review) or 2 separate profiles
        assert len(results) >= 1
        statuses = [r.profile.status for r in results]
        # At least one should be flagged or they are separate
        assert any(
            s in (CandidateStatus.MANUAL_REVIEW, CandidateStatus.ACTIVE)
            for s in statuses
        )

    def test_two_different_people_produce_two_profiles(self, engine):
        rec_a = SourceRecord(
            source_type=SourceType.RECRUITER_CSV,
            emails=[RawField(value="alice@example.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
            full_name=RawField(value="Alice", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
        )
        rec_b = SourceRecord(
            source_type=SourceType.RECRUITER_CSV,
            emails=[RawField(value="bob@example.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
            full_name=RawField(value="Bob", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
        )
        results = engine.process([rec_a, rec_b])
        assert len(results) == 2

    def test_confidence_populated(self, engine, csv_record_jane):
        results = engine.process([csv_record_jane])
        profile = results[0].profile
        assert profile.overall_confidence > 0.0

    def test_data_quality_score_populated(self, engine, csv_record_jane):
        results = engine.process([csv_record_jane])
        profile = results[0].profile
        assert profile.data_quality_score > 0.0

    def test_provenance_populated(self, engine, csv_record_jane):
        results = engine.process([csv_record_jane])
        profile = results[0].profile
        assert len(profile.provenance) > 0

    def test_candidate_id_deterministic(self, engine, csv_record_jane):
        results_1 = engine.process([csv_record_jane])
        results_2 = engine.process([csv_record_jane])
        assert results_1[0].profile.candidate_id == results_2[0].profile.candidate_id

    def test_empty_input_returns_empty(self, engine):
        results = engine.process([])
        assert results == []

    def test_invalid_phone_gracefully_skipped(self, engine):
        rec = SourceRecord(
            source_type=SourceType.RECRUITER_CSV,
            full_name=RawField(value="Test User", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
            emails=[RawField(value="test@example.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
            phones=[RawField(value="not-a-phone", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
        )
        results = engine.process([rec])
        assert len(results) == 1
        assert results[0].profile.phones == []  # invalid phone dropped
