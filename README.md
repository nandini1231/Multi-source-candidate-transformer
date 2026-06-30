# Multi-Source Candidate Data Transformer

A deterministic, explainable pipeline that ingests candidate data from **structured** (recruiter CSV) and **unstructured** (resume PDF/DOCX) sources, merges them into a single canonical profile per person, and emits **schema-valid JSON** — with full provenance, confidence scoring, and conflict logging.

> **Design principle:** Wrong-but-confident is worse than honestly empty. Every field is traceable to its source and resolution method.

---

## Highlights

| Capability | Implementation |
|------------|----------------|
| Multi-source merge | Email / phone / fuzzy name+company matching with union-find grouping |
| Normalization | E.164 phones, ISO-3166 countries, YYYY-MM dates, canonical skill names |
| Conflict resolution | LOW / MEDIUM / HIGH severity; structured source wins; never silent HIGH merges |
| Configurable output | Runtime JSON projection — field subset, rename, normalize, omit/null/error |
| Validation | Input validation + projected output type checks; graceful degradation on bad data |
| Explainability | `provenance`, `conflict_log`, `field_decisions`, `confidence_details` |
| Test coverage | 90 unit tests + 59 integration scenarios across 9 categories |

---

## Architecture

```
Input → Parse → Normalize → Validate → Match → Resolve → Confidence → Quality → Project → Output
         │                              │                    │
    CSV / Resume                   CandidateMatcher      FieldResolver
    adapters                       (email/phone/name)    + ReviewQueue
```

**Internal model:** The engine always builds a full **canonical profile**. The **Projector** reshapes it for export based on your projection config — no code changes required.

**Supported sources today:**

| Type | Source | Adapter |
|------|--------|---------|
| Structured | Recruiter CSV | `RecruiterCSVAdapter` |
| Unstructured | Resume PDF / DOCX | `ResumeAdapter` |

---

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install fpdf2   # only needed to regenerate test PDFs
```

### Default run (CSV + resume)

```bash
python main.py \
  --recruiter-csv data/sample_inputs/candidates.csv \
  --resume        path/to/resume.pdf \
  --output        output/result.json
```

### CSV only

```bash
python main.py --recruiter-csv data/sample_inputs/candidates.csv --output output/csv_only.json
```

### Resume only (single file or batch directory)

```bash
python main.py --resume path/to/resume.pdf --output output/resume_only.json

python main.py --resume-dir path/to/resumes/ --output output/batch.json
```

### Custom output shape (projection config)

```bash
# Subset of fields + renamed keys (see test_cases/06_projection/TC02/projection.json)
python main.py \
  --recruiter-csv test_cases/06_projection/TC02/recruiter.csv \
  --resume        test_cases/06_projection/TC02/resume.pdf \
  --projection    test_cases/06_projection/TC02/projection.json \
  --output        output/custom_shape.json

# Full audit output (provenance + conflict_log + confidence_details)
python main.py \
  --recruiter-csv test_cases/03_conflict_resolution/TC01/recruiter.csv \
  --resume        test_cases/03_conflict_resolution/TC01/resume.pdf \
  --projection    config/default_projection.json \
  --output        output/full_audit.json
```

### Custom engine behavior (thresholds, validation bounds)

```bash
python main.py \
  --resume        test_cases/09_extended_coverage/TC02/resume.pdf \
  --engine-config test_cases/09_extended_coverage/TC02/engine_config.json \
  --output        output/relaxed_dates.json
