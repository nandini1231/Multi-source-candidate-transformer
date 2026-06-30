# TC03 — Matching: Similar Names + Matching Company

## Purpose
Test the fallback matching path when neither email nor phone match: fuzzy name + normalised company.

## Modules Validated
- helpers.normalize_name_key, normalize_company_key
- CandidateMatcher._name_company_match_score
- Decision threshold and review margin behaviour

## Why correct
- Email + phone don't overlap (different addresses/numbers).
- "Sneha Patel" vs "Sneha S Patel" → high token-set ratio.
- "Wipro" vs "Wipro Limited" → company keys equal after suffix stripping.
- name+company raw score ≈ 0.70; weighted score = 0.70 × 0.5 = **0.35**, below merge threshold (0.75).
- **Correct outcome: SEPARATE → 2 profiles.** Principle: false merge is worse than a duplicate.
