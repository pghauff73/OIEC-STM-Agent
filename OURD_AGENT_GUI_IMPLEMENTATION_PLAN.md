# OIEC-STM-Agent GUI Implementation Plan

**System:** OIEC-STM-Agent evidence-governed engineering workbench
**Plan date:** 2026-08-21, Australia/Brisbane  
**Plan status:** Candidate implementation plan; not implementation authority, certification, or release approval  
**Certified implementation baseline:** source snapshot `d1f9ba74cb9fb91228a9924da58eee8f89e2e0f23ead9d42f0eb642f6691b47e`  
**Observed GUI baseline:** this checkout contains no `ourd_gui.py`, `ourd_agent_gui`, or GUI package  
**Technology decision:** Tkinter first; retain renderer-independent view models so a later PySide6 migration does not alter governance semantics  
**First major milestone:** `InteractiveSelectionTrace`

## 1. Executive Decision

The OIEC-STM-Agent GUI will be implemented as an inspectable control and
observability surface over the existing governed core. It will not be a shell
wrapper, a second policy engine, or an alternate mutation path.

The authoritative path remains:

```text
User
  -> GUI view
  -> GUI controller
  -> typed EGCF command or workflow
  -> capability resolution
  -> qualified algorithm selection
  -> evidence requirements
  -> approval manager
  -> EON / executor adapter
  -> verification and rollback
  -> append-only EGCF records
  -> GUI read-model projection
```

The GUI may request, explain, visualize, compare, and replay operations. It may
not grant authority, invent evidence, directly mutate repository files, execute
an unregistered callback, or convert model output into approval.

The implementation spine is:

```text
EventBus
  -> CoreEventBridge
  -> SelectionTrace read model
  -> EvidenceView
  -> WorkflowDAG
  -> ArtifactWorkbench
```

The first release should prove one complete interaction: a user submits an
objective, the core compiles it, and the GUI visualizes the exact intent,
capability requirements, candidate algorithms, exclusions, scores,
qualification evidence, selected algorithm, execution plan, and lifecycle.

## 2. Baseline and Change Boundary

### 2.1 Existing core assets to reuse

| Existing component | GUI use |
| --- | --- |
| `ourd.egcf.engine.EGCFEngine` | Sole high-level gateway for command compilation, invocation, authorization, execution, and replay |
| `ourd.egcf.models.IntentRecord` | Authoritative task-intent anchor |
| `CommandInvocation` | Exact command inputs, modifiers, scope, actor, and command-definition binding |
| `CapabilitySpec` and `CapabilityGrant` | Capability ladder and effective authority display |
| `AlgorithmDefinition` | Algorithm metadata, inputs, outputs, invariants, risk, rollback, and provenance |
| `QualificationRecord` | Contextual qualification status and evidence |
| `SelectionDecision` | Candidate, exclusion, score, ranking, winner, and tie-break data |
| `EvidenceRequirement` and `EvidenceArtifact` | Evidence coverage and evidence-detail views |
| `ConfidenceAssessment` | Evidence confidence dimensions, gaps, conflicts, and unknowns |
| `InvariantRecord` and `DecisionRecord` | Governance panels and trace links |
| `CompiledWorkflow` and `ExecutionPlan` | Workflow DAG, risk, approval, budget, scope, and rollback views |
| `ApprovalRecord` | Exact-plan human approval display and validation |
| `ExecutionRecord` and `RollbackRecord` | Execution status, output, usage, and rollback history |
| `FailureRecord` | CFEL failure and retry views |
| `AssuranceCase` | Task assurance summary and export |
| `ArtifactRecord` | Artifact index, provenance, and preview lookup |
| `EGCFStore` | Canonical content-addressed object access and rebuildable projection |
| `EventStore` | Append-only hash-chained history and replay source |
| `Lifecycle` | Canonical workflow state display |
| `Workspace` | Canonical path validation and safe repository reads |

### 2.2 Missing GUI capabilities

The current checkout does not yet contain:

- a GUI application or console entry point;
- a typed GUI event bus;
- live bridging from the EGCF event log to GUI events;
- session and task projections;
- renderer-neutral read models;
- a `SelectionTrace` assembler;
- graph, evidence, diff, JSON, or artifact widgets;
- GUI-specific persistence or tests;
- a non-blocking worker boundary for engine calls.

Therefore the first phase is a controlled scaffold, not a literal extraction
from an existing monolithic `ourd_gui.py`. If an external prototype is supplied
later, its behavior should be migrated into the planned views and controller;
its direct callbacks must not become an additional authority path.

### 2.3 Source and certification boundary

The certified baseline above remains a historical record. Adding this plan or
implementing the GUI creates a new source snapshot. No new GUI implementation
is certified until the changed snapshot has deterministic validation and exact
human approval of its candidate and validation hashes.

## 3. Goals

1. Make intent, scope, capability, algorithm selection, evidence, approval,
   execution, rollback, failure, and assurance state visible.
2. Preserve a clickable chain from task intent to every governing object.
3. Keep all C3 or higher mutations behind the existing deterministic core.
4. Keep the Tk main loop responsive while commands, tests, and projections run.
5. Reconstruct a task view from persisted events and content-addressed objects.
6. Make selection rejection reasons as visible as the selected algorithm.
7. Make evidence gaps and approval limits visually prominent.
8. Support progressive delivery without committing early to a heavy GUI stack.
9. Keep GUI state separate from canonical engineering evidence.
10. Provide deterministic fixtures and headless tests for each major view model.

## 4. Non-Goals

- Reimplementing `EGCFEngine`, `PolicyEngine`, EON, the transaction manager, or
  approval validation in GUI code.
- Executing raw filesystem mutations from a button, tree view, editor, preview,
  drag-and-drop operation, or integrated terminal.
