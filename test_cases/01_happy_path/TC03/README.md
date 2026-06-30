# TC03 — Happy Path: Multiple Independent Candidates

## Purpose
Verify the pipeline processes multiple unrelated candidates in a single CSV without confusing them.

## Modules Validated
- CSV adapter (multi-row parsing)
- Candidate Matcher (correctly produces N groups for N independent identities)
- Country normalization for international candidates (UK → GB)
- Phone normalization across regions (IN, GB)

## Why correct
- Three rows with three distinct emails, phones, names → three groups, three profiles.
- Diya (Hyderabad) and Rohan (Chennai) have only city — country parsed as null is honest.
- Sara has "London, UK" → city=London, country=GB (alias mapping).
- UK number `+447911123456` is valid E.164 → no normalization change.
- No conflicts → all three `AUTO_APPROVED`.
