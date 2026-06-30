"""Manual review queue.

The system does NOT guess when it cannot resolve confidently — it escalates.
The best-effort canonical profile is still produced but flagged as manual_review.

Triggers (config-driven via EngineConfig.review):
  1. Any HIGH-severity conflict on identity fields (email, phone, full_name)
  2. HIGH conflict count > auto_merge_max_high_severity_conflicts (default 0)
  3. Match score within flag_near_threshold_margin of merge_decision_threshold
  4. Same phone + completely different name AND email
  5. overall_confidence < min_confidence_without_review
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.decision.severity import ConflictSeverity
from src.models.engine_config import EngineConfig
from src.utils.logging import get_logger

logger = get_logger(__name__)

_IDENTITY_FIELDS = frozenset({"emails", "email", "phones", "phone", "full_name"})


@dataclass
class ReviewTrigger:
    trigger_code: str
    description: str
    field: str | None = None


@dataclass
class ReviewDecision:
    requires_review: bool
    triggers: list[ReviewTrigger] = field(default_factory=list)

    @property
    def summary_reasons(self) -> list[str]:
        return [t.description for t in self.triggers]


class ReviewQueue:
    """Evaluates whether a candidate requires manual review."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config

    def evaluate(
        self,
        conflict_severities: dict[str, ConflictSeverity],
        match_score: float,
        overall_confidence: float,
        same_phone_diff_identity: bool = False,
    ) -> ReviewDecision:
        """
        Evaluate all review triggers and return a ReviewDecision.

        Args:
            conflict_severities : {field_name: severity} for each conflicted field
            match_score         : candidate matching score (0–1)
            overall_confidence  : merged profile overall confidence
            same_phone_diff_identity : phone matched but name+email are both different
        """
        triggers: list[ReviewTrigger] = []

        triggers.extend(self._check_high_severity_conflicts(conflict_severities))
        t = self._check_near_threshold_match(match_score)
        if t:
            triggers.append(t)
        t = self._check_confidence_floor(overall_confidence)
        if t:
            triggers.append(t)
        if same_phone_diff_identity:
            triggers.append(ReviewTrigger(
                trigger_code="SAME_PHONE_DIFF_IDENTITY",
                description="Same phone number but completely different name and email",
            ))

        requires = len(triggers) > 0
        if requires:
            logger.info("Manual review flagged: %s", [t.trigger_code for t in triggers])

        return ReviewDecision(requires_review=requires, triggers=triggers)

    # ------------------------------------------------------------------
    # Individual trigger checks
    # ------------------------------------------------------------------

    def _check_high_severity_conflicts(
        self, conflict_severities: dict[str, ConflictSeverity]
    ) -> list[ReviewTrigger]:
        triggers: list[ReviewTrigger] = []
        max_allowed = self.config.review.auto_merge_max_high_severity_conflicts
        high_count = 0

        for field_name, severity in conflict_severities.items():
            if severity == ConflictSeverity.HIGH:
                high_count += 1
                if field_name.lower() in _IDENTITY_FIELDS:
                    triggers.append(ReviewTrigger(
                        trigger_code="HIGH_SEVERITY_IDENTITY_CONFLICT",
                        description=f"HIGH-severity conflict on identity field '{field_name}'",
                        field=field_name,
                    ))

        if high_count > max_allowed and not triggers:
            triggers.append(ReviewTrigger(
                trigger_code="TOO_MANY_HIGH_CONFLICTS",
                description=f"Total HIGH conflicts ({high_count}) exceeds limit ({max_allowed})",
            ))

        return triggers

    def _check_near_threshold_match(self, match_score: float) -> ReviewTrigger | None:
        threshold = self.config.matching.merge_decision_threshold
        margin = self.config.review.flag_near_threshold_margin

        if threshold - margin <= match_score < threshold:
            return ReviewTrigger(
                trigger_code="NEAR_THRESHOLD_MATCH",
                description=(
                    f"Match score {match_score:.3f} is near threshold "
                    f"{threshold} (margin ±{margin})"
                ),
            )
        return None

    def _check_confidence_floor(self, overall_confidence: float) -> ReviewTrigger | None:
        floor = self.config.review.min_confidence_without_review
        if overall_confidence < floor:
            return ReviewTrigger(
                trigger_code="LOW_CONFIDENCE",
                description=(
                    f"Overall confidence {overall_confidence:.3f} < minimum {floor}"
                ),
            )
        return None
