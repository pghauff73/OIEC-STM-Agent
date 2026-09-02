# Context Budget Recovery v1.0 Implementation Plan

Date: 2026-08-30

## Objective

Add deterministic, fail-closed recovery before OIEC-STM-SR-Agent provider calls so requests that exceed the configured context budget can shed optional conversation history, replace completed tool-result bodies with evidence-bound projections, and retire the oldest completed evidence-backed tool exchanges from active model context without changing confirmed task meaning, authority, durable evidence, tool schemas, or current requests.

## Safety Rule

Automatic recovery may remove redundancy, but it may not silently remove governed meaning. A completed tool result may be compacted only when its call identity remains intact and the replacement discloses the original output hash, original size, evidence identifiers, preserved scalar status fields, and a deterministic head/tail excerpt.

If compacted outputs still leave cumulative call-envelope growth over budget, the oldest completed call/output pair may leave active model context only when the output is bound to durable evidence. The reduction report retains both canonical item signatures. Incomplete calls, the current task, authority, instructions, tool schemas, and the newest useful exchanges remain protected until no safer reduction can fit the request.

The v1.0 verdicts are:

```text
FIT
INSUFFICIENT_CONTEXT_BUDGET
```

`RECONFIRM_REQUIRED` is reserved for a later envelope-reprojection slice because changing file previews, pinned context, evidence selection, constraints, or the current task invalidates the existing exact confirmation binding.

## Phase 1: Deterministic Budget Model

Create `ourd/context_budget.py` with:

```text
ContextReductionStep
ContextBudgetReport
ContextRecoveryResult
estimate_tokens
effective_input_budget
recover_context_request
format_context_budget_error
```

The report records component estimates for instructions, tools, unpinned history, active request state, output reservation, safety margin, and runtime context when known. All identities use canonical JSON and SHA-256 without timestamps or random identifiers.

Pass gate:

```text
identical canonical input -> identical report and recovery signatures
```

## Phase 2: Semantics-Preserving Recovery

When the request is over budget:

1. Remove the oldest unpinned whole conversation turn.
2. Re-estimate the exact provider payload.
3. Repeat only while unpinned history remains.
4. If the request still does not fit, compact oversized completed tool outputs oldest-first into explicit evidence-bound projections.
5. Re-project previously bounded or medium completed outputs to a minimal evidence/hash projection.
6. If cumulative call envelopes still exceed the budget, remove the oldest completed evidence-backed call/output pair while retaining its durable evidence and reduction signatures.
7. Stop immediately when the request fits.
8. Fail closed if required active context still exceeds the effective budget.

The controller must never truncate the current task, an incomplete tool call, instructions, tool schemas, authority constraints, or confirmed context-envelope body. Full tool evidence remains durable; only the bounded active model projection changes.

Pass gate:

```text
automatic recovery changes only leading unpinned history, explicitly marked completed tool-result projections, or completed evidence-backed tool exchanges
```

## Phase 3: Runtime Integration

Run recovery immediately before every provider invocation in both the base and production loops. Persist only bounded diagnostics and hashes in trace events. Preserve the providers' existing independent pre-transport context guard as a second fail-closed boundary.

Configuration additions:

```text
runtime_context_tokens
context_safety_margin_tokens
```

Enforce:

```text
estimated_input <= configured_input_budget
```

and, when runtime context is known:

```text
estimated_input + reserved_output + safety_margin <= runtime_context
```

The automatic Qwen3.8 27B Fast profile binds its verified 8,192-token runtime context explicitly.

## Phase 4: Diagnostics and No-Blind-Retry

Each recovery report contains exact request, history, active-input, and reduction signatures. An irreducible request raises `ContextBudgetError` before transport with component totals and the deterministic report signature. CFEL uses that signature in its collision fingerprint so rewording an error cannot masquerade as a new epistemic attempt.

Pass gate:

```text
unchanged oversized request -> unchanged recovery signature and no provider call
```

## Phase 5: Tests

Add focused tests for:

```text
component accounting
whole-turn removal
completed tool-output compaction
cumulative completed-output re-projection
oldest evidence-backed exchange retirement
current-task preservation
irreducible fail-closed behavior
runtime output reservation
deterministic signatures
agent-loop automatic recovery
provider guard preservation
```

## Phase 6: Graceful Cycle Stop

Keep `CYCLE_STOP` as a deterministic no-progress boundary, but do not expose it as a GUI exception. After recording the collision, permit exactly one terminal provider call with tools disabled and instructions restricted to synthesis from existing observations. Certify that terminal transition. If the provider requests a tool, returns no prose, exceeds context, or fails transport, return a deterministic system stop message instead.

Pass gate:

```text
cycle stop -> no further tool dispatch -> terminal response or deterministic fallback
```

## Phase 7: Truncated Tool-JSON Recovery

Local Ollama may reject a response before returning it when `llama-server` reaches the output limit in the middle of function-call arguments. Recognize only the explicit `invalid tool call arguments ... unexpected end of JSON input` signature. If runtime context is known, retry exactly once with a larger output allowance bounded by:

```text
estimated_input + retry_output + safety_margin <= runtime_context
```

The retry changes the provider request materially, records the affected tool, old and new output limits, estimated input, and a deterministic signature, and is emitted as `provider_response_recovery`. Unrelated HTTP 500 responses and configurations without proven runtime headroom continue to fail closed.

The automatic Qwen3.8 27B Fast profile reserves 1,400 output tokens by default. With a 6,000-token input budget, 512-token margin, and 8,192-token runtime context, this retains the full configured input allowance while substantially reducing malformed tool-envelope risk.

Pass gate:

```text
truncated tool JSON -> one bounded expanded retry -> valid response or signed failure
```

## Deferred v1.1 Work

The following changes are intentionally not automatic in v1.0:

```text
reducing pinned file previews
summarizing confirmed conversation content
dropping evidence atoms
changing selected files
batching a confirmed folder projection
altering the current task
```

Those operations require a new `InteractionContextEnvelope`, a visible context delta, and a fresh exact confirmation receipt.
