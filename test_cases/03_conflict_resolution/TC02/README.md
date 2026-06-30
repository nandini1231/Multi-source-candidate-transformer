# TC02 — Conflict Resolution: Email Union

## Purpose
When two sources have different emails for the same person, both must be retained (not dropped).

## Modules Validated
- FieldResolver.resolve_emails
- Email list union with deduplication
- primary_email selection from highest-priority source

## Why correct
- Phone matches → same candidate.
- Different emails from work + personal accounts → both real, both kept.
- Output `primary_email` is the CSV one (higher priority); both available in full canonical profile.
