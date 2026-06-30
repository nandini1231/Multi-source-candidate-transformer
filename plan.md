# Multi-Source Candidate Data Transformer
## Technical Architecture Design Document

This document describes the architectural design, data-flow contracts, and resolution policies for the Multi-Source Candidate Data Transformer. It is intended for engineering review and design defense. Operational test procedures live in [TESTING.md](TESTING.md).

---

## 🎯 System Objectives & Problem Statement

Recruiting systems ingest candidate data from heterogeneous sources whose schemas, quality, and completeness vary widely. A recruiter CSV export provides structured, columnar identity fields; a resume PDF or DOCX provides unstructured prose with implicit section boundaries, inconsistent formatting, and partial contact information. These sources frequently disagree on the same person—different email aliases, formatting variants of the same phone number, or alternate spellings of a legal name.

The system must solve three concurrent problems:

1. **Ingestion heterogeneity** — Parse structured and unstructured inputs through dedicated adapters without assuming a single universal schema at the boundary.
2. **Entity resolution** — Determine which raw records refer to the same human being and merge them into one canonical profile without false-positive joins.
3. **Trustworthy output** — Emit a normalized, schema-valid JSON artifact where every populated field is attributable to a source, every conflict is classified, and uncertain data is explicitly flagged rather than silently invented.

A non-negotiable operational constraint is **defensive execution**: missing files, empty rows, corrupt PDFs, invalid emails, and schema drift must never crash the pipeline. Wrong-but-confident output is considered a higher-severity failure than an honestly empty or `manual_review` profile. The architecture therefore prioritizes graceful degradation, explicit validation rejections, and auditable decision traces over aggressive gap-filling heuristics.

---

## 🏗️ Architectural Overview

The pipeline follows a linear staged architecture with strict separation between **computation** (building truth) and **presentation** (exporting truth):

```
┌─────────┐   ┌────────────┐   ┌───────────┐   ┌─────────┐   ┌──────────┐   ┌───────────┐
│ Adapters│ → │ Normalizers│ → │ Validator │ → │ Matcher │ → │ Resolver │ → │ Projector │
└─────────┘   └────────────┘   └───────────┘   └─────────┘   └──────────┘   └───────────┘
     │              │                │               │              │               │
  SourceRecord   Normalized        Validated      Grouped        CanonicalProfile   Output JSON
  (per file)     RawFields         Records        Clusters       (internal truth)   (consumer view)
```

### Stage responsibilities

| Stage | Responsibility |
|-------|----------------|
| **Adapters** | Translate external artifacts (CSV rows, PDF/DOCX text) into typed `SourceRecord` objects with `RawField` provenance metadata. Adapters perform extraction only—they do not merge or score. |
| **Normalizers** | Transform raw string values into canonical forms: E.164 phones, lowercase emails, ISO-3166 countries, YYYY-MM dates, canonical skill names. Normalization is idempotent and side-effect free. |
| **Validator** | Reject structurally invalid values (malformed email, out-of-range dates, unparseable phone) before they enter merge logic. Rejections are collected, not thrown, preserving pipeline continuity. |
| **Matcher** | Pairwise-compare `SourceRecord` instances using weighted keys (email, E.164 phone, fuzzy name + company). Union-find grouping ensures transitive closure (A↔B, B↔C ⇒ one cluster). |
| **Resolver** | Within each cluster, apply survivorship rules and source-priority policies to produce a single `CanonicalProfile`. Conflicts are logged with severity tiers; field-level decisions record reason codes. |
| **Projector** | Read-only transformation of `CanonicalProfile` into consumer JSON according to a runtime `ProjectionConfig`. The canonical record is never mutated during projection. |

### Canonical record vs projection layer

The **Internal Canonical Record** (`CanonicalProfile`) is the system's source of truth: a rich, stable object model containing all merged fields, conflict logs, provenance chains, confidence breakdowns, and review state. It exists solely inside the engine boundary.

