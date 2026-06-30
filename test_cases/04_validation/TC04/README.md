# TC04 — Validation: Missing Required Field (Empty Email)

## Purpose
Empty cells are not validation failures — they are just absent values. The pipeline must still build a profile, but the data_quality_score must reflect missing required fields.

## Modules Validated
- CSV adapter skipping empty cells
- QualityScorer penalising missing required fields
