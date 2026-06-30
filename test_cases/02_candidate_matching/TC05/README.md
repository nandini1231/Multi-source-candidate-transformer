# TC05 — Matching: Duplicate Resumes

## Purpose
When two PDFs of the same person are accidentally uploaded, they must collapse into a single profile.

## Modules Validated
- Resume adapter idempotency
- Union-find grouping
- Email + phone dual key

## Why correct
- Both resume parses produce identical SourceRecords (same email, same phone).
- group_records puts them in one bucket.
- No conflicts (values are identical) → severity LOW everywhere.
- Quality and confidence unaffected by duplication.
