# TC04 — Matching: Completely Different Identities

## Purpose
Ensure the matcher does NOT merge unrelated candidates.

## Modules Validated
- CandidateMatcher.group_records (union-find correctness)
- All three match keys returning 0

## Why correct
- Different names, emails, phones, companies → all three match signals score 0.0.
- Decision = SEPARATE → matcher keeps them in separate groups.
- Two profiles emitted.
