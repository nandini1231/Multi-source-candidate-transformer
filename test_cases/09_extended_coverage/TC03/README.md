# TC03 — full canonical projection with provenance + conflict_log

Uses `default_projection.json` (via projection.json `_note` redirect) so output
includes audit fields: `provenance`, `conflict_log`, and `confidence_details`.

CSV + resume disagree on `full_name`, producing a non-empty conflict log.

**Modules:** `Projector`, `FieldResolver`, conflict logging
