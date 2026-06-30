# TC03 — Conflict Resolution: Phone Normalization (LOW)

## Purpose
Different surface forms of the SAME phone number must not produce a conflict.

## Modules Validated
- normalize_phone (E.164)
- SeverityClassifier.classify_phone returning LOW
- FieldResolver.resolve_phones deduping via E.164

## Why correct
- "9876543210" + IN region → +919876543210
- "+91-9876-543-210" → +919876543210
- Same E.164 → severity LOW → no conflict logged → no confidence penalty.
