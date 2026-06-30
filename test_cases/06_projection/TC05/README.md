# TC05 — Projection: Full Canonical

## Purpose
Use config/default_projection.json to emit every canonical field + audit metadata.

## Run
```bash
python3 main.py --recruiter-csv test_cases/06_projection/TC05/recruiter.csv \
                --projection config/default_projection.json \
                --output test_cases/06_projection/TC05/output.json
```
