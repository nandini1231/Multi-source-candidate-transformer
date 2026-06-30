# TC08 — Conflict Resolution: HIGH Severity / Manual Review

## Purpose
The classic false-merge scenario: a shared phone, but entirely different name and email. The pipeline must NOT silently merge — it must escalate.

## Modules Validated
- SeverityClassifier.classify_name → HIGH (zero token overlap)
- SeverityClassifier.classify_email → HIGH (different local + domain)
- ReviewQueue.SAME_PHONE_DIFF_IDENTITY trigger
- Profile.status transition to MANUAL_REVIEW

## Why correct
- Phone signal alone is insufficient when name+email are both completely different.
- The system produces a best-effort merged profile but flags it `manual_review` so a recruiter can decide.
- `review_reasons` populated for explainability.
