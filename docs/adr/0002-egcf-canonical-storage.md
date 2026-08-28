# ADR 0002: Canonical Ledger and Content-Addressed Objects

**Status:** Accepted for implementation  
**Date:** 2026-08-21

## Decision

EGCF canonical state consists of a hash-chained event ledger and immutable,
content-addressed objects/artifacts under `.ourd-agent/egcf/`. SQLite is a
rebuildable query projection and is never authority.

Supersedence adds a new object and relation. It never rewrites the superseded
object or earlier event.

## Consequences

- Projection deletion or corruption is recoverable.
- Exact object and plan identities can be approved and replayed.
- Historical decisions, failures, algorithms, and evidence remain inspectable.