- Treating a local or remote model as an approval authority.
- Replacing canonical EGCF objects with GUI-specific copies.
- Implementing every proposed view in the first milestone.
- Migrating to PySide6 before interaction contracts and read models stabilize.
- Building a general-purpose IDE, source editor, debugger, or terminal emulator
  during the `InteractiveSelectionTrace` milestone.
- Rendering arbitrary HTML, scripts, or untrusted active content from artifacts.
- Allowing replay to reuse stale approval for C3-C5 execution.
- Representing proposal, simulation, or model critique as successful execution.

## 5. Preserved Safety Invariants

1. `GUIAuthority <= AgentAuthority`.
2. `Authority <= Evidence` for any action requiring evidence.
3. Only the core may resolve capability, qualify algorithms, authorize plans,
   execute EON actions, validate postconditions, or perform rollback.
4. GUI views are projections; canonical EGCF records remain authoritative.
5. C4 and C5 remain fail-closed until the core explicitly supports them.
6. A GUI approval is bound to the exact `ExecutionPlan`, plan hash, source
   snapshot, constraints, expiry, and use limit accepted by the core.
7. Model output is labelled proposal evidence and cannot set `human=True`.
8. Evidence gaps, conflicts, unknowns, stale records, and unavailable artifacts
   remain visible; the GUI may not silently suppress them.
9. Simulation results remain visibly distinct from real execution.
10. Historical records are append-only. Corrections create new records or
    supersedence links rather than rewriting prior evidence.
11. GUI preferences may be mutable, but they are not engineering evidence.
12. No view or widget may import a mutating adapter directly.
13. No view callback may call `Path.write_text`, `os.remove`, `subprocess`, or an
    executor. All action requests go through the controller.
14. Repository paths are canonicalized by `Workspace` before reading or display.
15. The Tk main thread owns widgets; worker threads communicate only by events.

## 6. Target Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Tkinter views and widgets                                           │
│ repository | task | conversation | selection | evidence | workflow │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ intents and view actions
┌──────────────────────────────▼──────────────────────────────────────┐
│ GuiController                                                       │
│ task lifecycle | command dispatch | approval workflow | navigation  │
└───────────────┬───────────────────────────────┬─────────────────────┘
                │                               │
┌───────────────▼────────────────┐  ┌───────────▼─────────────────────┐
│ CoreGateway                    │  │ GuiEventBus / GuiStateReducer   │
│ short-lived EGCFEngine calls   │  │ typed queue and replay          │
│ no policy duplication          │  │ renderer-neutral state          │
└───────────────┬────────────────┘  └───────────▲─────────────────────┘
                │                               │
┌───────────────▼────────────────────────────────┴────────────────────┐
│ EGCF canonical state                                                │
│ objects | artifacts | append-only events | SQLite projection        │
└───────────────┬─────────────────────────────────────────────────────┘
                │ authoritative event/object references
┌───────────────▼─────────────────────────────────────────────────────┐
│ CoreEventBridge / ReadModelRepository                               │
│ event mapping | object hydration | SelectionTrace | evidence graph  │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.1 Layer responsibilities

| Layer | May do | Must not do |
| --- | --- | --- |
| Views | Render immutable view models, send typed user intents | Open the core store, execute commands, or mutate files |
| Widgets | Render JSON, graphs, diffs, badges, and artifact previews | Interpret governance or infer approval |
| Controller | Coordinate tasks, workers, navigation, and exact approval requests | Reimplement capability or evidence gates |
| Core gateway | Invoke existing typed core APIs and return object IDs/results | Broaden authority or substitute algorithms |
| Event bridge | Map canonical events into GUI events and hydrate references | Rewrite or reorder canonical events |
| Read-model repository | Build query-oriented projections from canonical objects | Become a second canonical database |
| GUI persistence | Store preferences, session navigation, and rebuildable indexes | Duplicate evidence or certify outcomes |

### 6.2 Engine lifetime and locking

`EGCFStore` currently owns an exclusive workspace lock. The GUI must therefore
not retain one `EGCFEngine` for the entire desktop session. The `CoreGateway`
will open a short-lived engine context per compile, invoke, authorize, execute,
or replay job and close it when the operation completes.

Read views should use a dedicated read-only query path over the SQLite
projection and immutable object files. Until that query path exists, read
refreshes may use short-lived `EGCFStore` contexts. The event tailer reads only
complete newline-terminated records and must tolerate a partially appended last
line while another process is writing.

## 7. Proposed Source Layout

```text
ourd_gui/
├── __init__.py
├── __main__.py
├── app.py
├── controller.py
├── events.py
├── state.py
├── core_gateway.py
├── read_models.py
├── selection_trace.py
├── persistence.py
├── commands.py
├── styles.py
├── views/
│   ├── __init__.py
│   ├── shell.py
│   ├── repository.py
│   ├── tasks.py
│   ├── conversation.py
│   ├── selection.py
│   ├── governance.py
│   ├── evidence.py
│   ├── algorithms.py
│   ├── workflow.py
│   ├── eon.py
│   ├── cfel.py
│   ├── artifacts.py
│   ├── approvals.py
│   ├── assurance.py
│   └── terminal.py
└── widgets/
    ├── __init__.py
    ├── json_view.py
    ├── graph_view.py
    ├── diff_view.py
    ├── status_badge.py
    ├── object_link.py
    ├── property_grid.py
    └── artifact_preview.py

tests/gui/
├── __init__.py
├── fixtures.py
├── test_events.py
├── test_state.py
├── test_core_gateway.py
├── test_read_models.py
├── test_selection_trace.py
├── test_selection_view.py
├── test_evidence_view.py
├── test_approval_flow.py
├── test_replay.py
└── test_gui_safety.py
```

