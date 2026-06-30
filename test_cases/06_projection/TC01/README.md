# TC01 — Projection: Include-Only Subset

## Purpose
Confirm only declared fields appear in output; all others are excluded.

## Modules Validated
- Projector field iteration
- include_confidence=false suppresses meta block

## Run
```bash
python3 main.py --recruiter-csv test_cases/06_projection/TC01/recruiter.csv \
                --projection test_cases/06_projection/TC01/projection.json \
                --output test_cases/06_projection/TC01/output.json
```
