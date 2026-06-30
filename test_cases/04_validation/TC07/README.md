# TC07 — Validation: Mixed-Case Email Passes

## Purpose
Casing is normalised, not rejected. Output email is always lowercase.

## Modules Validated
- Pipeline normalization pass (email.strip().lower())
- Validator accepting case-normalised email