The project scripts should eventually add:

```toml
oiec-stm-gui = "ourd_gui.app:main"
ourd-gui = "ourd_gui.app:main"  # compatibility alias
```

The build backend must include `ourd_gui/**/*.py` in wheels and source
distributions. GUI tests remain under the repository-level `tests/` hierarchy
to match the current project convention and stay out of the runtime wheel.

## 8. Typed GUI Event System

### 8.1 Event envelope

The initial user-proposed event shape should be strengthened with ordering and
canonical provenance:

```python
@dataclass(frozen=True)
class AgentEvent:
    event_id: str
    sequence: int
    event_type: AgentEventType
    timestamp: str
    session_id: str
    task_id: str
    action_id: str
    source: str
    authoritative: bool
    core_event_hash: str
    object_ids: tuple[str, ...]
    payload: Mapping[str, Any]
```

`source` distinguishes `ui`, `controller`, and `egcf`. Only events with a valid
`core_event_hash` or canonical object reference may be labelled authoritative.
UI events such as panel selection or prompt edits remain provisional.

### 8.2 Event types

```text
SESSION_OPENED
SESSION_CLOSED
TASK_STARTED
TASK_FINISHED
TASK_SELECTED
AGENT_STEP
TOOL_REQUESTED
TOOL_COMPLETED
GOVERNANCE_UPDATED
SELECTION_UPDATED
EON_CREATED
EVIDENCE_UPDATED
GATE_DECIDED
APPROVAL_REQUIRED
APPROVAL_RECORDED
APPROVAL_REJECTED
ACTION_STARTED
ACTION_FINISHED
FAILURE_DETECTED
CFEL_UPDATED
FILE_CHANGED
ARTIFACT_CREATED
WORKFLOW_UPDATED
ASSURANCE_UPDATED
REPLAY_POSITION_CHANGED
UI_ERROR
```

### 8.3 Event bus contract

The bus provides:

- thread-safe `publish(event)`;
- typed `subscribe(event_type, handler)`;
- `unsubscribe(token)`;
- monotonic in-session sequence numbers;
- bounded queue delivery into Tk via `root.after()`;
- subscriber failure isolation;
- deterministic replay from a saved GUI event stream;
- no widget access from worker threads;
- no persistence of secrets before existing redaction.

### 8.4 Canonical event mapping

The `CoreEventBridge` maps existing EGCF event types without erasing the source
identity. Examples:

| EGCF event | GUI event |
| --- | --- |
| `egcf_object_registered` for an `intent` | `TASK_STARTED` or `AGENT_STEP` |
| `egcf_execution_plan_created` | `EON_CREATED` and `WORKFLOW_UPDATED` |
| `egcf_human_approval` | `APPROVAL_RECORDED` |
| `egcf_node_executed` | `ACTION_FINISHED` |
| `egcf_workflow_completed` | `TASK_FINISHED` |
| `egcf_evidence_collected` | `EVIDENCE_UPDATED` |
| `egcf_object_superseded` | `GOVERNANCE_UPDATED` |
| `egcf_candidate_certified` | `ASSURANCE_UPDATED` |

Unknown future event types remain available as generic `AGENT_STEP` events
with their original type preserved in the payload.

## 9. Session and Task Read Model

### 9.1 Projection records

Session and task concepts are GUI navigation projections, not new governance
authority. They refer to existing canonical object IDs.

```python
@dataclass(frozen=True)
class GuiSession:
    session_id: str
    repository_root: str
    opened_at: str
    source_snapshot_at_open: str
    task_ids: tuple[str, ...]

@dataclass(frozen=True)
class GuiTask:
    task_id: str
    session_id: str
    title: str
    status: str
    intent_ids: tuple[str, ...]
    invocation_ids: tuple[str, ...]
    selection_ids: tuple[str, ...]
    compiled_workflow_ids: tuple[str, ...]
    execution_plan_ids: tuple[str, ...]
    execution_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    failure_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    assurance_case_ids: tuple[str, ...]
```

### 9.2 Task identity

For an in-process request, the controller creates a GUI task ID before invoking
the core and records it in GUI events. The first resulting `IntentRecord`
becomes the authoritative task anchor. During replay or import, a task may be
reconstructed by grouping records through intent, invocation, workflow, plan,
and execution references.

### 9.3 State reducer

`GuiState` is immutable or copy-on-write from the views' perspective. A single
reducer applies `AgentEvent` values and produces:

- current repository and source snapshot;
- sessions and ordered task summaries;
- selected task, object, evidence item, algorithm, workflow node, and artifact;
- capability ladder state;
- approval request state;
- worker and connection status;
- panel filters, tabs, and replay cursor;
- non-authoritative warnings.

Views render state and dispatch commands. They do not update shared state
directly.

## 10. Core Gateway and Query Boundary

### 10.1 Command gateway

`CoreGateway` is the only GUI module allowed to instantiate `EGCFEngine`.

```python
class CoreGateway(Protocol):
    def snapshot(self) -> str: ...
    def run_objective(self, request: ObjectiveRequest) -> CoreResult: ...
    def invoke(self, request: CommandRequest) -> CoreResult: ...
    def authorize(self, request: ApprovalRequest) -> CoreResult: ...
    def execute(self, request: ExecutionRequest) -> CoreResult: ...
    def replay(self, request: ReplayRequest) -> CoreResult: ...
```

All requests carry exact scope, evidence IDs, approval mode, risk, rollback,
budget, timeout, trace, record, strict, and simulation fields. The GUI must not
drop universal modifiers when translating a form into a core invocation.

### 10.2 Read-model repository

The read path provides typed query methods:

