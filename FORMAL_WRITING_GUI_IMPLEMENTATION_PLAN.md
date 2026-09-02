# Formal Writing GUI Implementation Plan

**Plan version:** 1.0  
**Plan date:** August 31, 2026, Australia/Brisbane  
**Status:** Candidate implementation plan; not implementation authority,
certification, release approval, or evidence that the GUI has been implemented  
**Requested module:** `ourd_gui/formal_writing_gui.py`  
**Canonical writing owner:** `ourd/writing_engine/`  
**Compatibility facade:** `ourd/formal_writing.py`  
**Existing embedded view:** `ourd_gui/views/formal_writing.py`  
**Standalone entry-point decision:** `oiec-stm-formal-writing-gui`  

## 1. Executive Decision

Create `ourd_gui/formal_writing_gui.py` as a thin standalone Tkinter
application and composition root for the existing governed formal-writing
system. It will not become a second writing engine, command compiler, evidence
store, policy engine, audit authority, SAA registry, or mutation path.

The target path is:

```text
User
  -> FormalWritingApplication
  -> FormalWritingView and typed request state
  -> FormalWritingController worker boundary
  -> compile_formal_writing_request
  -> FormalWritingService
  -> signed .ourd-agent/writing artifacts
  -> FormalWritingProjectionStore
  -> document, argument, evidence, and audit projections
```

For an ordinary final-document output request, the path remains:

```text
GUI candidate
  -> exact request signature
  -> exact-snapshot authority manifest
  -> governed transaction and EON action
  -> evidence and human approval
  -> apply, verification, finalization, and rollback
```

The standalone GUI will reuse the existing embedded formal-writing view and
remain compatible with the main `oiec-stm-gui` workbench. The requested module
will own application startup, shutdown, argument parsing, and composition. It
will delegate rendering to views, execution to a controller, writing semantics
to `FormalWritingService`, and authority to the existing governed core.

## 2. Relationship to Existing Plans

This plan is an additive implementation slice under:

- `FORMAL_WRITING_ENGINE_ICPI_IMPLEMENTATION_PLAN.md`, especially Phase 17,
  GUI Source Reader and Writing Workspace;
- `OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md`, especially the view/controller/core
  gateway separation, Tk worker boundary, governance navigation, accessibility,
  and release gates; and
- `COMPLETE_IMPLEMENTATION_STRATEGY.md`, especially canonical ownership,
  current-source evidence, exact-snapshot approval, and no duplicate mutation
  path.

Where those plans and this plan overlap, the stricter governance, evidence,
security, compatibility, or release requirement applies. This plan does not
replace their broader project or release requirements.

## 3. Observed Current Baseline

### 3.1 Repository state

Observed on August 31, 2026:

```text
branch: codex/complete-implementation-strategy
HEAD:   4aa1d13d3a521db13fa4bd96a707c79b828aa33e
```

The worktree contains substantial existing modified and untracked work. The
implementation must preserve unrelated changes, stage only intended files if
later asked to commit, and never treat the Git commit alone as the current
formal-writing source snapshot.

### 3.2 Existing implementation to extend

| Current asset | Observed role | Required decision |
| --- | --- | --- |
| `ourd_gui/views/formal_writing.py` | Embedded read-only artifact view with Writing Runs, Document, Argument Graph, Evidence, and Formal Writing Audit panels | Preserve and evolve into a reusable workbench view |
| `ourd_gui/formal_writing_projection.py` | Reads persisted results and source pages from `.ourd-agent/writing/` | Harden and extend; do not replace with a GUI-owned store |
| `ourd_gui/widgets/graph_view.py` | General layered, zoomable, keyboard-navigable graph widget | Reuse through a formal-writing graph adapter |
| `ourd_gui/views/shell.py` | Owns the existing Formal Writing tab in the main workbench | Preserve embedded use and refresh/navigation behavior |
| `ourd/writing_engine/compiler.py` | Canonical profile list and command-to-operation compiler | Reuse directly; do not copy command mappings into the GUI |
| `ourd/writing_engine/service.py` | Shared execution and persistence owner | Remain the only formal-writing use-case service |
| `ourd/formal_writing_cli.py` | Dedicated CLI, persisted plan/draft lookup, audit gate, and governed write preparation | Use for behavioral parity tests, not as a GUI subprocess |
| `tests/gui/test_formal_writing_projection.py` | One focused projection test | Extend into complete projection/controller/GUI coverage |
| `pyproject.toml` | Current CLI and GUI entry points | Add one standalone formal-writing GUI entry point |

### 3.3 Observed relevant-file hashes

These hashes identify the inspected planning baseline, not a certified release:

```text
ourd_gui/views/formal_writing.py
  5a11db13be33ff4615cb657bbc11b00aee753c3eec4bede8a71d1a7dc7957171
ourd_gui/formal_writing_projection.py
  64581bf6a45e4e9fd21fc5a7512aadc702c58f5415e2bbec2125d565804ad4f4
ourd_gui/widgets/graph_view.py
  bb9a5e1334c873a9d06366f9edf4dbe7df4cc785454ea7a1bdca3782e9f08471
ourd/writing_engine/service.py
  0277a14ffa884b1df07670eff1f58dab6c61d49e21354728588a83263f2a57a6
ourd/writing_engine/compiler.py
  6926adabd892578143f522020f4742e4cdfc0960a3646db401de4552abb05d3d
ourd/formal_writing_cli.py
  25077117fc800f35258334e26b572529a6bf82590d135045c1ffaa7086e9835d
tests/gui/test_formal_writing_projection.py
  409e9a6278de9cecf780a3b77456bb534b253d2b2468969a511160d3f5dfc0b3
pyproject.toml
  58d813c4584a50cacb7c306df47346074a1d4cfa2ac2b58a53ad938489be23d9
```

Any implementation changes invalidate this observed hash set and require a new
validation manifest before a completion or release claim.

### 3.4 Current capability and gap assessment

Implemented now:

- persisted writing-result and source-page projection;
- a writing-run selector;
- a read-only document panel;
- raw JSON argument-graph display;
- evidence source/page selection;
- raw JSON audit and novelty display;
- sentence-to-claim selection and trace projection;
- embedding as a tab in the main workbench; and
- deterministic engine, CLI, schema, and benchmark coverage outside the GUI.

