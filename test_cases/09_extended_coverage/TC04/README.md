# TC04 — multi-resume directory batch (--resume-dir)

Two independent resumes live under `resumes/`; the runner invokes
`main.py --resume-dir` (no single `--resume`).

**Modules:** CLI `--resume-dir`, `Pipeline._collect_resume_files`, `ResumeAdapter`