```python
get_object(object_id)
list_objects(object_type, filters)
get_selection_trace(selection_id)
get_workflow_graph(compiled_workflow_id)
get_evidence_graph(subject_id)
get_capability_status(capability_grant_id)
get_assurance_summary(subject_id)
get_artifact_descriptor(artifact_id)
get_task_projection(task_id)
```

Returned objects are immutable view models. Missing, corrupt, stale, or
superseded objects return explicit diagnostic states rather than empty success.

### 10.3 Controller worker model

- One serialized core-operation worker owns each short-lived engine call.
- Read-model hydration may use a separate bounded worker pool after a read-only
  query API exists.
- Worker results are converted to events and placed on the GUI queue.
- Cancellation is cooperative and never represented as rollback.
- Closing the window blocks new work, requests safe cancellation, drains final
  events, closes resources, and does not terminate unrelated processes.

## 11. `SelectionTrace` Contract

### 11.1 Read model

```python
@dataclass(frozen=True)
class SelectionCandidateView:
    algorithm_id: str
    algorithm_digest: str
    definition_id: str
    status: str
    selected: bool
    qualified: bool
    qualification_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    score_components: Mapping[str, float | int]
    rejection_reasons: tuple[str, ...]
    capability_level: str
    capability_requirements: tuple[str, ...]
    invariants: tuple[str, ...]
    rollback_class: str
    risk_floor: str
    known_failures: tuple[str, ...]
    implementation_kind: str
    implementation_digest: str

@dataclass(frozen=True)
class SelectionTrace:
    selection_id: str
    command_id: str
    intent_id: str
    invocation_id: str
    context_hash: str
    required_capability_level: str
    required_capabilities: tuple[str, ...]
    candidates: tuple[SelectionCandidateView, ...]
    ranking: tuple[str, ...]
    selected_algorithm_id: str
    selected_algorithm_digest: str
    tie_break: str
    evidence_ids: tuple[str, ...]
    source_snapshot_hash: str
```

### 11.2 Assembly algorithm

1. Load the `SelectionDecision` referenced by a compiled workflow node.
2. Load its command definition and the corresponding command invocation.
3. Load each candidate and excluded `AlgorithmDefinition` by exact algorithm
   ID and digest; do not resolve to a newer active version.
4. Load referenced `QualificationRecord` objects.
5. Load qualification and selection evidence objects.
6. Preserve candidate ordering from the recorded ranking and deterministic
   tie-break fields.
7. Merge excluded reasons without interpreting them as a single score.
8. Mark missing records, digest mismatches, expired qualifications, and stale
   source snapshots visibly.
9. Return an immutable trace object suitable for Tkinter or a future Qt view.

### 11.3 Selection view

The first visual implementation uses a deterministic Tkinter `Canvas` with
layered columns:

```text
Intent -> Capability -> Candidate Algorithms -> Filters/Scores -> Selected
```

Candidate cards show:

- selected, qualified, excluded, retired, stale, or missing status;
- algorithm ID and short digest;
- capability and risk badges;
- qualification count;
- evidence count;
- top score components;
- first rejection reason when excluded.

The full details appear in a property panel after selection. The view must not
collapse all score components into an invented percentage unless the core
stores that percentage.

### 11.4 Selection actions

```text
Explain Selection
Compare Candidates
Show Rejections
Show Evidence
Open Qualification
Open Command Definition
Copy Object ID
```

These actions navigate existing records or invoke read-only semantic commands.
They do not rerun selection unless the user explicitly requests a new compile.

## 12. Evidence Binding and Governance Navigation

Every visible node that claims support must expose the exact evidence IDs used.

### 12.1 Evidence detail

The evidence view shows:

- evidence ID and content SHA;
- subject, target, category, producer, method, and oracle;
- source snapshot and creation time;
- success, simulated status, and limitations;
- requirement, claim, command, and algorithm links;
- environment and provenance with redaction preserved;
- file or artifact path only when safe to preview.

### 12.2 Evidence dashboard

The dashboard derives existing confidence dimensions directly from
`ConfidenceAssessment` and coverage from `EvidenceRequirement` plus
`EvidenceArtifact`. It must label any extended vector such as
`(C_I, C_D, C_B, C_T, C_M, C_R)` as a GUI/domain projection unless the core
later stores those dimensions canonically.

The most prominent panel shows:

```text
Verdict / conclusion
Mandatory gaps
Conflicts
Known unknowns
Approval status and scope
Rollback coverage
Source snapshot freshness
```

### 12.3 Backward navigation

Object links implement:

```text
Execution
  -> Plan
  -> Compiled Workflow
  -> Selection Decision
  -> Algorithm Definition
  -> Qualification
  -> Evidence
  -> Intent
```

The navigation history supports Back and Forward without changing task state.

## 13. Application Shell

The initial Tkinter shell uses `ttk.PanedWindow`, `ttk.Notebook`, and a bottom
command bar. It should prioritize information density over decorative styling.

```text
┌───────────────────────────────────────────────────────────────────┐
│ repository | snapshot | backend | capability | worker | event head│
├──────────────┬─────────────────────────────┬──────────────────────┤
│ Repository   │ Conversation / Selection    │ Governance / Evidence│
│ Tasks        │ Workflow                    │ Algorithms / Details │
├──────────────┼─────────────────────────────┼──────────────────────┤
│ Artifacts    │ Trace timeline              │ EON / CFEL / Approval│
├──────────────┴─────────────────────────────┴──────────────────────┤
│ prompt | command palette | simulate | submit | approval status   │
└───────────────────────────────────────────────────────────────────┘
```

The first sprint may ship a reduced three-pane shell containing Tasks,
SelectionTrace, and Details. Empty future tabs should not be presented as
implemented features.

## 14. Repository and Artifact Safety

### 14.1 Repository explorer

