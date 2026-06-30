# TC05 — Happy Path: Senior Profile with Rich Resume

## Purpose
Test merging when the candidate has a substantial resume (multiple companies, many skills, formal education) and a corresponding CSV row.

## Modules Validated
- All adapters
- Skill canonicalization for short tokens (ML → Machine Learning)
- Skill canonicalization for case variants (ElasticSearch → Elasticsearch)
- Experience date normalization with "Present"
- Quality scorer (should reach 1.0)

## Why correct
- CSV and resume agree on email/phone/name → clean merge via email match.
- Skills go through canonical mapping (10 entries).
- All required + important fields populated → `data_quality_score = 1.0`.
- No conflicts; status = `AUTO_APPROVED`.
