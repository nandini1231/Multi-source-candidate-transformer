# TC02 — Error Handling: Empty CSV

## Purpose
A zero-byte CSV must produce an empty result without crashing.

## Modules Validated
- RecruiterCSVAdapter — handles empty file (no headers detected)
- Pipeline.run early-exit branch