- Uses `Workspace.iter_files()` and canonical paths.
- Starts read-only.
- Ignores `.ourd-agent`, build outputs, and configured ignored directories by
  default, with an explicit toggle for internal state inspection.
- Applies file-size and line-count bounds before preview.
- Detects binary content before decoding.
- Never saves edits during the first major milestone.
- Opens diffs only from canonical execution or transaction records.

### 14.2 Artifact workbench

- Treats `ArtifactRecord` metadata and content SHA as authoritative.
- Stores thumbnails as disposable cache entries keyed by artifact SHA.
- Never modifies an original artifact.
- Supports text, JSON, Markdown, PNG, JPEG, SVG-as-data, logs, and reports first.
- Treats SVG and HTML as untrusted data; no script execution or network loads.
- Adds OBJ, STL, PLY, GLTF, and GLB only after bounded parsers and preview
  isolation exist.

## 15. Capability and Approval Workbench

### 15.1 Capability ladder

The toolbar shows both the configured grant and the requirement of the selected
task or plan:

```text
C0 Observe    granted
C1 Analyse    granted
C2 Simulate   granted
C3 Mutate     gated or granted for exact scope
C4 External   blocked
C5 Critical   blocked
```

Clicking a level shows capability facets, scope, resources, budget, expiry,
issuer, authority hash, approval modes, and use limits. The GUI computes no
grant; it displays `CapabilityGrant` and compiler output.

### 15.2 Approval state machine

```text
NONE
  -> REQUIRED
  -> INSPECTING
  -> SUBMITTED
  -> RECORDED | REJECTED | STALE | EXPIRED | EXHAUSTED
```

The controller keeps authorization and execution as separate user actions.
Successful approval does not automatically execute unless an explicitly scoped
future setting is separately approved and implemented.

### 15.3 Approval dialog

The dialog displays:

- exact action or workflow name;
- plan ID and plan hash;
- source snapshot;
- capability level and risk;
- target files and scope;
- evidence IDs and uncovered requirements;
- invariants and postconditions;
- rollback class and prepared rollback data;
- constraints, expiry, and use limit;
- whether the result is simulation or real execution.

Buttons are:

```text
Approve Scoped
Reject
Inspect Evidence
Inspect Rollback
Cancel
```

`Approve Scoped` calls `EGCFEngine.authorize`. A model-generated event cannot
trigger this method. Stale source snapshots cause the core to reject approval
even if the dialog is still open.

## 16. Workflow, IURM, OURD, and CFEL Views

### 16.1 Workflow DAG

The workflow view consumes `CompiledWorkflow.nodes`, `edges`,
`execution_order`, lifecycle projection, execution records, and rollback graph.
Nodes render as pending, current, passed, failed, blocked, simulated, rolled
back, or partially compensated.

The first implementation uses a deterministic layered layout from topological
order. It does not need an external graph package.

### 16.2 OURD graph

The OURD view initially displays graph output returned by existing semantic
commands. It must distinguish canonical stored relationships from inferred GUI
links. Later domain records may introduce first-class objects, files, symbols,
requirements, tests, and relation types.

### 16.3 IURM dimension explorer

The first version renders returned IURM dimensions and experiment designs as a
table. Interactive `Add Dimension`, `Generate OFAT`, `Generate Pairwise`, and
`Show MVD` actions invoke semantic commands through the controller. The GUI
does not independently determine experimental coverage.

### 16.4 CFEL failure viewer

The viewer combines `FailureRecord`, execution failure state, rollback state,
and any legacy collision records exposed by the core. It displays expected,
observed, active dimension, frozen dimensions, evidence, retry count, novelty,
and status. `Create Regression Test` initially creates a proposed semantic
command; it does not write a test file directly.

## 17. Command Palette, Terminal, Models, and Replay

### 17.1 Command palette

`Ctrl+K` searches a static registry of GUI commands and the checked-in semantic
command catalog. Each entry declares whether it is navigation, read-only
invocation, simulation, mutation request, approval, or replay.

### 17.2 Integrated terminal

The terminal is deferred until EON and approval views are complete. Its first
version is a command transcript and bounded command-submission view, not an
unrestricted PTY.

- Read-only commands are classified and executed through a qualified adapter.
- Mutating commands require a compiled semantic command and EON binding.
- Output is captured, redacted, bounded, and linked to execution evidence.
- Shell metacharacters are not passed through as an implicit escape hatch.
- The terminal never bypasses the repository scope or sandbox policy.

### 17.3 Model backend panel

The panel is observational first. It displays configured backend, exact model,
quantization, context, latency, memory, device residency, provenance, and last
health check where those facts exist. Backend switching or model lifecycle
actions are separate governed commands. Model proposals remain visibly
non-authoritative.

### 17.4 Replay mode

Replay has two modes:

1. **GUI event replay:** reconstructs the interface without invoking the core.
2. **EGCF plan replay:** calls `EGCFEngine.replay`, recompiles the historical
   plan, compares graph and snapshot hashes, and requires reauthorization for
   C3-C5.

Playback controls affect the projection cursor only. They never re-execute a
plan unless the user explicitly chooses governed plan replay.

## 18. Persistence Model

Canonical objects remain in the existing EGCF store. GUI-only data is isolated:

```text
.ourd-agent/
├── egcf/                         canonical existing EGCF state
└── gui/
    ├── preferences.json          mutable, atomic, non-authoritative
    ├── events.jsonl              append-only GUI interaction stream
    ├── projection.sqlite3        rebuildable GUI session/task index
    ├── layouts/                  named user layout presets
    └── cache/                    disposable thumbnails and render cache
```

The GUI must not create parallel canonical directories for evidence,
decisions, assurance, or artifacts. It references existing typed IDs instead.