Not yet implemented as a standalone formal-writing GUI:

- `ourd_gui/formal_writing_gui.py`;
- a dedicated package entry point;
- a request editor for task, profile, sources, rubrics, and constraints;
- GUI execution of Research, Argument, Plan, Draft, Audit, and Revise;
- a formal-writing-specific asynchronous controller;
- progress and truthful cancellation semantics;
- a rendered argument graph using `GraphView`;
- typed audit metric presentation;
- explicit persisted plan and draft navigation;
- governed output preparation from the standalone workbench;
- malformed-artifact recovery and diagnostics;
- standalone lifecycle, packaging, and headless tests; and
- current exact-source GUI qualification evidence.

## 4. Goals

1. Launch a standalone formal-writing workbench without launching the complete
   AgentICPI application.
2. Preserve the existing embedded Formal Writing tab and avoid divergent GUI
   behavior between standalone and integrated use.
3. Let a user construct a typed request without learning every CLI option.
4. Execute the complete read-only pipeline: Research, Argument, Plan, Draft,
   Audit, Explain, and Export References.
5. Support revision from an exact persisted draft identity.
6. Make every rendered material sentence traceable to its claim, evidence,
   reasoning edges, qualifications, limitations, and source artifact.
7. Make audit failures visible and actionable without hiding or weakening the
   underlying deterministic result.
8. Keep long extraction and writing operations off the Tk main thread.
9. Keep normal GUI use offline and read-only toward ordinary workspace files by
   default.
10. Route final document output through the existing governed write path.
11. Provide deterministic non-rendering tests and bounded human visual review.
12. Produce requirement-level evidence for implementation, validation,
   packaging, accessibility, governance, and rollback readiness.

## 5. Non-Goals

The first release will not:

- create a second formal-writing engine or duplicate pipeline logic;
- use `ourd/formal_writing_cli.py` as a subprocess execution backend;
- make model output authoritative;
- automatically accept novelty claims;
- automatically qualify an SAA proposal;
- approve or apply its own governed output;
- add a free-form rich-text editor that permits unsupported material claims to
  bypass the argument graph;
- edit canonical `.ourd-agent/writing` JSON artifacts in place;
- infer missing bibliographic metadata or page labels;
- add network retrieval without an explicit supported policy and capability;
- promise immediate cancellation while a non-cancellable engine phase continues;
- replace the main AgentICPI GUI; or
- claim release certification from focused GUI tests alone.

## 6. Non-Negotiable Invariants

### 6.1 Single semantic owner

`FormalWritingService`, the writing pipeline, and their signed contracts remain
authoritative. Views render state; controllers coordinate work; projections
adapt artifacts. No GUI module decides whether a claim is supported, whether a
document is qualified, or whether a reasoning algorithm is reusable.

### 6.2 Single mutation path

No view callback may write a final document directly. A final output requires
an exact request signature, exact-snapshot authority manifest, governed
transaction, EON action, evidence, human approval, apply, verification, and
rollback. An explicit user export of a diagnostic report is not equivalent to
governed document application and must be labelled accordingly.

### 6.3 Read-only default

Research, argument, planning, drafting, auditing, explaining, and reference
export may create signed evidence and state under `.ourd-agent/writing/`. They
must not mutate ordinary workspace files unless the existing governed write
path is explicitly entered and approved.

### 6.4 Exact identity

The GUI must display and preserve exact request, source, plan, draft, audit,
claim, evidence, and transaction identifiers. A path, title, row number, or
currently selected object is not an acceptable substitute for a canonical ID.

### 6.5 Fail-closed projection

Malformed, incomplete, stale, missing, or signature-invalid artifacts remain
visible as diagnostics and must never be silently treated as valid. The GUI
must not repair canonical artifacts by inference.

### 6.6 Tk thread isolation

The Tk main thread owns every widget. Worker threads may execute services and
construct immutable results, but may not read or mutate Tk objects. UI updates
arrive through a bounded queue polled with `after()`.

### 6.7 Honest progress and cancellation

Progress events identify completed deterministic phases. They do not estimate
unsupported percentages. Cancellation is cooperative at declared engine
checkpoints; if a phase cannot be interrupted, the UI states that cancellation
is pending rather than claiming the operation stopped.

### 6.8 No audit laundering

`QUALIFIED_FORMAL_DOCUMENT`, `REVISION_REQUIRED`, and
`EVIDENCE_INSUFFICIENT` are displayed exactly. The GUI may explain repair
options, but it may not rewrite status, lower thresholds, omit failed checks, or
present potential novelty as established novelty.

### 6.9 Untrusted source isolation

Source text, PDF metadata, OCR text, citations, filenames, and persisted draft
content are untrusted data. They cannot alter authority, system instructions,
tool availability, output paths, network policy, or confirmation requirements.

### 6.10 Compatibility

Existing imports, CLI behavior, main-workbench integration, persisted artifact
formats, and formal-writing tests remain compatible. Any schema extension must
be additive or versioned with migration and compatibility tests.

## 7. Target Source Layout

```text
ourd_gui/
├── formal_writing_gui.py             # standalone parser, application, main
├── formal_writing_controller.py      # worker, queue, progress, cancellation
├── formal_writing_models.py          # renderer-neutral form and job models
├── formal_writing_projection.py      # hardened artifact and graph projections
├── app.py                            # existing complete GUI entry point
├── views/
│   ├── formal_writing.py             # reusable workbench view
│   └── shell.py                      # existing embedded integration
└── widgets/
    └── graph_view.py                 # reused general graph widget

tests/gui/
├── test_formal_writing_gui.py
├── test_formal_writing_controller.py
├── test_formal_writing_models.py
├── test_formal_writing_projection.py
└── fixtures_formal_writing.py
```

New files should be added only when they establish a real ownership boundary.
If form state remains small, it may live in `formal_writing_controller.py`
instead of creating `formal_writing_models.py`. If graph adaptation remains
small, it stays in `formal_writing_projection.py` instead of creating another
module.

## 8. Architecture and Ownership

### 8.1 `FormalWritingApplication`

`ourd_gui/formal_writing_gui.py` will provide:

