# TC01 — Matching: Same Email, Different Names

## Purpose
When two sources share the same email but have name variants ("Robert" vs "Bob"), the matcher MUST merge them as one candidate; the resolver picks the higher-priority source for the name.

## Modules Validated
- CandidateMatcher.email_match_score → returns 1.0 → MERGE decision
- SeverityClassifier.classify_name → MEDIUM (token "James" overlaps)
- FieldResolver.resolve_scalar → CSV wins by source priority
- ConflictEntry logged with severity MEDIUM

## Why correct
- Email key is the strongest match signal (weight 1.0) → score above merge_decision_threshold.
- "Robert" and "Bob" share the token "James" → not HIGH, but not LOW either → MEDIUM.
- MEDIUM conflict on full_name does not trigger manual review (only HIGH on identity fields does).
- Status remains `AUTO_APPROVED` with a conflict entry recorded for audit.