Preferences include window geometry, pane sizes, selected tabs, filters, open
object IDs, recent repositories, and accessibility settings. Secrets, approval
content, command output, or model prompts are not stored in preferences.

GUI event projection follows the same rule as EGCF storage: the event stream is
canonical for GUI navigation history, and SQLite is rebuildable. A corrupted
GUI projection must not affect EGCF execution or evidence.

## 19. Implementation Phases and Release Gates

### Phase 0 - Contract baseline and fixtures

**Deliverables**

- Record the certified core baseline and observed absence of GUI source.
- Define GUI invariants, event schema, task projection, and authority boundary.
- Add representative immutable test fixtures for selection, workflow,
  evidence, approval-required, execution-success, and failure cases.
- Define a fixture schema version and digest each fixture bundle.

**Gate**

- Fixtures load through the same read-model code used by the GUI.
- No fixture requires a model or network connection.
- No GUI module imports mutating adapters.

### Phase 1 - GUI v0.3 application scaffold

**Deliverables**

- Add `ourd_gui` package, canonical `oiec-stm-gui` entry point, legacy
  `ourd-gui` alias, and build-backend inclusion.
- Implement `app.py`, `controller.py`, `events.py`, `state.py`, and minimal
  `views/shell.py`.
- Open a repository, display source snapshot, and close cleanly.
- Add worker-to-Tk queue polling and structured error display.
- Add a placeholder-free Tasks, Selection, and Details layout.

**Gate**

- Application launches with `python3 -m ourd_gui --repo <path>`.
- The Tk main thread remains responsive during a delayed worker fixture.
- Closing the window releases all threads and store locks.
- Wheel contains the GUI package and entry point.

### Phase 2 - Event bus, core bridge, and task projection

**Deliverables**

- Implement typed `AgentEvent`, event enum, bus, state reducer, and navigation
  commands.
- Map existing EGCF events and hydrate object references.
- Add GUI event persistence and rebuildable task/session projection.
- Implement short-lived `CoreGateway` operations.
- Add task list, status badges, and trace timeline.

**Gate**

- Replaying the same GUI event file produces the same `GuiState` digest.
- A partially written core event line does not crash or invent an event.
- Unknown core events remain inspectable.
- No event is labelled authoritative without a core hash or object ID.

### Phase 3 - GUI v0.4 `SelectionTrace` read model

**Deliverables**

- Implement exact-record `SelectionTrace` assembly.
- Resolve command definition, invocation, algorithm, qualification, evidence,
  candidate, exclusion, ranking, score, and tie-break records.
- Add stale, missing, superseded, and digest-mismatch diagnostics.
- Add deterministic comparison and filtering.

**Gate**

- Every candidate and excluded algorithm in a recorded decision appears once.
- The selected algorithm ID and digest match the recorded decision exactly.
- Rejection reasons are preserved verbatim as data.
- No active/newer algorithm silently replaces the recorded definition.

### Phase 4 - `InteractiveSelectionTrace` graphical milestone

**Deliverables**

- Implement layered selection graph on Tkinter `Canvas`.
- Add algorithm cards, capability/risk/status badges, selection highlighting,
  keyboard navigation, scrolling, zoom presets, and detail panel.
- Bind algorithm, qualification, evidence, invariant, and command-definition
  object links.
- Add Explain, Compare, Rejections, and Evidence actions.

**Gate**

- Clicking any candidate shows why it was admitted or rejected.
- Clicking any evidence badge opens the exact evidence record.
- Selected and rejected states remain distinguishable without relying on color.
- A trace with at least 100 candidate nodes remains usable and does not block
  the UI thread during assembly.
- The milestone scenario from Section 22 passes end to end.

### Phase 5 - GUI v0.5 OURD and IURM views

**Deliverables**

- Add domain graph projection and scope highlighting.
- Add IURM dimension, baseline, coverage, interaction, and MVD tables.
- Route experiment-generation controls through semantic commands.
- Cross-link files, symbols, tests, invariants, evidence, and workflow nodes.

**Gate**

- Inferred GUI relationships are labelled separately from canonical relations.
- One active IURM dimension remains visually explicit.
- No experiment control mutates source without an EON plan.

### Phase 6 - GUI v0.6 evidence dashboard

**Deliverables**

- Add evidence requirements, artifacts, confidence, conflicts, and history.
- Add mandatory-gap panel and approval-scope summary.
- Add evidence graphs and coverage visualizations.
- Add JSON and Markdown evidence export.

**Gate**

- Missing mandatory evidence is visually blocking.
- Simulated evidence cannot be displayed as real execution evidence.
- Export preserves IDs, hashes, limitations, and source snapshots.

### Phase 7 - GUI v0.7 EON, capability, and approval workbench

**Deliverables**

- Add execution-plan and EON action inspector.
- Add C0-C5 ladder and effective grant details.
- Add exact scoped approval dialog, rejection, expiry, and use-limit display.
- Add simulation, authorization, execution, and rollback controls.

**Gate**

- Views contain no direct mutation calls.
- Stale-snapshot approval fails closed.
- Authorization and execution remain separate actions.
- C4 and C5 remain blocked by the core.
- Rejected approval produces no execution record.

### Phase 8 - GUI v0.8 workflow DAG, CFEL, and replay

**Deliverables**

- Add workflow lifecycle DAG and execution overlay.
- Add failure, collision, retry, and rollback views.
- Add GUI event replay and governed EGCF replay.
- Add task-to-task and replay-to-original navigation.

**Gate**

- GUI replay performs no core execution.
- EGCF replay reports graph/snapshot equality and reauthorization requirements.
- Failure details preserve expected, observed, dimensions, evidence, and retry
  identity.

### Phase 9 - GUI v0.9 artifact, algorithm, comparison, and terminal tools

**Deliverables**

