"""Tests for candidate matching."""

import pytest

from src.decision.matcher import CandidateMatcher, MatchDecision
from src.models.engine_config import EngineConfig
from src.models.source_record import ExtractionMethod, RawField, SourceRecord, SourceType


@pytest.fixture
def matcher(engine_config):
    return CandidateMatcher(engine_config)


def make_record(name=None, email=None, phone=None, company=None, source=SourceType.RECRUITER_CSV):
    r = SourceRecord(source_type=source)
    if name:
        r.full_name = RawField(value=name, source=source, extraction_method=ExtractionMethod.DIRECT)
    if email:
        r.emails = [RawField(value=email, source=source, extraction_method=ExtractionMethod.DIRECT)]
    if phone:
        r.phones = [RawField(value=phone, source=source, extraction_method=ExtractionMethod.DIRECT)]
    if company:
        r.current_company = RawField(value=company, source=source, extraction_method=ExtractionMethod.DIRECT)
    return r


class TestCandidateMatcher:
    def test_email_match_yields_merge(self, matcher):
        a = make_record(email="jane@example.com")
        b = make_record(email="jane@example.com", source=SourceType.RESUME)
        result = matcher.compare(a, b)
        assert result.decision == MatchDecision.MERGE

    def test_phone_match_yields_merge(self, matcher):
        a = make_record(phone="+919876543210")
        b = make_record(phone="+919876543210", source=SourceType.RESUME)
        result = matcher.compare(a, b)
        assert result.decision == MatchDecision.MERGE

    def test_different_emails_yields_separate(self, matcher):
        a = make_record(email="alice@example.com")
        b = make_record(email="bob@example.com")
        result = matcher.compare(a, b)
        assert result.decision == MatchDecision.SEPARATE

    def test_no_overlap_yields_separate(self, matcher):
        a = make_record(name="Alice Johnson")
        b = make_record(name="Bob Lee")
        result = matcher.compare(a, b)
        assert result.decision == MatchDecision.SEPARATE

    def test_grouping_two_same_person(self, matcher):
        a = make_record(email="jane@example.com")
        b = make_record(email="jane@example.com", source=SourceType.RESUME)
        groups = matcher.group_records([a, b])
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_grouping_two_different_people(self, matcher):
        a = make_record(email="alice@example.com")
        b = make_record(email="bob@example.com")
        groups = matcher.group_records([a, b])
        assert len(groups) == 2