```text
build_parser
FormalWritingApplication
main
```

Responsibilities:

- parse `--workspace` with `--repo` as a compatibility alias;
- accept an optional `--authority` path without granting authority;
- validate and resolve the workspace;
- create the Tk root, styles, controller, and reusable view;
- route window-close to orderly worker shutdown;
- provide standalone menus, accelerators, and status presentation;
- report startup failures without a partially initialized workbench; and
- return a deterministic process exit status.

It must not import or instantiate mutating executor adapters directly.

### 8.2 `FormalWritingController`

The controller coordinates one active writing job at a time.

Proposed API:

```python
class FormalWritingController:
    def submit(self, request: FormalWritingRequest, options: ExecutionOptions) -> str: ...
    def request_cancel(self, job_id: str) -> None: ...
    def poll_events(self) -> tuple[FormalWritingGuiEvent, ...]: ...
    def shutdown(self, *, wait: bool = False) -> None: ...
```

The controller:

- uses `ThreadPoolExecutor(max_workers=1)`;
- creates `FormalWritingService` inside the worker operation;
- emits immutable GUI-only job events clearly labelled non-canonical;
- returns canonical result IDs and artifact paths from the service;
- prevents a second operation while one is active;
- records bounded diagnostic text without copying entire source documents;
- refreshes projections only after service persistence completes; and
- supports deterministic dependency injection for tests.

The controller does not implement claim, evidence, audit, or governance rules.

### 8.3 `FormalWritingView`

The existing view becomes a reusable presentation and input surface. It may:

- expose typed user intents through callbacks;
- render immutable projections;
- maintain ephemeral selection and pane state;
- request source/rubric paths through file dialogs;
- display exact identifiers, warnings, and limitations; and
- navigate between document, graph, evidence, and audit projections.

It may not call `FormalWritingService`, open canonical stores, or write final
documents directly.

### 8.4 `FormalWritingProjectionStore`

The projection store remains read-only. It will:

- parse complete signed artifacts;
- convert raw dictionaries into renderer-neutral projection records;
- expose malformed-artifact diagnostics rather than raising through the UI;
- provide stable sorting and selection identities;
- map the argument graph into `GraphNode` and `GraphEdge` objects;
- map audit metrics into typed status projections;
- expose exact source page, locator, and trace data; and
- remain rebuildable from `.ourd-agent/writing/` artifacts.

It must not become a second persistence database.

## 9. Standalone Command Contract

Canonical launch forms:

```bash
oiec-stm-formal-writing-gui --workspace /path/to/workspace
python3 -m ourd_gui.formal_writing_gui --workspace /path/to/workspace
```

Compatibility alias:

```bash
oiec-stm-formal-writing-gui --repo /path/to/workspace
```

Initial arguments:

```text
--workspace PATH
--repo PATH
--authority PATH
--open-result ID
--profile PROFILE
--task TEXT
--source PATH            repeatable
--rubric PATH            repeatable
--network-policy POLICY
--require-page-accuracy
--allow-ocr
--ocr-language LANGUAGE
```

Command-line defaults initialize visible form state; they do not automatically
start a job unless a later explicit `--run` option is designed and separately
approved. Startup must remain observational by default.

## 10. User Interface Specification

### 10.1 Application shell

```text
┌────────────────────────────────────────────────────────────────────┐
│ Workspace | Status | Current job | Audit status | Authority state │
├─────────────────┬──────────────────────────────────────────────────┤
│ Request         │ Writing Runs                                     │
│ Sources         ├──────────────────────────┬───────────────────────┤
│ Rubrics         │ Document                 │ Argument Graph        │
│ Workflow        ├──────────────────────────┼───────────────────────┤
│                 │ Evidence                 │ Formal Writing Audit  │
└─────────────────┴──────────────────────────┴───────────────────────┘
```

The existing five-region behavior—Writing Runs plus four main workbench
panels—remains recognizable in both standalone and embedded use.

### 10.2 Request editor

Fields:

- task or research question;
- profile;
- genre;
- audience;
- discipline;
- word target;
- citation style;
- locale;
- network policy;
- require page accuracy;
- allow OCR and OCR language; and
- repeatable constraints.

The profile field uses the canonical profile list from
`ourd/writing_engine/compiler.py`. The GUI must not maintain a copied list.

### 10.3 Source and rubric collections

Each selected input displays:

- workspace-relative path;
- media type;
- byte size;
- current content hash when ingested;
- source document ID;
- page count or `reflowable`;
- extraction/OCR state;
- freshness or drift state; and
- remove/inspect actions.

Folder selection expands to a deterministic, displayed manifest before a job
starts. Hidden files, unsupported formats, symlink behavior, and size limits
must follow existing workspace and ingestion policy.

### 10.4 Workflow controls

Primary actions:

```text
Research
Argument
Plan
Draft
Audit
Revise
```

Secondary actions:

```text
Inspect Sources
Locate Passage
Explain Reference
Export References
Refresh Artifacts
Prepare Governed Write
```

Buttons compile through `compile_formal_writing_request`; they do not duplicate
the compiler's operation mapping. Mutating and non-mutating operations must be
visually and semantically distinct.

### 10.5 Document panel

The document panel displays persisted draft text and supports selection only.
For v1, free-form editing is disabled so unsupported material cannot bypass the
graph. Later supervised editing requires a new explicit draft-revision contract
that maps edits back to claims and reruns qualification.

Selecting a sentence highlights its canonical trace and updates the graph,
evidence, and audit panels.

### 10.6 Argument graph panel

Replace raw JSON as the primary display with `GraphView`. Raw JSON remains
available through a details action.

Recommended layers:

```text
Evidence
  -> Premise and definitional claims
  -> Intermediate causal/comparative/interpretive claims
  -> Counterclaims and responses
  -> Thesis or hypothesis
```

Every node must have a non-color status label. Graph selection displays:

- exact claim or evidence ID;
- full statement or locator;
- claim type;
- support status and confidence;
- incoming and outgoing reasoning relations;
- qualifications and limitations;
- graph issue codes; and
- source identities.

### 10.7 Evidence panel

The evidence panel provides:

- source and page selection;
- extracted text;
- physical page index and displayed page label;
- extraction kind and confidence;
- exact selected text and bounded context;
- reference kind and verification status;
- source content hash; and
- optional safe page rendering and geometry highlighting.

