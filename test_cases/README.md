# Synthetic Testing Suite

A comprehensive black-box testing suite for the candidate ingestion pipeline.
All inputs are **synthetic** but realistic; all expected outputs are **deterministic**.

The suite does NOT modify any project code. It only contains test inputs and
expected outcomes that can be compared against actual pipeline runs.

---

## Directory Layout

```
test_cases/
├── 01_happy_path/          (5 TCs)  — clean inputs, no surprises
├── 02_candidate_matching/  (6 TCs)  — email/phone/fuzzy match scenarios
├── 03_conflict_resolution/ (8 TCs)  — severity, source priority, gap fill
├── 04_validation/          (8 TCs)  — bad inputs, empty fields, range checks
├── 05_normalization/       (6 TCs)  — phones, emails, countries, skills, dates, names
├── 06_projection/          (5 TCs)  — include/exclude/rename/missing/full
├── 07_error_handling/      (6 TCs)  — bad paths, empty/header-only CSV, corrupt PDF, no inputs
├── 08_edge_cases/          (10 TCs) — duplicates, unicode, multi-email, long resumes, formatting
└── 09_extended_coverage/   (5 TCs)  — years_experience, engine-config, canonical audit, resume-dir, DOCX
```

Each test case folder follows the same layout:

```
TCxx/
├── resume.txt               # synthetic resume body (source for PDF/DOCX generation)
├── resume.pdf               # generated via test_cases/generate_test_pdfs.py
├── recruiter.csv            # CSV (may say "(none)" if unused)
├── projection.json          # only when a custom projection is needed
├── engine_config.json       # only when custom engine config is tested
├── expected_output.json     # deterministic expected output (partial match)
└── README.md                # purpose / modules validated / why correct
```

---

## How to Run

```bash
# Regenerate PDFs/DOCX from resume.txt
python test_cases/generate_test_pdfs.py

# Full suite (unit + integration)
python test_cases/run_all_tests.py

# Single case manually
python main.py \
  --resume        test_cases/01_happy_path/TC02/resume.pdf \
  --recruiter-csv test_cases/01_happy_path/TC02/recruiter.csv \
  --output        output/tc02_result.json
```

Compare `output/tc02_result.json` against `expected_output.json` (partial key matching).

---

## Modules Exercised Across the Suite

| Module                       | Where it's exercised                                        |
|------------------------------|-------------------------------------------------------------|
| `RecruiterCSVAdapter`        | All CSV-driven cases; explicit edge cases in 07/08          |
| `ResumeAdapter`              | All resume-driven cases; corrupt-PDF in 07/TC05             |
| Normalization (phones)       | 05/TC01, 03/TC03, plus every case with a phone              |
| Normalization (emails)       | 05/TC02, 04/TC07                                            |
| Normalization (country)      | 05/TC03                                                     |
| Normalization (skills)       | 03/TC04, 05/TC04, 08/TC10                                   |
| Normalization (dates)        | 05/TC05                                                     |
| Validator                    | All of category 04                                          |
| CandidateMatcher             | All of category 02                                          |
| SeverityClassifier           | 02/TC01, 03/TC01, 03/TC08                                   |
| FieldResolver                | All conflict-resolution cases                               |
| ConfidenceScorer             | Every case has an expected confidence range                 |
| QualityScorer                | 04/TC04, 08/TC06, 08/TC09                                   |
| ReviewQueue                  | 02/TC06, 03/TC08                                            |
| Projector                    | All of category 06                                          |
| Error/fallback paths         | All of category 07                                          |

---

## Determinism Guarantees

Every expected output is produced from rules that are encoded in the engine:
- Phone E.164 conversion is region-aware and idempotent.
- Email lowercase is a pure transform.
- Skill canonicalisation uses the static SKILL_SYNONYMS dictionary.
- Source priority (recruiter_csv=100, resume=70) is fixed in config.
- Severity classifier uses deterministic regex/token rules.
- Match thresholds and review margins live in `config/engine_config.json`.

Therefore the same input + same config will always yield the same output,
modulo non-deterministic ids/timestamps that the diff harness should ignore.

---

## Summary Counts

|  Category                 | # TCs |
|---------------------------|-------|
| 01 Happy Path             |   5   |
| 02 Candidate Matching     |   6   |
| 03 Conflict Resolution    |   8   |
| 04 Validation             |   8   |
| 05 Normalization          |   6   |
| 06 Projection             |   5   |
| 07 Error Handling         |   6   |
| 08 Edge Cases             |  10   |
| 09 Extended Coverage      |   5   |
| **Total**                 | **59**|
