"""Tests for the Projector."""

import pytest

from src.decision.engine import DecisionEngine
from src.models.canonical import CanonicalProfile, CandidateStatus, Location, Skill
from src.models.projection_config import ProjectionConfig, ProjectionField
from src.project.projector import Projector, ProjectionError


def _make_profile(**kwargs) -> CanonicalProfile:
    defaults = {
        "candidate_id": "cand_test",
        "full_name": "Jane Doe",
        "emails": ["jane@example.com"],
        "phones": ["+919876543210"],
    }
    defaults.update(kwargs)
    return CanonicalProfile(**defaults)


class TestProjector:

    def test_full_name_projected(self):
        cfg = ProjectionConfig(fields=[
            ProjectionField(path="full_name", type="string")
        ])
        p = Projector(cfg)
        out = p.project(_make_profile())
        assert out["full_name"] == "Jane Doe"

    def test_email_index_path(self):
        cfg = ProjectionConfig(fields=[
            ProjectionField(**{"path": "primary_email", "from": "emails[0]", "type": "string"})
        ])
        p = Projector(cfg)
        out = p.project(_make_profile())
        assert out["primary_email"] == "jane@example.com"

    def test_missing_field_null_on_missing_null(self):
        cfg = ProjectionConfig(
            fields=[ProjectionField(path="headline", type="string")],
            on_missing="null",
        )
        p = Projector(cfg)
        out = p.project(_make_profile())
        assert out["headline"] is None

    def test_missing_field_omit_on_missing_omit(self):
        cfg = ProjectionConfig(
            fields=[ProjectionField(path="headline", type="string")],
            on_missing="omit",
        )
        p = Projector(cfg)
        out = p.project(_make_profile())
        assert "headline" not in out

    def test_missing_required_field_raises_on_error(self):
        cfg = ProjectionConfig(
            fields=[ProjectionField(path="headline", type="string", required=True)],
            on_missing="error",
        )
        p = Projector(cfg)
        with pytest.raises(ProjectionError):
            p.project(_make_profile())

    def test_skill_list_extraction(self):
        profile = _make_profile(skills=[
            Skill(name="Python", confidence=0.9),
            Skill(name="React", confidence=0.8),
        ])
        cfg = ProjectionConfig(fields=[
            ProjectionField(**{"path": "skills", "from": "skills[].name", "type": "string[]"})
        ])
        p = Projector(cfg)
        out = p.project(profile)
        assert out["skills"] == ["Python", "React"]

    def test_confidence_injected_when_toggled(self):
        cfg = ProjectionConfig(fields=[], include_confidence=True)
        p = Projector(cfg)
        profile = _make_profile()
        profile.overall_confidence = 0.85
        out = p.project(profile)
        assert "overall_confidence" in out
        assert out["overall_confidence"] == 0.85

    def test_e164_normalization_applied(self):
        cfg = ProjectionConfig(fields=[
            ProjectionField(**{"path": "phone", "from": "phones[0]", "normalize": "E164"})
        ])
        p = Projector(cfg)
        profile = _make_profile(phones=["+919876543210"])
        out = p.project(profile)
        assert out["phone"] == "+919876543210"

    def test_alternative_emails_slice(self):
        profile = _make_profile(emails=[
            "p1@example.com",
            "p2@example.com",
            "p3@example.com",
        ])
        cfg = ProjectionConfig(fields=[
            ProjectionField(**{"path": "primary_email", "from": "emails[0]", "type": "string"}),
            ProjectionField(**{"path": "alternative_emails", "from": "emails[1:]", "type": "string[]"}),
            ProjectionField(**{"path": "all_emails", "from": "emails", "type": "string[]"}),
        ])
        p = Projector(cfg)
        out = p.project(profile)
        assert out["primary_email"] == "p1@example.com"
        assert out["alternative_emails"] == ["p2@example.com", "p3@example.com"]
        assert out["all_emails"] == ["p1@example.com", "p2@example.com", "p3@example.com"]

    def test_alternative_emails_empty_when_single(self):
        cfg = ProjectionConfig(fields=[
            ProjectionField(**{"path": "alternative_emails", "from": "emails[1:]", "type": "string[]"}),
        ])
        p = Projector(cfg)
        out = p.project(_make_profile())
        assert out["alternative_emails"] == []
