# TC05 — Error Handling: Corrupt PDF

## Purpose
A corrupt/unreadable PDF file must not crash the pipeline.

## Modules Validated
- ResumeAdapter._extract_text_pdf try/except
- BaseAdapter.safe_parse outer guard
- parse_errors propagation
