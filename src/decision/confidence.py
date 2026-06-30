"""Confidence calculator.

Per-field formula (all weights from EngineConfig — nothing hardcoded):

    field_confidence =
        confidence_weights[source]
        × extraction_certainty[method]
        × severity_factors[severity]
        × agreement_factor

overall_confidence = weighted average over PRESENT fields only.
Missing fields do NOT inflate the score.
Every step is recorded in ConfidenceDetail.reason[] for full explainability.
"""

from __future__ import annotations

from src.decision.severity import ConflictSeverity
from src.models.canonical import ConfidenceDetail
from src.models.engine_config import EngineConfig


class ConfidenceCalculator:

    def __init__(self, config: EngineConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Per-field confidence
    # ------------------------------------------------------------------

    def field_confidence(
        self,
        field_name: str,
        value: object,
        source: str,
        extraction_method: str,
        severity: ConflictSeverity,
        agreement: str,  # "all_sources_agree" | "single_source" | "conflict_penalty"
    ) -> ConfidenceDetail:
        """
        Compute confidence for a single resolved field value.
        Returns ConfidenceDetail with score + step-by-step explanation.
        """
        base = self._get_base_weight(source)
        certainty = self._get_extraction_certainty(extraction_method)
        sev_factor = self._get_severity_factor(severity)
        agree_factor = self._get_agreement_factor(agreement)

        score = round(min(base * certainty * sev_factor * agree_factor, 1.0), 4)

        reason = [
            f"Base weight ({source}): {base}",
            f"Extraction certainty ({extraction_method}): {certainty}",
            f"Severity factor ({severity.value}): {sev_factor}",
            f"Agreement factor ({agreement}): {agree_factor}",
            f"Final: {base} × {certainty} × {sev_factor} × {agree_factor} = {score}",
        ]

        return ConfidenceDetail(
            field=field_name,
            value=value,
            confidence=score,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Overall confidence
    # ------------------------------------------------------------------

    def overall_confidence(self, field_details: list[ConfidenceDetail]) -> float:
        """
        Weighted average over present fields only.
        Fields with None value are excluded so missing data doesn't inflate the score.
        """
        present = [fd for fd in field_details if fd.value is not None]
        if not present:
            return 0.0
        total = sum(fd.confidence for fd in present)
        return round(total / len(present), 4)

    # ------------------------------------------------------------------
    # Config lookups
    # ------------------------------------------------------------------

    def _get_base_weight(self, source: str) -> float:
        return self.config.confidence_weights.get(source, 0.5)

    def _get_extraction_certainty(self, method: str) -> float:
        return self.config.extraction_certainty.get(method, 0.5)

    def _get_severity_factor(self, severity: ConflictSeverity) -> float:
        return self.config.severity_factors.get(severity.value, 1.0)

    def _get_agreement_factor(self, agreement: str) -> float:
        return self.config.agreement_factors.get(agreement, 1.0)
