# TC05 — DOCX resume ingestion

Validates end-to-end pipeline when the resume input is a **`.docx`** file (not PDF).

Uses the same synthetic body as `01_happy_path/TC02`. `resume.docx` is generated from
`resume.txt` by `test_cases/generate_test_pdfs.py`.

**Modules:** `ResumeAdapter._extract_text_docx`, full pipeline via `main.py --resume`
