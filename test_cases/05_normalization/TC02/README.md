# TC02 — Normalization: Email Lowercase

## Purpose
All emails normalised to lowercase before validation and merging.

## Modules Validated
- Pipeline._normalize_records → email .strip().lower()
- Validator passing normalised emails
