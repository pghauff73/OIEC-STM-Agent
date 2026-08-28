# OURD GUI Architecture

**Architecture version:** 1  
**Date:** 2026-08-21  
**Status:** implemented candidate; deterministic validation and exact-snapshot human approval remain separate gates

## Authority Path

```text
Tk views
  -> WorkbenchShell
  -> GuiController
  -> CoreGateway
  -> short-lived EGCFEngine
  -> capability, algorithm, evidence, approval, EON, executor
  -> canonical EGCF objects and events
  -> read-only GUI projection
```

Views never import transaction managers, EON adapters, subprocess execution, or
the legacy agent mutation path. The GUI requests operations; the deterministic
core decides whether they are permitted.

## Layers

- `ourd_gui/app.py` owns Tk lifecycle, command routing, preferences, and user-visible errors.
- `ourd_gui/views/` renders repository, task, trace, workflow, governance, evidence, algorithm, EON, CFEL, artifact, replay, comparison, model, performance, and assurance state.
- `ourd_gui/controller.py` owns the event bus, one worker, short-lived core calls, replay projection, and exports.
- `ourd_gui/core_gateway.py` is the only high-level command, authorization, execution, and replay gateway.
- `ourd_gui/read_models.py` validates and reads immutable content-addressed objects without acquiring the writer lock.
- `ourd_gui/events.py` and `ourd_gui/state.py` define public GUI event and read-model schema version 1.
- `ourd_gui/persistence.py` stores the append-only GUI journal, rebuildable SQLite projection, preferences, and non-authoritative exports.

## Threads and Locks

Tk widgets are accessed only on the Tk main thread. Core operations run on one
`ThreadPoolExecutor` worker and return through `AgentEventBus`. Each
`CoreGateway` operation opens and closes `EGCFEngine`, preventing the GUI from
holding the exclusive core store lock for its full lifetime.

The controller polls at 50 ms, drains a bounded event batch, reduces immutable
state, saves the rebuildable projection, and renders changes. Selection trace
assembly also runs on the worker because it may hydrate many immutable objects.

## Large State

- Task rows are loaded incrementally in pages of 500; an off-page selected task remains visible.
- The immutable-object cache is LRU bounded by 2,048 records and 16 MiB by default.
- JSON/detail projection is bounded by depth, item count, string length, and rendered characters.
- Artifact reads and geometry inspection enforce explicit byte limits.
- Performance telemetry keeps only the newest 1,000 samples.

## Recovery

The GUI event journal is the replay source. The SQLite task/session projection
is disposable: if its schema, event count, or state digest is invalid, the
controller rebuilds it from the journal. A partial final core-event line is not
consumed until complete. A broken core hash chain fails closed rather than
being presented as authoritative history.

## Renderer Boundary

Selection, governance, replay, artifact, and assurance models are plain Python
objects independent of Tk. A future Qt renderer may replace widgets, but it
must preserve the same event, read-model, identity, authority, and approval
contracts.
