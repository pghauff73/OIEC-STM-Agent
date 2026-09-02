# OIEC-STM-Agent GUI

**Implementation date:** 2026-08-21  
**Updated:** 2026-08-30
**State:** governed candidate; deterministic validation and exact-snapshot human approval required

## Purpose

`oiec-stm-gui` is an inspectable workbench over the existing EGCF core. It exposes
the chain from intent to qualified algorithm, evidence, approval, execution,
verification, rollback, and learning. It is not a second policy engine and does
not provide a direct filesystem or shell bypass.

```text
User
  -> Tk view
  -> GuiController
  -> CoreGateway
  -> OURDAgent or EGCFEngine
  -> capability / selection / evidence / approval / EON / tools
  -> content-addressed records and append-only events
  -> read-only GUI projections
```

## Launch

```bash
python3 -m ourd_gui --repo .
```

Installed entry point:

```bash
oiec-stm-gui --repo .
```

`ourd-gui` remains an equivalent compatibility alias.

Agent Chat provider flags:

```text
--model MODEL
--provider llama_cpp_process
--runner-path PATH
--model-path PATH
--expected-model-sha256 digest
--llama-cpp-root PATH
--llama-cpp-build-dir PATH
--llama-grammar-dir PATH
--llama-context TOKENS
--reasoning-effort {none,low,medium,high,xhigh}
--max-output-tokens TOKENS
--context-budget TOKENS
--timeout-seconds SECONDS
--transport-retries COUNT
--max-steps COUNT
```

These flags configure both the Model panel and Agent Chat. Each chat turn runs
provider preflight before inference. The GUI never installs or silently
substitutes a model, and provider readiness grants no repository authority.

Invoking the exact case-sensitive `oiec-stm-sr-AgentICPI --repo .` product
entry point with no explicit provider configuration automatically selects the
direct Qwen profile: `qwen3.8:27B-Fast` maps to `qwen3.8-27b-direct` under the
`llama_cpp_process` provider. Runner, GGUF, digest, llama.cpp source, build, and
grammar evidence are verified by provider preflight, not by a model service.
Missing configured paths fail closed and are never downloaded automatically.
`--no-auto-qwen` disables this behavior; `--auto-qwen` enables it for
compatibility or source-tree launch commands.

## Implemented Views

### Agent Chat

- Provides a multiline composer with Enter-to-send and Shift+Enter for a
  newline; `Ctrl+L` focuses the chat tab.
- Executes one governed `OURDAgent` turn on the existing single GUI worker so
  Tk remains responsive and only one core operation owns the workspace lock.
- Sends a bounded sequence of prior user and assistant messages to the model.
  `New Chat` preserves the append-only transcript but excludes earlier messages
  from subsequent model context.
- Projects provider preflight, model steps, tool requests, tool results, and the
  final response into a bounded Agent Activity view linked to the core trace
  hashes.
- `Stop` is cooperative: it prevents subsequent steps and tool dispatch after
  the blocking provider call returns. Token-level streaming and transport-level
  interruption are not claimed.
- Model output may request existing agent tools, but cannot bypass capability,
  evidence, approval, transaction, or rollback rules.
- Converts explicit workspace references into content-addressed, snapshot-bound
  context envelopes before model invocation. The Context tab shows bounded file
  metadata, exact hash state, unresolved references, and truncation without
  granting authority.
- Redacts context preview bodies until the person explicitly reveals the
  already bounded in-memory preview. GUI route events retain envelope identity
  and counts only; core `run_started` events retain task hashes and size metrics
  rather than the structured task body.
- Builds the complete context envelope before any confirmation-required turn,
  then records an accepted or rejected deterministic receipt bound to the exact
  route, snapshot, envelope, budget, model-input digest, counts, and pinned
  draft. Accepted receipts are checked before task creation and again at the
  worker boundary; rejected or stale receipts start no provider turn.
- `/attach` validates and pins up to 32 workspace paths, then constructs the
  complete draft envelope without invoking the model or mutating files.
  `/detach` removes selected pins or all pins; `New Chat` clears the set.
- `/context` compares the pinned draft with the current exact snapshot and shows
  a deterministic file delta. `/context --refresh` explicitly installs the new
  in-memory draft; stale pinned drafts block model invocation until refreshed.
