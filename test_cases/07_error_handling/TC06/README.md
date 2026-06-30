# TC06 — Error Handling: No Inputs

## Purpose
Running the pipeline with no resume and no CSV should not crash; just produce zero candidates.

## Modules Validated
- Pipeline.run with None for both inputs
- Empty record list handled by every downstream module
