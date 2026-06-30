# TC02 — Happy Path: CSV + Resume Merged Cleanly

## Purpose
Verify that a recruiter CSV row and a matching resume PDF are correctly merged into ONE candidate profile when both share the same email.

## Modules Validated
- Resume adapter (text extraction, section detection)
- CSV adapter
- Candidate Matcher (email key)
- Field Resolver (scalar + union dedupe)
- Skills canonical mapping (ReactJS → React, PostgreSQL → SQL)
- Decision Engine end-to-end
- Projection

## Why the expected result is correct
- Email `arjun.mehta@example.com` appears in BOTH sources → matched via email key → single merged profile.
- CSV wins for scalar fields (`full_name`, `headline`) due to higher `source_priority` (100 vs 70).
- Phones agree after E.164 normalization → severity = LOW → no conflict logged.
- Skills extracted from resume → canonicalized → `ReactJS` becomes `React`, `PostgreSQL` becomes `SQL`.
- Experience + education come entirely from the resume (CSV has no such columns).
- Quality score = 1.0 (all required + important fields populated).
- No conflicts, no review triggers → `AUTO_APPROVED`.
