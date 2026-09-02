# OURD GUI Architecture

**Architecture version:** 1  
**Date:** 2026-08-31
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

### Formal-Writing Subsystem

```text
standalone FormalWritingApplication or embedded WorkbenchShell
  -> FormalWritingView
  -> typed FormalWritingFormState and FormalWritingExecutionOptions
  -> FormalWritingController (one worker, bounded GUI-only event queue)
  -> FormalWritingService and signed writing contracts
  -> .ourd-agent/writing atomic artifacts
  -> FormalWritingProjectionStore read-only reconstruction
```

- `ourd_gui/formal_writing_gui.py` owns only standalone parsing, Tk lifecycle,
  menus, font scaling, polling, authority selection, and exact-signature
  confirmation.
- `ourd_gui/formal_writing_controller.py` owns asynchronous coordination,
  cooperative cancellation, exact persisted lineage resolution, qualification
  gates, and shared governed-write preparation.
- `ourd_gui/formal_writing_models.py` owns renderer-neutral form, option, job,
  event, input-budget, and governed-preview records.
- `ourd_gui/formal_writing_projection.py` validates complete signed results and
  sources, emits bounded diagnostics for invalid artifacts, preserves source
  freshness, and maps canonical graphs/audits into renderer-neutral records.
- `ourd_gui/views/formal_writing.py` owns widgets and ephemeral selection only.
  It imports no service, agent, transaction, approval, or EON mutation owner.

The CLI and both GUI surfaces compile through the same canonical request
compiler and call the same service. Governed preparation is shared by
`ourd/formal_writing_governance.py`; no GUI-specific mutation path exists.

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
- Formal-writing selection is capped at 500 inputs, 32 MiB per input, and
  256 MiB total. Projection reads cap artifacts at 32 MiB, 500 results, 500
  source artifacts, and 5,000 pages. The view caps graph rendering at 500 nodes
  and 2,000 edges, source display at 200,000 characters, general text at
  500,000 characters, diagnostics at 100,000 characters, and PDF previews at
  four million pixels.
- Formal-writing projections cache validated path/stat snapshots. Source
  freshness is recomputed on every refresh, so the cache cannot hide drift.

## Recovery

The GUI event journal is the replay source. The SQLite task/session projection
is disposable: if its schema, event count, or state digest is invalid, the
controller rebuilds it from the journal. A partial final core-event line is not
consumed until complete. A broken core hash chain fails closed rather than
being presented as authoritative history.

Standalone formal-writing preferences share the atomic GUI preference store
but persist only window geometry, font scale, selected control tab, and one
canonical result ID. Task text, source bodies, drafts, authority contents,
signatures, approvals, and secrets are never stored as GUI preferences.

## Renderer Boundary

Selection, governance, replay, artifact, and assurance models are plain Python
objects independent of Tk. A future Qt renderer may replace widgets, but it
must preserve the same event, read-model, identity, authority, and approval
contracts.
