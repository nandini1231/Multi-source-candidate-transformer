"""Edge case tests — robustness and honest handling of bad input."""

import pytest

from src.decision.engine import DecisionEngine
from src.models.engine_config import EngineConfig
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType
from src.normalize.dates import normalize_date
from src.normalize.phones import normalize_phone
from src.normalize.skills import normalize_skill


class TestGarbageInputs:
    def test_garbage_phone_returns_none(self):
        assert normalize_phone("call me anytime") is None

    def test_garbage_phone_555_returns_none(self):
        assert normalize_phone("555") is None

    def test_garbage_date_returns_none(self):
        assert normalize_date("at some point last year") is None

    def test_empty_skill_normalizes(self):
        result = normalize_skill("   ")
        assert isinstance(result, str)


class TestMissingResumeForCSVRow:
    def test_csv_only_profile_has_lower_quality(self, engine_config):
        engine = DecisionEngine(engine_config)
        rec = SourceRecord(
            source_type=SourceType.RECRUITER_CSV,
            full_name=RawField(value="Alice", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
            emails=[RawField(value="alice@example.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
            phones=[RawField(value="+14155552671", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT)],
        )
        results = engine.process([rec])
        assert len(results) == 1
        # No skills/experience/education → quality < 1.0
        assert results[0].profile.data_quality_score < 1.0


class TestDuplicateSkills:
    def test_js_and_javascript_are_same_canonical(self):
        assert normalize_skill("JS") == normalize_skill("JavaScript")

    def test_reactjs_and_react_are_same_canonical(self):
        assert normalize_skill("ReactJS") == normalize_skill("React")

    def test_python_case_insensitive(self):
        assert normalize_skill("PYTHON") == normalize_skill("python") == "Python"


class TestCorruptRecord:
    def test_empty_record_does_not_crash(self, engine_config):
        engine = DecisionEngine(engine_config)
        empty = SourceRecord(source_type=SourceType.RESUME, source_file="corrupt.pdf")
        results = engine.process([empty])
        # Should produce one profile with no crash
        assert len(results) == 1


class TestInvalidEmailDropped:
    def test_invalid_email_not_in_profile(self, engine_config):
        engine = DecisionEngine(engine_config)
        rec = SourceRecord(
            source_type=SourceType.RECRUITER_CSV,
            full_name=RawField(value="Bob", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
            emails=[
                RawField(value="not-an-email", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
                RawField(value="bob@valid.com", source=SourceType.RECRUITER_CSV, extraction_method=ExtractionMethod.DIRECT),
            ],
        )
        results = engine.process([rec])
        assert len(results) == 1
        profile = results[0].profile
        assert "not-an-email" not in profile.emails
        assert "bob@valid.com" in profile.emails


class TestPresentDateHandling:
    def test_present_end_date_is_none(self):
        assert normalize_date("Present", allow_present=True) is None
        assert normalize_date("current", allow_present=True) is None

    def test_present_not_allowed_treated_as_garbage(self):
        result = normalize_date("Present", allow_present=False)
        assert result is None  # still None — not a valid date string
