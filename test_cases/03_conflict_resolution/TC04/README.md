# TC04 — Conflict Resolution: Skill Synonyms

## Purpose
11 raw skill strings that all reduce to 4 canonical skills via synonym mapping.

## Modules Validated
- normalize_skill (SKILL_SYNONYMS reverse lookup)
- FieldResolver.resolve_skills (dedupe by canonical name, merge sources/confidences)

## Why correct
- Maps ReactJS/react.js → React
- Maps NodeJS/node js → Node.js
- Maps K8s/kubernetes → Kubernetes
- Maps JS/ES6 → JavaScript
- All variants collapse to 4 unique canonical entries with confidence max-merged.
