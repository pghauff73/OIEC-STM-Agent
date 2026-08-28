# OURD GUI Safety Boundary

**Date:** 2026-08-21

## Primary Invariant

```text
GUIAuthority <= AgentAuthority
```

The GUI may request, display, compare, simulate, replay, and export. It may not
grant capability, invent evidence, authorize on behalf of a person, bypass EON,
or mutate repository files directly.

## Mutation Boundary

- View modules are statically prohibited from importing subprocess execution, EON adapters, transaction managers, or the legacy agent mutation path.
- C0/C1 semantic terminal commands may execute through registered deterministic adapters.
- C2 is forced through simulation.
- C3-C5 terminal requests compile only; authorization and execution remain separate controls.
- C4 and C5 remain blocked when the core denies them.
- Execution requires the current plan snapshot and, when required, an exact unexpired human approval for the same plan hash.
- Rejecting approval creates no execution request.
- Agent Chat calls the existing `OURDAgent` tool dispatcher. It does not expose
  a new write API, shell bypass, or GUI-owned capability grant.
- Every chat turn uses short-lived core ownership. C3 or higher behavior remains
  impossible without the same external authority, governance, evidence gate,
  EON action, exact candidate binding, and approval required outside the GUI.

## Untrusted Data

- Object envelopes are schema-validated and content-address checked before display.
- Core event payload and chain hashes are validated before authoritative replay.
- Partial event lines are ignored until complete.
- JSON/details are depth, count, string, and output bounded.
- Secret-like fields such as passwords, API keys, private keys, and access tokens are redacted in detail and export projections.
- Artifact paths are resolved beneath `.ourd-agent/egcf`; traversal fails closed.
- HTML and SVG are passive text. No scripts, network loads, or embedded active content execute.
- OBJ, STL, and PLY parsers return bounded metadata only.

## Model Boundary

OpenAI, Qwen, and compatible model metadata are observational. Agent Chat may
invoke existing governed tools, inspect the repository, draft candidates, or
critique, but model output is never evidence, approval, qualification, or
execution authority. A requested model tag is not silently replaced by another
installed model.

Chat history is bounded to user and assistant messages before each provider
request. `New Chat` advances a projection boundary without deleting historical
events. `Stop` is cooperative: cancellation is checked before preflight, before
each model step, after each provider response, and before every tool dispatch.
The current synchronous transport cannot interrupt an HTTP request already in
flight, so the UI reports `stopping` until control returns.

## Export Boundary

Evidence and assurance exports are clearly marked non-authoritative and are
stored only under `.ourd-agent/gui/exports`. They preserve canonical IDs,
hashes, snapshots, gaps, conflicts, unknowns, and limitations while redacting
secret-like fields.
