# TC01 — Validation: Invalid Email

## Purpose
Invalid emails must be DROPPED at the validation gate before reaching the resolver.

## Modules Validated
- Validator._validate_emails
- ValidationRejection with reason_code INVALID_EMAIL_FORMAT

## Why correct
- 'not-an-email' has no '@' → fails _EMAIL_RE regex.
- Email list becomes empty; profile still produced from name + phone.
- Validation failure count = 1 (reported in summary, not in final candidate JSON).
