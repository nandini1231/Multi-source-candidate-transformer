# TC05 — Conflict Resolution: Experience Merging

## Purpose
Resume has 3 experience blocks, CSV has the current role only. The resolver must produce a clean merged list without duplicating the current role.

## Modules Validated
- FieldResolver.resolve_experience identity key (company, title, start)
- Date normalization across all rows
- Source merging
