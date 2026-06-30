# TC01 — Conflict Resolution: Name Conflict (MEDIUM)

## Purpose
"Sanjay Rao" vs "Sanjay K. Rao" — same person, slight name variant.

## Modules Validated
- SeverityClassifier.classify_name → MEDIUM (high token overlap)
- FieldResolver.resolve_scalar → CSV wins (priority 100 > 70)
- ConflictEntry recorded with reason

## Why correct
- Both share full token "Sanjay" and "Rao" → above MEDIUM cutoff.
- CSV picked due to higher source priority.
- Logged as MEDIUM, NOT HIGH, so no manual review.