PDF rendering and OCR controls remain unavailable or visibly disabled when
their optional dependencies are absent.

### 10.8 Audit panel

The audit panel renders typed metrics and issues, including:

- claim support rate;
- evidence coverage;
- semantic consistency;
- argument connectivity;
- unsupported claim rate;
- counterargument coverage;
- qualification adequacy;
- citation traceability;
- unsupported claim IDs;
- graph issue codes;
- performed checks;
- limitations;
- novelty assessments; and
- final audit status.

`QUALIFIED_FORMAL_DOCUMENT`, `REVISION_REQUIRED`, and
`EVIDENCE_INSUFFICIENT` must remain readable without relying on color.

## 11. Formal-Writing Action Mapping

| GUI action | Canonical operation | Required inputs | Expected artifact/result |
| --- | --- | --- | --- |
| Inspect Sources | `INSPECT_SOURCES` | one or more sources | source registry and ingestion state |
| Locate Passage | `LOCATE_REFERENCE` | task plus sources | verified locators |
| Research | `BUILD_SOURCE_MAP` | task plus sources | source and evidence map |
| Argument | `BUILD_ARGUMENT_MAP` | task plus sources | typed argument graph |
| Plan | `OUTLINE` | task, profile, optional sources/rubrics | persisted formal and document plans |
| Draft | `DRAFT` | persisted plan or complete request | grounded persisted draft |
| Audit | `VALIDATE` | persisted draft or draft path | writing audit and integrity report |
| Revise | `REVISE` | exact persisted draft plus constraints | new draft bound to prior draft SHA |
| Explain Reference | `EXPLAIN_REFERENCE` | selected reference and task | explanation projection |
| Export References | `EXPORT_REFERENCES` | source/citation state | bibliography/reference result |
| Prepare Governed Write | `WRITE` | qualified candidate, outputs, authority, exact signature | prepared transaction and EON action |

Cross-surface equivalence tests must prove that equivalent GUI and CLI inputs
compile to the same `FormalWritingRequest` fields and request signature.

## 12. Job, Progress, and Cancellation Model

### 12.1 Job state

```text
IDLE
  -> QUEUED
  -> RUNNING
  -> CANCEL_REQUESTED
  -> COMPLETED | FAILED | CANCELLED
```

The state model is GUI-only and must be labelled as such. Canonical document
status comes from persisted writing artifacts, not the job state.

### 12.2 Progress events

Where supported by the service, deterministic progress names are:

```text
request_compiled
sources_ingested
references_qualified
meaning_resolved
claims_generated
argument_graph_built
reasoning_path_selected
falsification_completed
draft_rendered
audit_completed
artifacts_persisted
```

Adding progress callbacks to `FormalWritingService.execute` must be additive:

```python
execute(
    request,
    *,
    allow_ocr=False,
    ocr_language="eng",
    prior_draft_text="",
    progress_sink=None,
    cancellation_check=None,
)
```

Default `None` preserves all existing callers.

### 12.3 Cancellation

Cancellation is checked only at deterministic safe boundaries. It must not
leave a partially published canonical artifact. Temporary work is removed or
retained as an explicitly incomplete diagnostic according to existing atomic
persistence rules.

If fine-grained cancellation cannot initially be added, v0 must expose only
`Stop After Current Phase` and state the limitation in the UI and docs.

## 13. Persistence and Projection Rules

1. `FormalWritingService` remains the only writer of canonical writing result,
   draft, source, and algorithm-proposal artifacts.
2. GUI preferences may store pane positions, recent workspace paths, filters,
   selected tabs, and accessibility settings.
3. GUI preferences must not store source bodies, document drafts, authority
   contents, approvals, secrets, or model prompts.
4. Projection refresh reads only complete files and handles disappearance,
   malformed JSON, unknown schema fields, and permission errors.
5. Invalid artifacts produce a diagnostic projection containing path, failure
   class, bounded message, and observation time. They do not produce a valid
   writing result.
6. Result ordering is deterministic and should prefer persisted creation order
   or signed IDs rather than filesystem enumeration accidents.
7. Selection survives refresh only when the exact selected ID remains present.
8. A persisted plan or draft ID must resolve through the same semantics as the
   dedicated CLI.

## 14. Governed Write Design

### 14.1 Entry condition

`Prepare Governed Write` is enabled only when:

- a persisted draft exists;
- the exact draft is selected;
- the writing audit is present;
- output paths are explicitly selected; and
- no background job is active.

Whether the UI requires `QUALIFIED_FORMAL_DOCUMENT` before preparation must
match the accepted governed service policy. The UI may recommend qualification
but must not invent a policy that conflicts with the core.

### 14.2 Confirmation dialog

The dialog displays:

- task;
- profile;
- exact draft ID and SHA;
- exact audit ID and status;
- source document IDs and content hashes;
- output paths;
- authority manifest path and digest;
- request signature;
- limitations and unresolved issues; and
- the statement that preparation is not approval or application.

The user must confirm the exact request signature. A stale or changed request
invalidates confirmation and requires a new dialog.

### 14.3 Result

The GUI displays the returned transaction and EON action identities with:

```text
PREPARED_PENDING_EVIDENCE_AND_HUMAN_APPROVAL
```

It then offers navigation to the existing EON, evidence, governance, and
approval surfaces when running inside the main workbench. The standalone
application may show IDs and launch instructions but must not create a local
approval shortcut.

## 15. SAA and Novelty Boundary

The GUI may display:

- selected known reasoning patterns;
- reasoning-path scores;
- review-bound reasoning algorithm proposals;
- proposal status;
- exact human reviewer and approval references when present;
- EGCF qualification identity when present; and
- novelty status and comparison basis.

It may not:

- convert `PROPOSED` to `QUALIFIED`;
- register a proposal without the existing exact human approval requirement;
- retrieve a proposed algorithm as a qualified algorithm;
- collapse `KNOWN_COMBINATION`, `NEW_APPLICATION`, and
  `POTENTIAL_NOVELTY_REQUIRES_REVIEW` into a generic positive novelty badge; or
- describe an advisory novelty result as a certified discovery.

