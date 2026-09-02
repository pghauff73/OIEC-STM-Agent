# EGCF

## What you will learn

You will read the EGCF command grammar and attach scope, risk, evidence, approval, explanation, simulation, and rollback to an objective.

## Everyday analogy

A workshop job card names the job, machine, permitted area, risk, required inspection, approval route, and recovery plan. It is more useful than “fix it.”

## New vocabulary

**EGCF** means Evidence-Governed Command Fabric. A **namespace** groups one responsibility. A **verb** selects an operation. **Modifiers** declare governance details.

## Diagram

The diagram decomposes a command into objective, scope, risk, evidence, approval, execution, and rollback.

Capability levels use a workshop analogy:

| Level | Everyday meaning | Current documentation behavior |
| --- | --- | --- |
| C0 | Look at the machine | Observe only |
| C1 | Draw a repair plan | Analyse and propose |
| C2 | Try it on a test machine | Simulate |
| C3 | Repair the actual machine with permission | Authorized local mutation |
| C4 | Change something outside the workshop | Fail closed in the current implementation |
| C5 | Perform a critical or destructive operation | Fail closed in the current implementation |

## Command or interaction

```bash
egcf capability list --repo .

egcf run fix parser regression \
  --repo . \
  --input '{"target":"src/parser.py"}' \
  --dry-run \
  --why
```

## Expected output

The first command lists capability definitions. The second compiles and explains a plan without executing it.

## What just happened?

The grammar is `egcf namespace verb options`. The `run` namespace accepts a natural-language objective, while other namespaces invoke typed verbs from the command catalog.

## Try changing this

Enable graph output and strict checking in the command builder. Observe which generated tokens explain those choices.

## Common mistake

Do not treat EGCF as arbitrary shell execution. Its namespace, verb, inputs, capability, risk, evidence, and lifecycle remain typed and governed.

## Next lesson

Continue to **EON** and inspect the exact boundary around a proposed mutation.
