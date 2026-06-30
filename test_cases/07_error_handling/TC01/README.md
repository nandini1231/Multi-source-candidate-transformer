# TC01 — Error Handling: Missing CSV Path

## Purpose
The CLI must validate paths and fail BEFORE starting the pipeline.

## Modules Validated
- main.py _resolve_paths
- Graceful exit with non-zero code

## Run
```bash
python3 main.py --recruiter-csv /tmp/does/not/exist.csv
echo "Exit: $?"   # should print 1
```
