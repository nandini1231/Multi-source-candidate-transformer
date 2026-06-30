"""Candidate data quality scorer — measures completeness, not trust.

Formula:
    quality_score =
        (filled_required / total_required  × required_weight)
      + (filled_important / total_important × important_weight)

Field definitions driven entirely by EngineConfig.quality_fields — nothing hardcoded.
"""

from __future__ import annotations

from src.models.canonical import CanonicalProfile, QualityBreakdown
from src.models.engine_config import EngineConfig


class QualityScorer:

    def __init__(self, config: EngineConfig) -> None:
        self.config = config

    def score(self, profile: CanonicalProfile) -> tuple[float, QualityBreakdown]:
        """
        Compute quality_score (0–1) and QualityBreakdown.

        Returns:
            (quality_score, QualityBreakdown)
        """
        qf = self.config.quality_fields
        required_fields = qf.required
        important_fields = qf.important

        req_filled = [f for f in required_fields if self._is_present(profile, f)]
        req_missing = [f for f in required_fields if not self._is_present(profile, f)]
        imp_filled = [f for f in important_fields if self._is_present(profile, f)]
        imp_missing = [f for f in important_fields if not self._is_present(profile, f)]

        req_score = (len(req_filled) / max(len(required_fields), 1)) * qf.required_weight
        imp_score = (len(imp_filled) / max(len(important_fields), 1)) * qf.important_weight

        quality = round(req_score + imp_score, 4)
        breakdown = QualityBreakdown(
            required_filled=req_filled,
            required_missing=req_missing,
            important_filled=imp_filled,
            important_missing=imp_missing,
        )
        return quality, breakdown

    def _is_present(self, profile: CanonicalProfile, field_name: str) -> bool:
        """Return True if a canonical field has a non-None, non-empty value."""
        value = getattr(profile, field_name, None)
        if value is None:
            return False
        if isinstance(value, list):
            return len(value) > 0
        if isinstance(value, str):
            return bool(value.strip())
        if hasattr(value, "__dict__"):
            # Pydantic sub-model: at least one non-None field
            return any(
                v is not None and v != "" and v != []
                for v in vars(value).values()
            )
        return True