## 16. Security, Privacy, and Resource Limits

### 16.1 File safety

- Resolve all selected paths through the existing workspace boundary.
- Reject traversal, unsupported schemes, and output paths outside approved
  scope.
- Never execute HTML, PDF actions, embedded scripts, macros, or attachments.
- Treat symlink policy explicitly and test it.
- Use atomic persistence for GUI preferences and explicit diagnostic exports.

### 16.2 Untrusted content

- Render source text as inert text.
- Do not evaluate markup, terminal escapes, or source-provided commands.
- Bound displayed excerpts and diagnostic messages.
- Redact secret-like values from GUI job errors and exported diagnostics.
- Never let a source file set network, output, authority, or OCR policy.

### 16.3 Resource budgets

Define and enforce configurable bounds for:

```text
selected source count
total selected source bytes
individual source bytes
PDF page count
OCR page and time budget
projection result count
graph node and edge count
displayed source characters
diagnostic log characters
worker shutdown wait
```

Exceeding a bound fails closed with a clear diagnostic before unbounded UI or
worker allocation.

## 17. Accessibility and Interaction Requirements

1. Every primary action is reachable by keyboard.
2. Tab order follows Request, Sources, Workflow, Runs, Document, Graph,
   Evidence, and Audit.
3. Status is encoded by text and shape or icon, not color alone.
4. Graph nodes support keyboard selection through existing `GraphView`
   behavior.
5. Font scaling preserves pane usability.
6. Focus is returned predictably after dialogs and job completion.
7. Long text panels support search, copy, and screen-reader-compatible labels
   where Tk permits.
8. Motion is limited to bounded progress indication and may be disabled.
9. Error dialogs provide a short summary plus an inspectable bounded detail.
10. Human visual review covers contrast, scaling, focus, truncation, and
    high-density graph behavior.

## 18. Performance Targets

These are implementation targets, not certification until measured on a frozen
fixture and host:

```text
standalone window visible from warm Python start: <= 2 seconds
projection refresh for 100 result artifacts: <= 500 ms
graph projection for 500 nodes and 1,000 edges: <= 1 second off the Tk thread
selection response after data is loaded: <= 100 ms
bounded queue depth: <= 1,000 events
clean close after idle: <= 1 second
clean close after cancellation request: <= configured worker shutdown bound
```

Performance measurements must record host, Python, Tk, dependency, fixture,
source, and report hashes. Failing a target does not justify removing evidence
or weakening safety behavior.

## 19. Implementation Phases and Binary Gates

### Phase 0: Baseline Freeze and Requirement Registry

**Dependencies:** none.

**Work:**

1. Record current Git, dirty-state, relevant source, schema, test, and plan
   hashes.
2. Inventory every current formal-writing GUI import and caller.
3. Map this plan's `FWGUI-*` requirements to owners and tests.
4. Freeze representative result, source, graph, audit, plan, draft, malformed,
   and governed-write fixtures.
5. Record optional PDF/OCR availability separately from base behavior.

**Evidence:**

- baseline manifest;
- fixture manifest and hashes;
- import/caller inventory;
- initial requirement matrix; and
- dirty-worktree preservation record.

**Pass gate:**

```text
every planned change has a named owner, fixture, and requirement ID before implementation starts
```

### Phase 1: Standalone Application Scaffold

**Dependencies:** Phase 0.

**Work:**

1. Add `ourd_gui/formal_writing_gui.py`.
2. Implement parser, workspace validation, Tk root, startup errors, and clean
   close.
3. Embed the existing `FormalWritingView` without changing its core behavior.
4. Add `oiec-stm-formal-writing-gui` to `pyproject.toml`.
5. Preserve `oiec-stm-gui`, `ourd-gui`, and main-workbench behavior.

**Tests:**

- parser and alias tests;
- invalid workspace test;
- standalone construction test;
- clean shutdown test;
- entry-point packaging test; and
- existing shell integration test.

**Pass gate:**

```text
the standalone application launches and closes without adding a second engine, store, or mutation path
```

### Phase 2: Renderer-Neutral Request and Job Models

**Dependencies:** Phase 1.

**Work:**

1. Define immutable form state, source selection, execution options, job state,
   and GUI event records.
2. Validate profile, word target, network policy, OCR options, and constraints.
3. Convert form state to canonical compiler arguments.
4. Define deterministic signatures for GUI-only request drafts where useful,
   while clearly distinguishing them from canonical request signatures.
5. Add serialization only for non-sensitive preferences.

**Tests:**

- defaults;
- all profiles;
- repeated sources and rubrics;
- invalid combinations;
- deterministic form projection; and
- no authority or approval inference.

**Pass gate:**

```text
identical visible form state compiles to identical canonical request fields without hidden inputs
```

### Phase 3: Projection Hardening

**Dependencies:** Phases 0 and 2.

**Work:**

1. Replace unguarded JSON reads with bounded diagnostics.
2. Add typed plan, draft, audit, graph issue, novelty, and source projections.
3. Expose exact IDs and source hashes.
4. Add deterministic graph-node and graph-edge adaptation.
5. Handle unknown fields additively and reject incompatible schema versions.
6. Preserve sentence-to-claim offsets and section identity.
7. Add bounded pagination or result limits for large stores.

**Tests:**

- malformed JSON;
- disappearing file;
- unknown field;
- incompatible schema;
- stable ordering;
- duplicate IDs;
- sentence trace offsets;
- graph mapping; and
- source-page identity.

**Pass gate:**

```text
no malformed or stale artifact crashes the GUI or becomes a valid writing result by inference
```

### Phase 4: Asynchronous Controller and Lifecycle

**Dependencies:** Phases 2-3.

**Work:**

1. Add `FormalWritingController` with one worker.
2. Add bounded event polling through Tk `after()`.
3. Enforce one active job.
4. Add structured completion and failure events.
5. Add additive service progress and cancellation callbacks if required.
6. Implement orderly shutdown without Tk access from workers.
7. Preserve atomic artifact publication.

**Tests:**

- delayed service responsiveness;
- no widget access from worker;
- duplicate submission rejection;
- failure propagation;
- cancellation before and between phases;
- close during idle and active job; and
- no thread or store-lock leak.

**Pass gate:**

