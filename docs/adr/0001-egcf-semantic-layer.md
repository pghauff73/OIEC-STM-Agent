# ADR 0001: EGCF Is an Additive Semantic Layer

**Status:** Accepted for implementation  
**Date:** 2026-08-21

## Decision

EGCF compiles typed engineering commands into qualified algorithms and executor
adapters. It does not replace Codex primitives, repository tools, sandboxes,
MCP, skills, providers, EON, or transactions.

No command definition stores an executable callback. Execution is possible only
after exact command resolution, capability checking, contextual qualification,
workflow compilation, evidence gates, and any required approval.

## Consequences

- Existing `ourd-agent` behavior remains compatible.
- `egcf` is a separate CLI and Python API.
- Shell execution remains an exact-argv EON/PolicyEngine operation.
- Semantic breadth does not imply broader raw authority.
