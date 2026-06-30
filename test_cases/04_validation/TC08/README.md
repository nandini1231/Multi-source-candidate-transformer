# TC08 — Validation: Both Email and Phone Invalid

## Purpose
Pipeline must not crash when all identity fields fail validation. It produces a degraded profile with a low quality score.

## Modules Validated
- Multi-field rejection accumulation
- QualityScorer with all required missing
- Graceful degradation
