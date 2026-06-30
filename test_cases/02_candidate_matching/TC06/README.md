# TC06 — Matching: Near-Threshold Score

## Purpose
Exercise the ReviewQueue trigger NEAR_THRESHOLD_MATCH — when a match is uncertain, flag for human review instead of silently merging or silently separating.

## Modules Validated
- CandidateMatcher decision boundary (`MANUAL_REVIEW` decision branch)
- ReviewQueue._check_near_threshold_match
- Profile status transition to MANUAL_REVIEW

## Why correct
- Identity signals (email, phone) don't match.
- Name + company give a moderate score (~0.40–0.50 × weight 0.5) that may sit between (threshold − margin) and threshold.
- The system MUST escalate rather than guess: this is the system's "I don't know — ask a human" path.
- `review_reasons` populated with the trigger code.