- Add artifact gallery and bounded previews.
- Add algorithm database search and qualification history.
- Add session comparison for selections, evidence, files, commands, failures,
  approvals, duration, and cost.
- Add observational model backend panel.
- Add governed bounded terminal transcript.
- Add optional geometry previews after parser safety tests pass.

**Gate**

- Artifact previews cannot execute active content.
- Comparison distinguishes missing data from equal data.
- Terminal commands are classified, traced, and routed through the core.
- Geometry parsers enforce size, recursion, and resource limits.

### Phase 10 - GUI v1.0 assurance, accessibility, and hardening

**Deliverables**

- Add assurance viewer and JSON, Markdown, and static HTML export.
- Add keyboard-complete navigation, screen-reader labels where Tk permits,
  scalable fonts, reduced motion, and non-color status encoding.
- Add performance profiling, large-session virtualization, crash recovery, and
  compatibility documentation.
- Freeze public GUI event and read-model schema version 1.

**Gate**

- Full deterministic GUI and core test suites pass.
- Event replay and projection rebuild pass from a clean checkout.
- No security invariant in Section 5 is violated.
- A new exact-snapshot validation bundle and human approval are recorded.

## 20. Immediate Four-Sprint Implementation Sequence

### Sprint A - Component scaffold

**Files**

```text
ourd_gui/__init__.py
ourd_gui/__main__.py
ourd_gui/app.py
ourd_gui/controller.py
ourd_gui/events.py
ourd_gui/state.py
ourd_gui/views/__init__.py
ourd_gui/views/shell.py
tests/gui/test_events.py
tests/gui/test_state.py
tests/gui/test_app_smoke.py
```

**Work**

1. Create the application entry point and parse `--repo`.
2. Validate the repository through `Workspace`.
3. Create the three-pane shell and status toolbar.
4. Implement event queue delivery and immutable state reduction.
5. Add worker lifecycle and structured error events.
6. Add packaging support without changing core behavior.

**Acceptance**

- The app opens an empty workbench for the current repository.
- Snapshot, repository path, capability status placeholder, worker status, and
  event head area are visible.
- Unit tests prove ordered delivery, unsubscribe, subscriber isolation, and
  deterministic state reduction.

### Sprint B - `SelectionTrace` model

**Files**

```text
ourd_gui/core_gateway.py
ourd_gui/read_models.py
ourd_gui/selection_trace.py
tests/gui/fixtures.py
tests/gui/test_core_gateway.py
tests/gui/test_selection_trace.py
```

**Work**

1. Add short-lived core and read-only query gateways.
2. Create immutable algorithm, qualification, and selection view models.
3. Assemble traces by exact object ID and digest.
4. Preserve exclusions, scores, ranking, tie-break, and evidence IDs.
5. Add diagnostics for stale snapshot and missing objects.
6. Seed deterministic fixtures from a minimal temporary EGCF workspace.

**Acceptance**

- A recorded `SelectionDecision` round-trips into a stable trace digest.
- Candidate and excluded counts match canonical records.
- Missing evidence appears as a diagnostic node, not an exception or omission.

### Sprint C - Graphical selection view

**Files**

```text
ourd_gui/views/selection.py
ourd_gui/widgets/graph_view.py
ourd_gui/widgets/status_badge.py
ourd_gui/widgets/property_grid.py
tests/gui/test_selection_view.py
```

**Work**

1. Implement deterministic column and row layout.
2. Render intent, capability, candidate, filter/score, and winner layers.
3. Add selection, hover, keyboard focus, scroll, and zoom presets.
4. Render status with icon, text, shape, and color.
5. Publish object-selection events without loading records in the widget.

**Acceptance**

- The view renders selected and rejected algorithms from fixture traces.
- Keyboard navigation reaches every node.
- Resizing preserves semantic order and selected object identity.
- Rendering never calls the core or filesystem.

### Sprint D - Evidence-linked interaction

**Files**

```text
ourd_gui/views/evidence.py
ourd_gui/views/algorithms.py
ourd_gui/widgets/json_view.py
ourd_gui/widgets/object_link.py
tests/gui/test_evidence_view.py
tests/gui/test_selection_evidence_navigation.py
```

**Work**

1. Add exact evidence and qualification detail projections.
2. Link every selection node to algorithm, qualification, and evidence objects.
3. Add Explain Selection, Compare Candidates, Show Rejections, and Show
   Evidence actions.
4. Add navigation history and unresolved-reference diagnostics.
5. Add a milestone scenario using a real compiled EGCF command.

**Acceptance**

- Selecting an algorithm immediately shows why it was selected or rejected,
  applicable invariants, qualifications, evidence, risk, and rollback class.
- Back and Forward restore the same selected object and panel state.
- No displayed support claim lacks a clickable source record.

## 21. Test Strategy

### 21.1 Unit tests

Test:

- event construction, ordering, dispatch, unsubscribe, and subscriber failure;
- event-to-state reduction and deterministic state digest;
- task grouping and navigation history;
- core-event mapping and unknown-event preservation;
- exact object and digest resolution;
- `SelectionTrace` candidate, exclusion, score, and evidence assembly;
- graph layout and hit testing independent of Tk widgets;
- approval request construction without authorization side effects;
- artifact media-type classification and preview limits;
- preference persistence and projection rebuild.

### 21.2 Integration tests

Use temporary repositories and real `EGCFEngine` calls to test:

```text
objective
  -> intent
  -> invocation
  -> selection
  -> compiled workflow
  -> execution plan
  -> GUI event bridge
  -> SelectionTrace
  -> evidence navigation
```

Later integration scenarios cover simulation, approval rejection, exact
approval, execution, rollback, failure, assurance, and replay.

### 21.3 Headless UI tests