The **Projection Layer** is a configurable export façade. Consumers (ATS integrations, audit dashboards, lightweight APIs) declare which fields they need, how those fields should be renamed, whether values should be further normalized at export time, and how missing data should behave (`null`, `omit`, or `error`). This decoupling delivers three engineering benefits:

- **Schema evolution without code deployment** — New downstream consumers can request different JSON shapes by editing configuration, not Python.
- **Separation of concerns** — Merge correctness is validated once against the canonical model; projection correctness is validated separately against declared output schemas.
- **Audit integrity** — Full provenance and conflict history remain available via `default_projection.json` while operational integrations consume minimal ATS-friendly projections.

Confidence scoring, quality scoring, and manual-review queue evaluation occur after resolution but before projection, ensuring review decisions are based on the complete merged profile rather than a prematurely truncated export.

---

## 👥 Entity Resolution & Survivorship Algorithms

Entity resolution operates in two phases: **cluster formation** (Matcher) and **survivorship application** (Resolver).

### Deterministic matching identifiers

Records are compared using normalized, deterministic keys to ensure reproducibility:

| Key | Normalization | Match rule |
|-----|---------------|------------|
| **Email** | Lowercase, trimmed | Exact set intersection → weight 1.0 |
| **Phone** | E.164 via region-aware parsing | Exact E.164 intersection → weight 0.9 |
| **Name + Company** | Token-set fuzzy ratio + company suffix stripping | Combined score × weight 0.5; threshold-gated |

Pairwise scores aggregate additively (capped at 1.0). Decisions follow configured thresholds:

- `score ≥ merge_decision_threshold` → **MERGE**
- `threshold − margin ≤ score < threshold` → **MANUAL_REVIEW** (grouped but flagged)
- `score < threshold − margin` → **SEPARATE** (distinct profiles)

Union-find clustering ensures that if Record A matches B and B matches C, all three resolve as one candidate even when A and C share no direct key overlap.

The design principle **"false merge is worse than duplicate profile"** governs threshold selection: name+company alone rarely forces a merge unless the composite score clears a high bar (default 0.75).

### Survivorship policies

Once a cluster is formed, field-level survivorship rules determine which values populate the canonical profile:

#### Chronological / First-Seen Dominance (scalar attributes)

For single-value identity fields (`full_name`, `headline`, scalar location components), the resolver defaults to the **first valid value encountered in deterministic processing order** within the cluster. When multiple CSV rows collapse to the same normalized phone (e.g., `Phone1`, `Phone2`, `Phone3` variants of one E.164 number), the earliest row's scalar identity survives.

Structured source priority (configured in `engine_config.json`: `recruiter_csv` > `resume`) overrides first-seen when sources conflict at MEDIUM severity—recruiter data wins for contested scalars unless severity classification demands manual review.

#### Master Array Aggregation (multi-value attributes)

List-valued fields follow a **union + deduplicate** policy—unique variants are never silently discarded:

| Field | Policy |
|-------|--------|
| **emails** | Union across all sources; lowercase dedupe; structured-source ordering preserved |
| **phones** | Union across all sources; dedupe by normalized E.164 |
| **skills** | Union by canonical skill name; confidence and source lists merged |

The projection layer exposes this aggregation to downstream consumers via `all_emails` (full deduplicated set), `primary_email` (`emails[0]`), and `alternative_emails` (`emails[1:]`). This ensures secondary contact paths discovered in any source remain auditable and exportable.

#### Provenance attachment

Every resolved field carries `{ field, source, method }` provenance entries derived from field decisions, enabling post-hoc inspection of which adapter supplied each canonical value and through what extraction method (`direct`, `regex`, `heuristic`).

---

## ⚠️ Conflict Resolution Engine

When multiple sources supply different values for the same field, the **SeverityClassifier** assigns a tier before the **FieldResolver** selects a winner.

### Severity tiering

