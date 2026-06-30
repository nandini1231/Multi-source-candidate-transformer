# TC04 — Error Handling: Unknown CSV Columns

## Purpose
Columns whose headers aren't in _COLUMN_MAP must be ignored gracefully with warnings.

## Modules Validated
- RecruiterCSVAdapter._COLUMN_MAP lookup miss path
- parse_warnings population
