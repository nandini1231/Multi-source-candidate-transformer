# TC07 — Conflict Resolution: Missing Values / Gap Fill

## Purpose
When a higher-priority source has missing values, the lower-priority source fills them — NOT a conflict.

## Modules Validated
- FieldResolver scalar gap-fill logic
- ReasonCode.GAP_FILL path

## Why correct
- CSV missing phone, location.
- Resume has both.
- Output uses resume values; reason code = GAP_FILL.
- No conflict logged because there's no disagreement, only absence.
