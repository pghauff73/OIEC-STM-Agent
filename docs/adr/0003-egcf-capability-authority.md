# ADR 0003: Capability Requirements Union, Authority Intersection

**Status:** Accepted for implementation  
**Date:** 2026-08-21

## Decision

Workflow capability requirements are the union of command, algorithm, executor,
and reachable child requirements. Effective authority is the intersection of
the external grant, requested scope, and inherited constraints.

C0-C5 capability class is separate from L0-L2 contextual risk. A command may
raise either dimension but cannot lower a parent or deterministic minimum.

## Consequences

- Composite commands cannot launder a high-capability child.
- C4 and C5 remain fail-closed until separately qualified adapters exist.
- `capability grant` and `capability revoke` require external administration.