```text
long writing work never blocks the Tk event loop and shutdown leaves no active worker or canonical partial artifact
```

### Phase 5: Request, Source, and Rubric Workspace

**Dependencies:** Phases 2 and 4.

**Work:**

1. Add the request editor.
2. Add source and rubric collections with deterministic manifests.
3. Add file and folder selection through workspace validation.
4. Display supported-format and optional-dependency state.
5. Add source drift and ingestion status after execution.
6. Add explicit constraints and page/OCR policy controls.
7. Keep ordinary workspace content read-only.

**Tests:**

- path normalization;
- repeated and duplicate files;
- unsupported formats;
- folder ordering;
- symlinks and traversal;
- PDF dependency unavailable;
- OCR permission required; and
- no ordinary file write.

**Pass gate:**

```text
the complete visible input manifest is deterministic, policy-valid, and reviewable before execution
```

### Phase 6: Read-Only Workflow Execution

**Dependencies:** Phases 4-5.

**Work:**

1. Implement Inspect, Locate, Research, Argument, Plan, Draft, Audit, Explain,
   and Export References actions.
2. Compile every action through the canonical request compiler.
3. Execute every action through `FormalWritingService`.
4. Refresh the selected result only after persistence completes.
5. Add CLI/GUI equivalence fixtures.
6. Display canonical request and artifact IDs.

**Tests:**

- one test per action;
- exact GUI/CLI request equivalence;
- source-free plan fail-closed behavior;
- `--require-qualified` equivalent status behavior;
- repeated execution determinism; and
- artifact persistence identity.

**Pass gate:**

```text
the GUI and CLI produce the same canonical request and qualification result for equivalent inputs
```

### Phase 7: Persisted Plan, Draft, Audit, and Revision Flow

**Dependencies:** Phase 6.

**Work:**

1. Display plan and draft IDs as selectable objects.
2. Draft from an exact persisted plan ID.
3. Audit an exact persisted draft ID without regenerating it.
4. Revise from an exact persisted draft and bind the prior draft SHA.
5. Preserve run history and select the new revision without hiding its parent.
6. Expose missing persisted artifacts as fail-closed diagnostics.

**Tests:**

- plan-to-draft;
- draft-to-audit;
- draft-to-revision;
- prior SHA binding;
- unknown ID;
- missing draft artifact;
- source drift; and
- revision lineage display.

**Pass gate:**

```text
every plan, draft, audit, and revision transition binds the exact persisted predecessor identity
```

### Phase 8: Interactive Argument Graph

**Dependencies:** Phases 3 and 7.

**Work:**

1. Render the argument graph through `GraphView`.
2. Define stable layers, ordering, status labels, and subtitles.
3. Preserve all typed reasoning-edge relations.
4. Distinguish claims, counterclaims, evidence, and qualifications without
   relying on color.
5. Provide raw JSON as a secondary inspectable representation.
6. Cross-select graph nodes and document sentence traces.
7. Bound or virtualize very large graphs.

**Tests:**

- node/edge completeness;
- stable layout inputs;
- relation preservation;
- keyboard navigation;
- non-color labels;
- selection cross-linking;
- graph issue visibility; and
- large graph bounded behavior.

**Pass gate:**

```text
every canonical graph node and edge appears exactly once or is explicitly reported as unrenderable
```

### Phase 9: Evidence Reader and Source Traceability

**Dependencies:** Phases 5, 7, and 8.

**Work:**

1. Cross-select document sentence, claim, evidence link, reference span, and
   source page.
2. Display source hash, physical page, display label, extraction mode, and
   confidence.
3. Highlight exact text and bounded context.
4. Add safe optional PDF rendering and geometry overlays.
5. Display OCR and reflowable-source limitations.
6. Add copy-locator and inspect-reference actions without editing the source.

**Tests:**

- exact trace chain;
- repeated quotation disambiguation;
- page label versus physical page;
- reflowable locator behavior;
- stale source rejection;
- OCR warning;
- geometry fixture; and
- source containing prompt injection text.

**Pass gate:**

```text
a selected material sentence resolves to its exact source-bound evidence or displays an explicit missing-trace failure
```

### Phase 10: Audit, Diagnostics, and Repair Guidance

**Dependencies:** Phases 7-9.

**Work:**

1. Render all deterministic audit metrics.
2. Render graph issues, unsupported claims, limitations, and performed checks.
3. Cross-select audit findings to claims, graph nodes, and evidence.
4. Provide bounded repair guidance based only on stored issue codes and
   limitations.
5. Preserve exact statuses and novelty classifications.
6. Add export of a diagnostic report only after explicit path selection.

**Tests:**

- qualified document;
- missing counterargument;
- semantic drift;
- unsupported claim;
- missing citation trace;
- evidence insufficient;
- potential novelty review; and
- diagnostic export path policy.

**Pass gate:**

```text
every failed audit gate is visible, traceable, and unchanged from the canonical audit artifact
```

### Phase 11: Governed Write Preparation

**Dependencies:** Phases 7 and 10.

**Work:**

1. Add explicit output-path and authority-manifest selection.
2. Display exact request, source, draft, audit, authority, and output identities.
3. Require exact request-signature confirmation.
4. Detect drift between preview and preparation.
5. Reuse the existing governed transaction and EON preparation path.
6. Display prepared transaction and action IDs.
7. Navigate to main-workbench evidence/approval views when available.
8. Provide no standalone approval bypass.

**Tests:**

- missing output;
- missing authority;
- wrong signature;
- changed request after confirmation;
- changed source after confirmation;
- prepared status and IDs;
- no direct output write; and
- main-workbench navigation versus standalone limitation.

**Pass gate:**

```text
the GUI can prepare but cannot approve, apply, or certify a final document outside the canonical governed path
```

### Phase 12: SAA and Novelty Inspection

**Dependencies:** Phases 8, 10, and 11.

**Work:**

1. Display selected reasoning pattern and path scores.
2. Display reasoning algorithm proposal identity and status.
3. Display human review and EGCF qualification references when present.
4. Display novelty status and comparison basis.
5. Link qualified algorithms to the existing Algorithms view in embedded mode.
6. Keep proposal admission and qualification outside standalone GUI authority.

**Tests:**

