# TC04 — Happy Path: Resume Only (no CSV)

## Purpose
Confirm the pipeline works when only an unstructured source (resume) is supplied.

## Modules Validated
- Resume adapter end-to-end (text extraction, contact regex, section split, experience block parser, education block parser)
- Skill canonicalization (MongoDB → NoSQL, Node.js mapping)
- Date normalization ("Mar 2021" → "2021-03", "Present" → null)
- Confidence formula with resume base weight (0.70)

## Why correct
- Single resume = single source = single profile.
- Phone in resume is `+91 99887 76655` → `+919988776655` (E.164).
- Skills extracted from SKILLS section then canonicalized.
- Experience dates correctly normalized; "Present" properly mapped to `null` end date.
- Lower overall confidence (~0.65) is correct because resume has lower base weight than CSV and extraction methods are regex/heuristic.