- Keep layout calculations and view models testable without Tk.
- Use a withdrawn Tk root where widget construction is required.
- Use `xvfb-run` for Linux smoke tests when a display server is unavailable.
- Generate no screenshots as sole correctness evidence.
- Test focus order, keyboard invocation, resizing, empty state, error state, and
  large trace scrolling.

### 21.4 Safety and adversarial tests

- A view module importing `subprocess`, EON adapters, or transaction managers
  fails a static safety test.
- A malformed object envelope is rejected and shown as corrupt.
- A tampered event chain is not replayed as authoritative.
- A partial event line is retried after completion.
- A stale plan cannot be approved.
- A model-originated event cannot invoke human authorization.
- C4 and C5 requests display refusal without an execution control.
- A malicious artifact filename cannot escape cache or preview directories.
- Oversized JSON, deeply nested data, and binary files are bounded.
- Secret-like fields remain redacted in detail and export views.

### 21.5 Performance targets

Targets should be measured and adjusted after the first baseline:

- visible shell within 2 seconds on the reference host;
- no synchronous GUI callback longer than 50 ms for normal interactions;
- event-to-state-to-render latency below 100 ms for ordinary records;
- task list virtualization or incremental loading beyond 1,000 tasks;
- selection graph interaction remains responsive at 100 candidates;
- artifact thumbnails generated off the Tk thread;
- read-model cache bounded by count and total bytes.

Performance targets do not override correctness or evidence gates.

## 22. First Major Milestone Scenario

### Scenario

The user enters:

```text
Implement AxialProfile
```

### Required result

1. The GUI creates a task and submits the objective with `why`, `graph`,
   `trace`, and `record` enabled; it does not request mutation by default.
2. The core creates an intent and compiles a workflow or returns a typed
   interpretation result.
3. The event bridge attaches resulting object IDs to the task.
4. The Selection view shows:

```text
Intent
  -> Required Capabilities
  -> Candidate Algorithms
  -> Qualification and exclusion filters
  -> Score components and ranking
  -> Selected Algorithm
  -> Evidence
  -> Compiled Workflow / EON boundary
```

5. Clicking any candidate shows inputs, outputs, status, qualification,
   invariants, cost fields, known failures, evidence, and rejection reasons.
6. Clicking evidence opens the exact immutable record and provenance.
7. If no qualified algorithm exists, the trace remains useful and displays all
   exclusions rather than reducing the result to an error dialog.
8. No repository mutation occurs during this milestone scenario.

### Milestone definition of done

- The full chain is visible and navigable from one GUI task.
- Every displayed object has an exact canonical ID or is labelled as a GUI-only
  projection.
- Selected and rejected candidates are both inspectable.
- Evidence limitations and missing references are visible.
- GUI event replay reconstructs the same task view.
- Tests pass headlessly.
- Packaging and startup instructions are documented.

## 23. Risk Register

| Risk | Mitigation |
| --- | --- |
| GUI duplicates core authority | Enforce one `CoreGateway`; static tests forbid mutating imports in views |
| Tk freezes during commands or large projections | Worker boundary, bounded queues, incremental hydration, no widget access off main thread |
| Exclusive store lock blocks CLI or other agents | Short-lived engine contexts and read-only query path |
| Event stream and GUI state drift | Canonical core hashes, sequence numbers, rebuildable reducer, replay tests |
| Selection view invents meaning | Render stored score components and reasons; label GUI-derived summaries |
| Large histories exhaust memory | Paging, lazy hydration, bounded caches, virtualized lists |
| Approval becomes a one-click bypass | Exact-plan dialog, separate authorize/execute controls, stale-plan checks |
| Artifact preview executes content | Passive parsers, no script/network execution, sandboxed cache, size limits |
| GUI persistence leaks secrets | Redaction, allowlisted preference fields, no prompt/output storage by default |
| Future Qt migration rewrites semantics | Renderer-neutral events, state, read models, and controller protocols |
| Missing prototype causes incorrect refactor assumptions | Treat current work as greenfield scaffold; migrate external prototype only after audit |

## 24. Documentation Deliverables

Implementation should add and maintain:

- `README.md` GUI quick start and authority warning;
- `docs/GUI_ARCHITECTURE.md` layer and threading model;
- `docs/GUI_EVENT_SCHEMA.md` event types, provenance, and replay;
- `docs/GUI_SELECTION_TRACE.md` assembly and visualization rules;
- `docs/GUI_SAFETY.md` prohibited paths and approval boundary;
- `docs/GUI_TESTING.md` headless and fixture workflows;
- generated command-palette entries from the checked-in command catalog;
- versioned GUI state migration notes.

## 25. Release States

```text
DESIGNED
  -> SCAFFOLDED
  -> EVENT_REPLAYABLE
  -> SELECTION_TRACE_COMPLETE
  -> INTERACTIVE_SELECTION_TRACE
  -> GOVERNANCE_WORKBENCH
  -> FEATURE_COMPLETE
  -> DETERMINISTICALLY_VALIDATED
  -> HUMAN_APPROVAL_REQUIRED
  -> CERTIFIED
```

No earlier state implies the next. In particular, a visually complete GUI is
not certified, a passing model review is not deterministic validation, and
deterministic validation is not human approval.

## 26. Implementation Order

The required order is:

```text
1. EventBus and state reducer
2. CoreEventBridge and read-model repository
3. SelectionTrace assembler
4. Interactive SelectionTrace view
5. EvidenceView and object navigation
6. WorkflowDAG
7. EON and approval workbench
8. CFEL and replay
9. ArtifactWorkbench
10. Extended OURD, IURM, model, terminal, and geometry tools
```

This order keeps the first implementation focused on the system's distinguishing
value: exposing the evidence-governed reasoning chain rather than merely adding
more desktop controls around command execution.
