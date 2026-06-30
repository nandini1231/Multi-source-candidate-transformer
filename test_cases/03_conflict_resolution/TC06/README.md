# TC06 — Conflict Resolution: Education

## Purpose
Verify that multiple degrees from the same institution are NOT erroneously deduplicated.

## Modules Validated
- FieldResolver.resolve_education identity key (institution, degree)

## Why correct
- IIT Madras (PhD) ≠ IIT Madras (M.Sc) — different degrees → different keys → both kept.
- 3 distinct entries preserved.
