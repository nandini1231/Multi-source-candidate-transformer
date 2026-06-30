# TC01 — Normalization: Phone

## Purpose
All international and local phone formats reduce to E.164.

Five CSV rows are provided; Phone1–Phone3 share the same number in different formats and merge into one profile after normalization, yielding **3 final candidates**. All unique emails from merged rows are kept in the canonical `emails[]` array and projected as `primary_email` + `alternative_emails`.

## Modules Validated
- normalize_phone with multiple input shapes
- Default region (IN) fallback behaviour
- CandidateMatcher groups rows with identical E.164 phones