| Tier | Typical triggers | Resolution behavior | Confidence impact |
|------|------------------|---------------------|-------------------|
| **LOW** | Formatting-only differences (case, punctuation, whitespace) | Auto-resolve via normalization | No penalty |
| **MEDIUM** | Minor semantic variation (name initials, company suffix) | Higher-priority structured source wins | × 0.85 |
| **HIGH** | Completely different identity values (unrelated emails, unrelated names on same phone) | Never auto-merge silently; flag `manual_review` | × 0.40 |

Each conflict produces a `ConflictEntry` recording competing values, selected winner, severity, and human-readable explanation. These entries populate `conflict_log` when audit projection is enabled.

### Defensive collision detection

Beyond per-field severity, the **ReviewQueue** applies cross-field heuristics for high-risk patterns:

- **Phone identity mismatch** — Same normalized phone, completely different name *and* email across sources → immediate review flag regardless of individual field severity.
- **Near-threshold match scores** — Merge confidence within the configured margin of the decision threshold → review to prevent borderline false joins.
- **Low overall confidence** — Aggregated field confidence below `min_confidence_without_review` → `manual_review` status.
- **HIGH-severity identity conflicts** — Conflicts on `full_name`, `emails`, or `phones` at HIGH tier block auto-approval.

The engine never suppresses review signals to force an `active` status. Status flows: `active` (auto-approved) or `manual_review` (human decision required)—there is no silent override path for HIGH-tier identity collisions.

---

## 📉 Data Invalidation & Graceful Degradation

The pipeline treats invalid input as an **expected operating condition**, not an exceptional crash path.

### Field-level validation

The Validator inspects emails (RFC-inspired length and format), phones (E.164 feasibility), and experience dates (parseability and configurable year bounds). Invalid values generate `ValidationRejection` records with explicit `reason_code` values (e.g., `INVALID_DATE`, `INVALID_EMAIL`). Rejected experience entries are stripped from the valid set rather than propagated as corrupt canonical data.

Validation rejections surface in the output summary (`validation_failures`, `validation_rejections[]`) so downstream systems can distinguish "field absent because source was empty" from "field absent because source was rejected."

### Structural schema defense (CSV header drift)

Recruiter CSV ingestion maps known header aliases to canonical column names via a fixed allow-list (`name`, `email`, `phone`, etc.). When a row arrives with **unmapped or missing structural headers** (e.g., `candidate_full_name` instead of `name`), the adapter does not raise an unhandled exception. Instead:

1. Unrecognized columns are ignored safely.
2. Required identity fields remain null when no mappable column exists.
3. The pipeline emits a degraded profile with null-filled required fields, `overall_confidence` of `0.0`, and incremented `validation_failures` tracking.
4. Review queue logic assigns `manual_review` where quality thresholds are unmet.

This **Header Variant Defense** pattern ensures schema drift in upstream exports degrades to an inspectable null profile rather than a runtime fault—preserving batch stability when processing thousands of heterogeneous files.

### Corrupt and empty sources

| Condition | Behavior |
|-----------|----------|
| Empty CSV file | Zero records; empty summary returned |
| Header-only CSV | Parsed rows skipped; degraded or empty output |
| Corrupt / unreadable PDF | Parse error captured on `SourceRecord`; profile proceeds with available fields or review status |
| Empty resume text | Warning logged; minimal profile from other sources if present |
| Projection required field missing | Configurable: emit `null`, omit key, or return structured `{ error: "..." }` per `on_missing` policy |

At no stage does the orchestrator propagate unhandled exceptions to the CLI boundary for expected data-quality failures. The pipeline completes, writes JSON, and prints a human-readable summary—enabling batch operators to filter `manual_review` and `validation_failures` programmatically.

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Project overview, quick start, configuration reference |
| [TESTING.md](TESTING.md) | Three-layer verification strategy and test execution |
| [test_cases/README.md](test_cases/README.md) | Integration suite matrix (59 scenarios) |
| [config/engine_config.json](config/engine_config.json) | Source priorities, thresholds, validation bounds |
| [config/projection_config.json](config/projection_config.json) | Default ATS projection shape |