- Displays pinned count and signature in live route preview and Context details,
  records append-only transition/delta metadata, and rejects a model turn if its
  exact envelope omits a pin or differs from the pinned draft snapshot.
- Compiles an exact turn policy before dispatch. Read-only summaries receive
  only repository/corpus read tools; super reasoning remains hidden until its
  separate governance prerequisites are satisfied.
- Shortens Agent Activity to high-value state transitions, selected bounded
  arguments, structured error codes, aggregated corpus progress, and formal
  writing completion. Full append-only trace and persisted evidence remain
  available for detailed inspection and replay.

### Formal Writing

- Uses the same reusable `FormalWritingView` in the main workbench and the
  standalone `oiec-stm-formal-writing-gui` application.
- Provides typed Request, Inputs, Workflow, Writing Runs, Document, Argument
  Graph, Evidence, Audit, SAA proposal, and novelty surfaces backed by signed
  `.ourd-agent/writing/` artifacts.
- Runs the canonical `FormalWritingService` on one dedicated worker through
  `FormalWritingController`; Tk widgets remain on the main thread and receive
  bounded immutable progress events at 50 ms polling intervals.
- Supports Research, Argument, Plan, Draft, Audit, Revise, Inspect Sources,
  Locate Passage, Explain Reference, and Export References. A persisted plan,
  draft, audit, or request is selected by exact canonical ID.
- Displays deterministic input manifests, source hashes, physical page indexes,
  display labels, extraction/OCR state, freshness, sentence-to-claim traces,
  complete typed graph relations, all audit metrics, limitations, performed
  checks, exact novelty enums, and review-bound algorithm proposal status.
- Safely renders optional PDF pages only when PyMuPDF is installed. OCR controls
  are disabled unless PyMuPDF, Pillow, and `pytesseract` are all available;
  OCR also requires explicit permission.
- Keeps the document selection-only. No view can edit canonical writing
  artifacts or ordinary workspace output files.
- `Prepare Governed Write` binds the exact request signature, draft SHA, audit,
  sources, authority digest, and output paths, then prepares the shared
  transaction/EON candidate. The embedded workbench navigates to Governance;
  approval, evidence acceptance, apply, verification, and rollback remain
  separate authoritative surfaces.

### Selection Trace

- Resolves exact command, invocation, selection, algorithm digest,
  qualification, and evidence object IDs.
- Displays candidates, exclusions, score components, ranking, winner, and
  tie-break.
- Provides Explain, Compare, Show Rejections, Show Evidence, Open
  Qualification, Open Command, and Copy ID operations.
- Reports stale snapshots and unresolved references rather than omitting them.

### Workflow and EON

- Renders the compiled DAG from canonical nodes and edges.
- Shows capability, risk, scope, evidence, preconditions, postconditions,
  invariants, budget, rollback graph, and source snapshot.
- Enables execution only for a current non-dry-run plan and, when required, an
  exact non-expired matching human approval.
- Approval and execution remain separate user actions.

### Evidence and Governance

- Resolves evidence through selection, qualification, confidence, assurance,
  and plan references.
- Displays `C_I`, `C_D`, `C_B`, `C_T`, `C_M`, and `C_R` coverage where the core
  provides requirements or artifacts.
- Displays evidence classes, conflicts, blocking gaps, and known unknowns.
- Exports non-authoritative JSON and Markdown evidence views preserving IDs,
  hashes, limitations, and source snapshots.
- Derives the C0-C5 ladder from active `CapabilityGrant` and `CapabilitySpec`
  records; the GUI cannot create a grant.

### OURD and IURM

- Renders canonical `nodes` and `edges` returned by OURD commands.
- Uses labelled `GUI_REFERENCES` links only when no canonical domain graph was
  returned.
- Renders IURM dimensions, baseline, values, interactions, and MVD only from
  core-returned semantic outputs.
- Buttons prepare semantic commands; they do not independently infer coverage.

### CFEL, Replay, and Comparison

- Shows failure records, rollback records, root-cause hypotheses, active and
  frozen dimensions, retries, and evidence.
- `Create Regression Test` prepares a semantic verification command and never
  writes a test file directly.
- GUI replay reconstructs projection state through an event cursor and never
  invokes the core.
- Governed plan replay is an explicit dry-run request through
  `EGCFEngine.replay`.
