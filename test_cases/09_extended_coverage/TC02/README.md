# TC02 — custom --engine-config (relaxed date bounds)

Uses a per-case `engine_config.json` with `validation.date_min_year: 1800`.
The same resume body as `04_validation/TC06` is rejected under the default config
but accepted here, proving custom engine config is honored end-to-end.

**Modules:** CLI `--engine-config`, `Validator`, `ResumeAdapter`