```

Each run prints a human-readable summary to the terminal (status, confidence, match keys, validation rejections, conflicts resolved).

---

## Configurable Output (Projection Layer)

Pass `--projection path/to/config.json` to control the exported JSON **without changing code**:

| Config knob | Example |
|-------------|---------|
| Field subset | Only export fields listed in `"fields"` |
| Rename / remap | `"path": "work_email", "from": "emails[0]"` |
| Per-field normalize | `"normalize": "E164"` or `"canonical"` |
| Toggle audit fields | `"include_provenance"`, `"include_confidence"`, `"include_conflict_log"` |
| Missing values | `"on_missing": "null"` \| `"omit"` \| `"error"` |

Example projection config:

```json
{
  "fields": [
    { "path": "full_name",     "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string" },
    { "path": "phone",         "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

Live examples: `test_cases/06_projection/` (5 cases covering subset, rename, omit, error, full audit).

---

## Configuration

| File | Purpose |
|------|---------|
| `config/engine_config.json` | Source priorities, match weights, merge threshold, review rules, date bounds |
| `config/projection_config.json` | Default ATS-style output (primary email, phone, skills, etc.) |
| `config/default_projection.json` | Full canonical + all audit metadata |

Edit JSON configs to change behavior — no code deployment needed.

---

## Project Structure

```
├── main.py                 # Primary CLI entry point
├── cli.py                  # Alternate Typer-based CLI
├── src/
│   ├── adapters/           # CSV + resume parsers
│   ├── normalize/          # Phones, dates, skills, location, names
│   ├── validate/           # Email, phone, date range checks
│   ├── decision/           # Match, resolve, confidence, review queue
│   ├── project/            # Configurable output projection
│   └── pipeline.py         # Orchestrator
├── config/                 # Engine + projection JSON configs
├── tests/                  # Unit tests (pytest)
├── test_cases/             # 59 integration scenarios (9 categories)
├── data/sample_inputs/     # Sample CSV for quick demo
└── requirements.txt
```

---

## Testing

### Unit tests

```bash
pytest tests/ -v
pytest tests/ --cov=src
```

### Integration suite (59 black-box cases)

Synthetic inputs with deterministic expected outputs — covers happy path, matching, conflicts, validation, normalization, projection, error handling, edge cases, and extended coverage (DOCX, resume-dir batch, custom engine config).

**Two-step verification:**

```bash
# Step 1 — Regenerate test PDFs/DOCX from resume.txt (first time or after editing resume text)
python test_cases/generate_test_pdfs.py

# Step 2 — Run full suite (unit + integration); writes test_results.json + TEST_RESULTS.md
python test_cases/run_all_tests.py
```

**Categories:** `01_happy_path` · `02_candidate_matching` · `03_conflict_resolution` · `04_validation` · `05_normalization` · `06_projection` · `07_error_handling` · `08_edge_cases` · `09_extended_coverage`

Details: [test_cases/README.md](test_cases/README.md) · Testing strategy: [TESTING.md](TESTING.md) · Architecture: [plan.md](plan.md)

---

## Output Schema

The pipeline maintains a rich **canonical profile** internally (`candidate_id`, `emails[]`, `phones[]`, `skills[]`, `experience[]`, `education[]`, `provenance`, `conflict_log`, etc.). What you see in the final JSON depends on the projection config:

- **`default_projection.json`** — full canonical shape plus audit metadata (`confidence_details`, `provenance`, `conflict_log`).
- **`projection_config.json`** — ATS-friendly flattened export: `primary_email`, `alternative_emails`, `all_emails`, `phone`, skill name arrays, and confidence scores.

### Sample Shortened Output Profile (ATS Projection Shape)

```json
{
  "full_name": "Phone1",
  "primary_email": "p1@example.com",
  "phone": "+919876543210",
  "all_emails": [
    "p1@example.com",
    "p2@example.com",
    "p3@example.com"
  ],
  "location": {
    "city": null,
    "country": null
  },
  "headline": "Engineer",
  "overall_confidence": 0.874,
  "data_quality_score": 0.7,
  "status": "active"
}
```

---

## Conflict Resolution & Review

| Severity | Behavior |
|----------|----------|
| **LOW** | Auto-resolve (formatting differences); no confidence penalty |
| **MEDIUM** | Structured source wins; confidence × 0.85; logged |
| **HIGH** | Flagged for `manual_review`; never silently merged on identity fields |

**Manual review triggers:** HIGH identity conflicts · match score near threshold · low overall confidence · same phone with different name+email.

Every resolved field includes `reason_code` and human-readable explanation.

---

## 👥 Entity Resolution & Survivorship Policy

- **Chronological / First-Seen Dominance:** Scalar identity attributes (like `full_name`) default to the first record encountered in the execution sequence (e.g., `Phone1` survives over identical variants `Phone2` and `Phone3`).
- **Data Preservation (Array Aggregation):** Unique list-based data variants are never silently dropped. Secondary emails or alternative phone numbers found across merged records are accumulated inside the `all_emails` master tracking field.
- **Header Variant Defense:** If a row contains unmapped headers (e.g., `candidate_full_name` instead of `name`), the system avoids throwing a breaking runtime exception. It degrades gracefully by outputting a null-filled record with an `overall_confidence` of `0.0` and increments the `validation_failures` tracking metric explicitly.

---

## Assumptions & Descoped Items

Documented intentionally — core assignment requirements are met; these were out of scope:

- **ATS JSON adapter** — engine config supports `ats_json` priority; adapter not implemented
- **GitHub / LinkedIn live APIs** — links extracted from resume text only
- **Recruiter free-text notes** — not implemented as a separate source type
- **ML / NER** — resume parsing uses regex + section heuristics (deterministic, explainable)
- **Persistent version store** — in-memory per run; no cross-run state

---

## Requirements

- Python 3.9+
- See `requirements.txt` for dependencies (`pydantic`, `phonenumbers`, `pdfplumber`, `python-docx`, `rapidfuzz`, `pytest`, …)
