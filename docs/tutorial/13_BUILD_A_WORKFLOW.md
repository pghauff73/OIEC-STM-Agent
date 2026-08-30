# Build a Workflow

## What you will learn

You will combine interpretation, problem mapping, experimentation, command compilation, exact action review, evidence, failure learning, retrieval, and improvement.

## Everyday analogy

A complete engineering workflow carries a job from customer request through diagnosis, controlled testing, approved repair, inspection, records, and future reuse.

## New vocabulary

A **workflow** is an ordered set of responsibilities and gates. A **DAG** is a directed acyclic graph whose dependency edges cannot loop back into themselves.

## Diagram

The final course map connects all earlier lessons and marks where the system may stop, refuse, request evidence, or continue.

## Command or interaction

```bash
egcf run fix parser regression \
  --repo . \
  --input '{"target":"src/parser.py"}' \
  --dry-run --why --graph --strict \
  --risk L1 --rollback exact
```

## Expected output

You can explain every command token, identify the required evidence and authority, and locate where failures become reusable records.

## What just happened?

The architecture became a learning sequence rather than a wall of acronyms. Technical pages remain available when you need exact types, equations, source maps, and invariants.

## Try changing this

Choose one task route from the homepage and replace the parser objective with your own read-only or simulated goal. Preserve the same explicit reasoning about scope and proof.

## Common mistake

Do not treat completion of the tutorial as authority to run real mutations. Real work still requires current source state, explicit authority, exact evidence, and the applicable approval path.

## Next lesson

Continue through a task guide, case study, concept page, or the Architecture Explorer. The printable and Teacher views provide exercises and review material.
