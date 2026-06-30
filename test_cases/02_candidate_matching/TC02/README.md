# TC02 — Matching: Same Phone, Different Emails

## Purpose
Verify phone is a sufficient match signal even when emails differ — both emails are unioned.

## Modules Validated
- CandidateMatcher.phone_match_score
- FieldResolver.resolve_emails (union dedupe, no conflict)
- Phone normalization equivalence (`+91 98989 89898` → `+919898989898`)

## Why correct
- Same E.164 phone → phone_match_score = 1.0 × weight 0.9 = 0.9 → above threshold → MERGE.
- Different emails are simply added to the union list, not treated as a conflict.
- Name and company also agree → additional confidence boost.
- No HIGH conflicts → `AUTO_APPROVED`.
