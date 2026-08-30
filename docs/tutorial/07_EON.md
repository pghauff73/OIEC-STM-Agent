# EON

## What you will learn

You will inspect the exact target, source state, candidate, authority, risk, tests, approval, and rollback attached to a proposed action.

## Everyday analogy

“Fix the electricity” is too broad. “Test this switch in this circuit without modifying wiring” is a bounded action that can be reviewed.

## New vocabulary

**EON** means Exact Governed Action Boundary. **Authority** states what may be attempted. **Rollback** states how an accepted change can be undone.

## Diagram

The diagram turns “fix parser” into questions about files, source version, allowed paths, required tests, approval, expiry, and rollback.

## Command or interaction

```bash
oiec-stm-agent . \
  --write \
  --write-path "docs/**" \
  --task "Improve the introduction"
```

## Expected output

The session creates temporary bounded writing authority limited to `docs/**`. Any candidate remains subject to exact-candidate approval and verification.

## What just happened?

`--write-path` defined the legal proposal boundary. It did not predict where the model might write; it constrained where the session is allowed to propose writes.

## Try changing this

Use the command builder to compare read-only mode with bounded write mode. Then attempt the invalid combination of `--write` and `--yolo` in the refusal lesson.

## Common mistake

Tool availability is not authority. EON also does not create authority; it binds an exact proposal to authority that already exists.

## Next lesson

Continue to **CFEL** and see how failed expectations become reusable memory.
