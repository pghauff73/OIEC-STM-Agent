# OURD GUI Event Schema

**Schema:** `AgentEvent` version 1  
**Date:** 2026-08-30

## Envelope

Each GUI event contains:

```text
schema_version
event_id
sequence
event_type
timestamp
session_id
task_id
action_id
source
authoritative
core_event_hash
object_ids
payload
```

`sequence` orders events inside the GUI journal. `event_id` identifies the GUI
event. Canonical object IDs and `core_event_hash` link GUI observations back to
the governed core.

## Authority Rule

An event may be labelled authoritative only when it is mapped from a validated
core event and carries its core event hash. GUI-originated navigation,
selection, replay cursor, worker status, and error events are observational.
They never grant authority.

## Event Types

Version 1 includes session, task, agent-step, tool, governance, selection, EON,
evidence, gate, approval, action, failure, CFEL, file, artifact, workflow,
assurance, replay, navigation, worker, UI-error, and chat events. Chat adds
message, turn-start, stop-request, turn-finish, context-clear, and bounded
activity records. The exact enum is in `ourd_gui/events.py`.

Chat messages are observational GUI records. Agent activity mapped from the
root agent trace is authoritative only when it carries the validated root
event hash. A context-clear event changes future model input projection; it
does not delete or rewrite prior journal entries.

An `icpi_route` activity record may bind a context envelope by ID, signature,
source snapshot, route signature, budget signature, reference/file/evidence and
constraint counts, unresolved-reference count, and total bounded preview bytes.
It never contains file preview bodies, the original prompt, or the structured
model input. The authoritative core `run_started` event binds the model task by
SHA-256 digest and size metrics with `task_body_persisted=false`; it does not
store the task body. Confirmation-required routes additionally carry the exact
accepted confirmation-receipt identity and its route, snapshot, envelope,
budget, model-input digest, count, and pinned-context bindings.

An `icpi_confirmation_receipt` activity record is emitted for both accepted and
rejected decisions. It is non-authoritative and contains deterministic receipt
and confirmation IDs/signatures, the decision, binding kind, route identity,
source snapshot, envelope and budget identities, reference/file counts,
model-input SHA-256, and pinned-context identities. It explicitly sets
`confirmation_prompt_body_persisted=false` and
`confirmation_model_input_body_persisted=false`. A rejected receipt creates no
model turn. An accepted receipt is revalidated against the exact current
snapshot and context before provider invocation.

An `icpi_qwen_bootstrap` activity record captures automatic local-model profile
selection without creating authority. It records the product alias, requested and
resolved model names, exact configured or observed GGUF digest and size, whether
a direct runner and model path were configured, and the non-secret profile log
path. It carries `api_key_persisted=false`; no provider credential or model
response body is stored.

An `icpi_pinned_context` activity record captures each local attach/detach
transition with the route identity, action, pinned-context ID and signature,
bounded path count, and canonical workspace-relative paths. It is explicitly
non-authoritative and carries `preview_bodies_persisted=false`. Context checks,
stale-turn blocks, and explicit refreshes additionally bind baseline/observed
snapshots, freshness, refresh-applied state, deterministic delta signature, and
unchanged/changed/missing/new/indeterminate counts. A subsequent
model-turn `icpi_route` event also records pinned ID/signature/count and is
rejected before dispatch if any pinned path is absent from the exact context
envelope or the pinned draft snapshot differs from the turn envelope.

Unknown core event names map to `AGENT_STEP` while preserving the original core
event type in the payload. Unknown future GUI event names in a schema-v1
journal also map to `AGENT_STEP` and preserve `unknown_gui_event_type`.
Unsupported GUI schema versions fail closed.

## Replay

`GuiEventJournal` stores events in an append-only hash-chained EventStore. A
replay reduces events through `reduce_event` in sequence order. Replaying the
same valid event stream must produce the same `GuiState.digest`.

GUI replay never invokes the core. Governed plan replay is a separate explicit
dry-run request through `EGCFEngine.replay` and does not reuse historical
approval as current authority.

## Projection

Projection schema version 2 stores session, task, and bounded chat payloads plus
the complete state JSON, event count, and state digest. It is a cache, not
evidence. Canonical facts remain the content-addressed EGCF objects and
validated core event chains.
