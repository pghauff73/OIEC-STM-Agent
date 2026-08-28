# OURD GUI Event Schema

**Schema:** `AgentEvent` version 1  
**Date:** 2026-08-21

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
