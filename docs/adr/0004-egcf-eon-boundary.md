# ADR 0004: EON Remains the Sole Workspace Mutation Boundary

**Status:** Accepted for implementation  
**Date:** 2026-08-21

## Decision

EGCF C3 workspace changes are staged through `OURDAgent.prepare_transaction`,
compiled into exact `EONAction` objects, evidence-gated, bound to an immutable
EGCF execution plan and human approval object, applied by
`TransactionManager`, verified, and rolled back through the existing manifest.

No EGCF module exposes a second filesystem writer.

## Consequences

- Existing canonical path, exact argv, policy, candidate hash, source drift,
  atomic apply, and rollback enforcement remains authoritative.
- Model tools cannot construct human approval records.
- A forged approval dictionary is insufficient; the immutable object must exist.
