# Safely Modify Files

## Goal

Grant the smallest useful write boundary, inspect an exact candidate, run mandatory verification, and retain rollback.

## Command recipe

```bash
oiec-stm-agent . \
  --write \
  --write-path "docs/**" \
  --task "Improve the introduction"
```

## Learning route

Complete T06 EGCF and T07 EON.

## Boundary rules

- `--write-path` defines where proposals are allowed.
- `--write` and `--authority` are mutually exclusive.
- bounded write mode rejects `--yolo`.
- exact-candidate review and verification remain separate from model confidence.

## Safe completion condition

Only intended paths changed, required tests passed against the exact candidate, and the rollback path remains available.