- known pattern;
- proposed algorithm;
- proposed-not-qualified retrieval boundary;
- qualified algorithm identity;
- missing review;
- all novelty statuses; and
- no automatic novelty or qualification transition.

**Pass gate:**

```text
the GUI exposes SAA and novelty evidence without creating authority or upgrading status
```

### Phase 13: Accessibility, Resilience, and Security Hardening

**Dependencies:** Phases 1-12.

**Work:**

1. Complete keyboard navigation, focus behavior, non-color status encoding, and
   font scaling.
2. Add bounded lists, logs, excerpts, and graph rendering.
3. Add crash recovery for GUI-only preferences and selection state.
4. Test malformed and adversarial documents as inert data.
5. Add redaction for diagnostics and exported reports.
6. Validate close, cancellation, and interrupted persistence behavior.
7. Document optional dependency and platform limitations.

**Tests:**

- keyboard-only acceptance path;
- focus restoration;
- high-DPI/font scaling;
- color-independent status;
- malformed source and artifact;
- oversized fixture;
- prompt injection;
- secret-like content;
- interrupted worker; and
- projection rebuild after crash.

**Pass gate:**

```text
untrusted content cannot alter authority or execution, and the complete primary workflow is keyboard operable
```

### Phase 14: Deterministic Qualification and Benchmarks

**Dependencies:** Phases 0-13.

**Work:**

1. Run focused projection, controller, CLI equivalence, engine, and GUI tests.
2. Run full test discovery from the current source.
3. Run the formal-writing benchmark and bind its report hash.
4. Measure startup, refresh, graph, selection, and shutdown targets.
5. Run clean base installation and optional PDF/OCR installation tests.
6. Run headless/Xvfb GUI smoke tests where available.
7. Perform bounded human visual review on the exact candidate.
8. Record source, fixture, dependency, test, benchmark, screenshot, and report
   hashes.

**Minimum deterministic gates:**

```text
GUI/CLI request equivalence: 100%
canonical graph node and edge coverage: 100%
sentence-to-claim trace fixture coverage: 100%
stale-source rejection: 100%
unauthorized ordinary-file mutation count: 0
automatic approval or SAA qualification count: 0
malformed artifact accepted as valid: 0
full deterministic test failures: 0
formal-writing benchmark failures: 0
```

**Pass gate:**

```text
all frozen deterministic gates pass on one exact source snapshot and human visual review records no unresolved release blocker
```

### Phase 15: Documentation, Packaging, and Release Audit

**Dependencies:** Phase 14.

**Work:**

1. Document standalone and embedded launch paths.
2. Document request fields, actions, statuses, persistence, OCR, and page limits.
3. Document governed write preparation and approval separation.
4. Update GUI architecture, safety, testing, and formal-writing documentation.
5. Add packaging and entry-point checks.
6. Build wheel and sdist from the frozen source snapshot.
7. Validate installation and launch from the built wheel.
8. Produce a requirement-to-evidence completion audit.
9. Prove rollback to the prior compatible GUI and writing behavior.
10. Obtain exact-hash human release approval if release is requested.

**Pass gate:**

```text
every FWGUI requirement has current exact-snapshot evidence, packaging is reproducible, rollback is proven, and any release approval binds the exact candidate
```

## 20. Requirement-to-Evidence Matrix

| ID | Requirement | Primary phase | Required evidence |
| --- | --- | --- | --- |
| FWGUI-001 | Add standalone `ourd_gui/formal_writing_gui.py` | 1 | parser, launch, close, and packaging tests |
| FWGUI-002 | Preserve embedded main-workbench use | 1 | shell integration and compatibility tests |
| FWGUI-003 | Keep one formal-writing semantic owner | 0-6 | import audit and GUI/CLI equivalence |
| FWGUI-004 | Typed deterministic request form | 2 and 5 | form-to-request tests |
| FWGUI-005 | Robust read-only artifact projection | 3 | malformed, stale, and schema tests |
| FWGUI-006 | Non-blocking Tk execution | 4 | delayed-worker and thread-isolation tests |
| FWGUI-007 | Truthful progress and cancellation | 4 | phase and cancellation evidence |
| FWGUI-008 | Deterministic source/rubric manifest | 5 | path, ordering, and policy tests |
| FWGUI-009 | Complete read-only workflow actions | 6 | one operation test per action |
| FWGUI-010 | Exact persisted plan/draft/revision identity | 7 | lineage and prior-hash tests |
| FWGUI-011 | Interactive complete argument graph | 8 | node/edge coverage and selection tests |
| FWGUI-012 | Sentence-to-source evidence trace | 9 | exact trace and page fixtures |
| FWGUI-013 | Complete canonical audit presentation | 10 | metric/status/issue coverage tests |
| FWGUI-014 | No audit or novelty laundering | 10 and 12 | negative status tests |
| FWGUI-015 | Governed output preparation only | 11 | signature, authority, and no-write tests |
| FWGUI-016 | No GUI approval or SAA qualification | 11-12 | prohibited-transition tests |
| FWGUI-017 | Untrusted-source isolation | 13 | adversarial source tests |
| FWGUI-018 | Keyboard and non-color accessibility | 13 | automated and human review evidence |
| FWGUI-019 | Bounded performance and lifecycle | 4, 13, and 14 | measurements and shutdown tests |
| FWGUI-020 | Exact-snapshot qualification and rollback | 14-15 | validation bundle, hashes, and rollback proof |

## 21. Test Matrix

### 21.1 Pure deterministic tests

Run without a display, provider, network, PDF, or OCR dependency:

- parser and entry-point configuration;
- form and job models;
- request compilation;
- CLI/GUI equivalence;
- artifact projection;
- graph adaptation;
- audit metrics;
- source/path policy;
- persisted ID resolution;
- controller events with a fake service;
- governed write confirmation data; and
- SAA/novelty status projection.

### 21.2 Tk smoke tests

Run under an available display or Xvfb:

- application construction;
- initial focus and tab order;
- control enable/disable states;
- worker polling;
- run selection;
- graph selection;
- sentence highlighting;
- evidence navigation;
- error dialog behavior; and
- clean close.

Skipping display-dependent tests must be explicit and cannot establish GUI
qualification by itself.

### 21.3 Integration tests

