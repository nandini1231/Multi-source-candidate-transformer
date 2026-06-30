# TC04 — Projection: Required Missing → Error

## Purpose
on_missing=error causes ProjectionError when a required field is null.

## Modules Validated
- Projector.project raising ProjectionError
- Pipeline catching it and recording in projected[i]
- `candidate_id` is still emitted (hash-based); tests assert only the `error` message
