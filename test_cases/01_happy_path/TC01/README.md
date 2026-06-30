# TC01 — Happy Path: Single CSV Record

## Purpose
Validate the simplest possible pipeline run: one well-formed CSV row, no resume.

## Modules Validated
- CSV adapter (`RecruiterCSVAdapter`)
- Normalization (phones, location, email lowercase)
- Validator (no rejections expected)
- Decision Engine (single-source path)
- Projector (default `projection_config.json`)
- Console summary

## Why the expected result is correct
- All fields are clean and well-formed; `recruiter_csv` is the only source so every field is `SINGLE_SOURCE`.
- Phone is already in E.164 format → no normalization change but still valid.
- `location` is fully parseable as `Pune, Maharashtra, India` → city/region/country populated.
- No conflicts → `status = AUTO_APPROVED`.
- Confidence ≈ 0.95 because: base(0.95) × certainty(1.0) × severity_LOW(1.0) × agreement_single_source(0.95).

## Run

```bash
python3 main.py \
  --recruiter-csv test_cases/01_happy_path/TC01/recruiter.csv \
  --output test_cases/01_happy_path/TC01/output.json
```