- real `FormalWritingService` with temporary workspaces;
- source ingestion and persisted artifacts;
- plan-to-draft-to-audit-to-revision;
- exact source and prior-draft hashes;
- qualification failure modes;
- malformed persisted artifacts;
- optional PDF/OCR capability detection;
- governed transaction preparation; and
- main-workbench cross-navigation.

### 21.4 Human review

Use one frozen candidate and fixture bundle to review:

- 100%, 125%, 150%, and 200% scaling;
- narrow and wide window layouts;
- keyboard-only workflow;
- screen-reader labels where supported;
- non-color statuses;
- long tasks, paths, citations, and issue messages;
- high-density graphs;
- PDF page and evidence highlighting;
- warning and confirmation clarity; and
- visual distinction between candidate, qualified, proposed, prepared,
  approved, and applied states.

## 22. Acceptance Scenario

The primary end-to-end acceptance scenario is:

1. Launch `oiec-stm-formal-writing-gui --workspace <fixture>`.
2. Add two source documents and one rubric.
3. Enter a scientific or argumentative writing task.
4. Run Research and inspect the source/evidence map.
5. Run Argument and inspect every graph node and edge.
6. Run Plan and record the exact plan ID.
7. Draft from that persisted plan.
8. Select a material sentence and navigate to its claim, reasoning relation,
   evidence span, exact source hash, and page/section locator.
9. Audit the exact persisted draft.
10. Observe either `QUALIFIED_FORMAL_DOCUMENT`, `REVISION_REQUIRED`, or
    `EVIDENCE_INSUFFICIENT` without status alteration.
11. If revision is required, revise from the exact draft ID and verify prior SHA
    lineage.
12. Select an output and authority manifest.
13. Review and confirm the exact request signature.
14. Prepare a governed write transaction.
15. Observe transaction and EON action IDs with pending evidence/human approval.
16. Verify that no final ordinary workspace file was written by the GUI.
17. Close the application and confirm all workers and locks are released.

The scenario passes only if every displayed canonical object can be traced to
its exact persisted identity and the GUI creates no independent authority.

## 23. Risk Register

| Risk | Mitigation |
| --- | --- |
| `formal_writing_gui.py` becomes a monolith | Keep it as parser/application composition; move execution and projection to existing owners |
| GUI duplicates CLI or compiler logic | Direct compiler/service use plus cross-surface equivalence tests |
| Tk freezes during extraction or drafting | One worker, bounded queue, main-thread-only widgets |
| Cancellation claim is false | Cooperative checkpoints or explicit `Stop After Current Phase` wording |
| Raw JSON artifacts crash startup | Diagnostic projections and bounded parsing failures |
| Graph drops relations | Exact node/edge coverage gate and raw JSON fallback |
| Selection maps to wrong repeated text | Canonical section offsets, claim IDs, and exact source anchors |
| GUI silently edits final document | Read-only document widget and governed write-only output path |
| Approval becomes a button bypass | Prepare-only standalone behavior and exact-signature confirmation |
| Proposed SAA algorithm appears qualified | Preserve exact status and require EGCF qualification identity |
| Novelty badge overstates evidence | Render full novelty enum and review requirement |
| Large artifact stores exhaust UI | Paging, bounds, lazy projection, and performance gates |
| Source content injects instructions | Inert rendering, no source-driven policy, adversarial tests |
| Preferences leak sensitive text | Allowlisted GUI-only fields and no document bodies |
| Existing dirty work is overwritten | Minimal patches, no cleanup, targeted status checks, no broad staging |
| Focused tests are mistaken for release readiness | Full discovery, packaging, benchmark, human review, audit, and exact approval |

## 24. Documentation Deliverables

Implementation should update or add:

- `README.md` standalone formal-writing GUI quick start;
- `docs/OURD_AGENT_GUI.md` embedded/standalone relationship;
- `docs/GUI_ARCHITECTURE.md` formal-writing application/controller/view path;
- `docs/GUI_SAFETY.md` read-only and governed-output boundary;
- `docs/GUI_TESTING.md` headless, Xvfb, integration, and human review workflow;
- `docs/FORMAL_WRITING_RESEARCH.md` GUI traceability and interaction limits;
- `docs/FORMAL_WRITING_ENGINE_IMPLEMENTATION_AUDIT.md` only after current-source
  evidence exists; and
- generated documentation only after source and Markdown freeze.

Documentation must distinguish:

```text
implemented
deterministically validated
human reviewed
prepared for approval
approved
certified
released
```

## 25. Release States

```text
DESIGNED
  -> STANDALONE_SCAFFOLDED
  -> REQUEST_COMPILED
  -> ASYNC_EXECUTION_COMPLETE
  -> TRACEABLE_WORKBENCH
  -> GOVERNED_WRITE_PREPARATION_COMPLETE
  -> FEATURE_COMPLETE_CANDIDATE
  -> DETERMINISTICALLY_VALIDATED
  -> HUMAN_VISUAL_REVIEWED
  -> HUMAN_APPROVAL_REQUIRED
  -> CERTIFIED
  -> RELEASED
```

No state implies the next. In particular:

- a launchable application is not feature complete;
- feature complete is not deterministically validated;
- deterministic validation is not human visual review;
- visual review is not authority approval;
- approval of one transaction is not release certification; and
- a release claim requires exact source and artifact identity.

## 26. Required Implementation Order

```text
1. Freeze baseline, fixtures, and FWGUI requirements
2. Add thin standalone application and entry point
3. Add immutable request/job models
4. Harden artifact projections
5. Add asynchronous controller and truthful lifecycle
6. Add request, source, rubric, and policy controls
7. Add read-only workflow execution and CLI equivalence
8. Add persisted plan/draft/audit/revision navigation
9. Add complete interactive argument graph
10. Add exact document-to-evidence navigation
11. Add audit and diagnostic cross-linking
12. Add governed write preparation
13. Add SAA and novelty inspection
14. Harden accessibility, security, resilience, and performance
15. Run full qualification, packaging, documentation, rollback, and audit
```

This order keeps the implementation centered on the system's distinguishing
requirement: a source-grounded, traceable, evidence-governed writing workbench,
not merely a desktop wrapper around the formal-writing CLI.