- Run comparison reports algorithm, evidence, file, failure, approval,
  artifact, status, and usage differences.

### Artifacts and Assurance

- Text, JSON, Markdown, logs, HTML, and SVG are displayed as passive text.
- PNG and GIF use Tk's passive native image loader.
- OBJ, STL, and PLY use bounded metadata parsers for counts and bounding boxes;
  original files are never modified.
- Assurance records export to `.ourd-agent/gui/exports/` as JSON, Markdown, or
  static escaped HTML. Exports are views, not canonical evidence.

### Semantic Terminal

The terminal accepts only:

```text
<namespace> <verb> [one JSON object]
<namespace>.<verb>[@version] [one JSON object]
```

The command must resolve to a checked-in `CommandDefinition`. Shell
metacharacters are rejected. C0/C1 commands may run through the qualified
semantic adapter; C2 is forced through simulation; C3-C5 remain compile-only
until the normal EON and approval path authorizes them.

## Persistence

```text
.ourd-agent/
├── egcf/                         canonical core state
└── gui/
    ├── events.jsonl              append-only GUI event stream
    ├── projection.sqlite3        rebuildable task/session/chat projection
    ├── preferences.json          non-authoritative layout/accessibility state
    └── exports/                  non-authoritative assurance views
```

Chat messages and turn state are reconstructed from the append-only GUI event
journal. The in-memory and SQLite projections retain at most 500 chat messages;
the journal remains the replay source.

Preferences include window geometry, selected tabs, pane positions, recent
repositories, the last open file, selected filters, font scaling, and reduced
motion. They contain no secrets or approval authority.

Task rows load incrementally in pages of 500. Immutable object hydration uses a
bounded LRU cache, and the Performance panel exposes bounded timing telemetry.
Detail and export projections redact secret-like fields and bound deeply nested
or oversized data.

Detailed contracts:

- `docs/GUI_ARCHITECTURE.md`
- `docs/GUI_EVENT_SCHEMA.md`
- `docs/GUI_SELECTION_TRACE.md`
- `docs/GUI_SAFETY.md`
- `docs/GUI_TESTING.md`
- `docs/GUI_STATE_MIGRATIONS.md`

## Qwen From VisualGrammar2d

`../VisualGrammar2d/qwen_cli.py` may be used only as an external bounded
drafting helper. It must remain outside the authority path:

```text
Qwen proposal
  -> human/core review
  -> deterministic evidence
  -> exact plan approval
  -> governed execution
```

The currently supported Agent Chat profile is the direct
`qwen3.8-27b-direct` GGUF path. Do not silently substitute a different requested
model; bind exact model identity and provenance before using any generated text
as a proposal.

## Validation

Focused GUI tests:

```bash
python3 -m unittest discover -s tests/gui -t . -v
```

Headless smoke test:

```bash
tmpdir=$(mktemp -d)
printf 'fixture\n' > "$tmpdir/README.md"
xvfb-run -a python3 -m ourd_gui --repo "$tmpdir" --smoke-test
```

Build verification:

```bash
python3 -m build --wheel --sdist
```

See `docs/OURD_AGENT_GUI_COMPLETION_AUDIT.md` for the phase-by-phase
requirements mapping and explicit release boundary.

## Compatibility

- Python 3.10 or newer.
- Tk 8.6-compatible runtime for the desktop workbench.
- Linux headless smoke accepts `xvfb-run`; the deterministic validator uses an
  authenticated TCP Xvfb transport when Unix display sockets are unavailable.
- No mandatory third-party GUI or graph dependency.
- PNG/GIF support uses Tk; JPEG decoding depends on the host Tk build.
- The custom PEP 517 backend packages the GUI without setuptools.

## Current Limits

- Tkinter remains the current toolkit; a Qt migration is deferred until the
  interaction contract stabilizes.
- Image support is intentionally passive and bounded; JPEG may be metadata-only
  when the Tk build lacks a decoder.
- GLTF/GLB and interactive OpenGL geometry are deferred.
- The semantic terminal is not an unrestricted PTY.
- Agent Chat uses complete-response turns; token streaming is deferred.
- Stop is cooperative around blocking provider transport and cannot abort an
  already in-flight HTTP request.
- Performance targets are instrumented but remain host-dependent diagnostics.
- This source state is not certified merely because tests pass.
