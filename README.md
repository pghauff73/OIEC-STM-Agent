# OIEC-STM-Agent

A compact Python coding agent with a deterministic bounded-transition,
governance, and transaction boundary:

**HRTv1 → OURD → IURMv1.1.1 → EONv1 → Evidence Gate → Action → CFEL feedback**

When a task benefits from explicit hypothesis comparison, the optional
super-reasoning path is:

**HRTv1 → OURD → OIEC boundary/dimension projection → OIEC-SR → IURMv1.1.1 → EONv1 → Evidence Gate → Action → CFEL feedback**

The model may inspect, reason, propose, generate candidate patches, and analyze
failures. It cannot grant itself mutation authority, lower deterministic risk,
approve its own unsupported evidence, write internal evidence, or certify a
release.

The dependency-ordered program for integrating and completing every accepted
implementation is `COMPLETE_IMPLEMENTATION_STRATEGY.md`. It covers current
source recovery, upstream integration, OIEC-SR completion, direct llama.cpp
Qwen3.8 support, documentation regeneration, qualification, exact-hash approval,
merge, and release.

## What Is Enforced

- Workspace mutation authority comes from a human-authored, exact-snapshot
  authority manifest.
- The model may establish only governance scope that is equal to or narrower
  than the authority manifest.
- File writes are staged as immutable candidate transactions before an EON
  action is created.
- EON action IDs bind the authority hash, source snapshot, exact targets,
  candidate hash, canonical command argv, capability IDs, tests, invariants,
  risk, expiry, initial use count, and use limit.
- File mutations have a deterministic minimum risk of L1. Broad or structural
  changes have a deterministic minimum risk of L2.
- L1 and L2 actions require grounded evidence artifact IDs. L2 additionally
  requires counterexample evidence.
- Full approval cannot contain uncovered evidence. Limited approval has
  machine-enforced target, exact-command, capability, and use-count limits.
- Paths are canonicalized before authority, OURD, or EON matching. Traversal,
  symlink escape, absolute paths, and access to `.ourd-agent/` are blocked.
- Commands use `subprocess.run(argv)`, `shell=False`, a sanitized environment,
  and exact command capabilities. Executable-name allowlists are not used.
- L2 application displays the exact action ID, transaction ID, candidate hash,
  and diff for human approval unless the authority manifest explicitly permits
  `--yolo`.
- Multi-file transactions apply atomically where possible and automatically
  restore already-written files if a later write fails.
- Applied transactions retain original bytes, modes, and hashes for tested
  rollback.
- State is restored across processes. Events are append-only and SHA-256 chained;
  `state.json` is a rebuildable projection.
- A workspace lock enforces one writer. Prepared or applied transactions are
  detected on restart and block unrelated mutation until finalized, discarded,
  or rolled back.
- Significant failures create CFEL collision records. An unchanged failed tool
  call is blocked rather than blindly repeated. Revised-evidence retries are
  bounded by the authority manifest, and L2 automatic retries are disabled.
- Sensitive key assignments, bearer tokens, configured secret patterns, and
  matching secret environment values are redacted from event evidence.

Internal `.ourd-agent/` bookkeeping is created independently of workspace
mutation governance. Model tools cannot read or write that namespace.

## OIEC-STMv1.2 Bounded Transitions

OIEC-STMv1.2 adds a deterministic, fixed-point control projection without
creating another authority, evidence, or execution engine. Its six primitives
are `BoundaryState`, `DimensionBudget`, `FiniteEvidenceState`, `AttemptKey`,
`ProgressCertificate`, and `BoundedTransitionKernel`.

The kernel composes with existing owners:

- `BoundaryState` requires every concrete target to satisfy both the human
  authority patterns and the established governance patterns.
- `DimensionBudget` selects a finite, deterministic experimental basis and
  defaults to one varied dimension at a time.
- `FiniteEvidenceState` projects only action-relevant evidence atoms while the
  durable evidence registry remains append-only.
- `AttemptKey` binds the exact current snapshot, EON action, relevant evidence,
  boundary, and dimension state before execution.
- CFEL records significant failures against that pre-action key, so unrelated
  evidence or changed prose cannot unlock blind repetition.
- `ProgressCertificate` accepts continuation only for new evidence, material
  goal or risk improvement, boundary resolution, a discriminating experiment,
  or a terminal stop.

`BoundedTransitionKernel.prepare()` runs immediately before the existing
transaction apply and governed command paths. It can block or prepare, but it
has no subprocess or repository-write method. EON, the evidence gate,
`PolicyEngine`, `TransactionManager`, and human approval remain authoritative.

All OIEC control quantities use integer basis points from `0` to `10000`.
These values are deterministic telemetry and cannot lower the existing L0/L1/L2
risk floor.

## OIEC-SR v1.0 Super Reasoning

OIEC-SR is an additive, bounded reasoning layer. It does not replace OURD,
IURM, EON, CFEL, the evidence registry, or the mutation executor. It converts a
governed `ReasoningProblem` and explicit `Hypothesis` pool into independently
proposed, verified, and falsified candidate paths, then emits a deterministic
`ReasoningCertificate`.

The canonical records are `ReasoningProblem`, `Hypothesis`, `HypothesisSet`,
`HypothesisUpdateRecord`, `ReasoningNode`, `ReasoningEdge`,
`ReasoningTopology`, `ReasoningStep`, `ReasoningPath`, `VerifierReport`,
`FalsifierReport`, `CandidateSet`, `ReasoningMetrics`, `ReasoningCertificate`,
and `ReasoningBudget`. `SuperReasoningKernel` owns the pure orchestration.

The default search uses four independent perspectives: causal/mechanistic,
counterexample-first, formal derivation, and evidence synthesis. Candidate
count is adapted to recorded uncertainty, difficulty, and disagreement but is
always capped by OIEC dimensions and the provider's
`max_reasoning_samples`. Each candidate receives a step-level verifier report;
the top two verifier-ranked candidates receive separate falsifier reports.
Selection then uses fixed-point scores and lexical path IDs as the final
tie-break.

Only structured artifacts are requested from providers: claims, premises,
declared evidence IDs, checks, assumptions, counterexamples, and conclusions.
The system neither requests nor persists hidden chain-of-thought. Provider
self-confidence cannot override verifier, falsifier, evidence, topology, or
budget results.

`ReasoningTopology` schema v2 makes each inference edge content-addressed and
assigns it an explicit deductive, inductive, abductive, causal, analogical,
probabilistic, authority, defeasible, constraint, or computational mode.
Evidence nodes must belong to the declared finite evidence universe. Material
conclusions must trace through positive acyclic edges to evidence, an
observation, a validated problem premise, or an explicit assumption;
assumption-only conclusions remain hypothetical. Contradiction, falsification,
undercut, and rebuttal edges never count as positive support, and disconnected
reasoning branches fail closed.

`OURDAgent.run_super_reasoning()` requires established governance, the exact
current source snapshot, declared evidence IDs, and no pending EON action. It
persists the bounded problem, hypotheses, candidate set, topology, and
certificate in RuntimeState schema v4. `HypothesisSet` is the signed immutable
owner; `hypothesis_pool` remains a derived compatibility projection. Every
fixed-point evidence or CFEL belief change is bound to an immutable
`HypothesisUpdateRecord`. A current accepted certificate may be
bound into a later EON action; stale, tampered, unresolved, or no-value
certificates fail closed. Existing callers that do not start a reasoning
episode continue through the baseline path unchanged.

CFEL collisions can weaken or falsify matching hypotheses without deleting
previous support evidence. Collision identities and belief updates are
content-addressed so identical projected inputs replay identically. Repeating
different wording without measurable evidence, uncertainty, contradiction, or
confidence improvement produces `STOP_NO_VALUE`, not a new permission to act.

## Install

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

The local model transport is the direct `llama_cpp_process` provider. It uses a
bounded JSONL subprocess protocol with the checked-in `oiec-llama-runner`; no
remote provider SDK is required.

The canonical commands are `oiec-stm-agent` and
`oiec-stm-sr-agent-icpi`. The exact-name `oiec-stm-sr-AgentICPI` command is
installed as a compatibility alias for the product name. The historical
`oiec-stm-gui`, `ourd-agent`, `ourd-gui`, and `python ourd_agent.py` launch
paths remain supported compatibility aliases. The `ourd` Python package, `OURD_*`
environment variables, and `.ourd-agent/` state directory remain stable public
interfaces because OURD is still the semantic problem-model layer inside
OIEC-STM-Agent.

## Read-Only Use

Without `--authority`, the agent is deliberately read-only:

```bash
oiec-stm-agent /path/to/repo \
  --task "Inspect the parser and report the likely regression. Do not modify files."
```

Read-only runs may create `.ourd-agent/` evidence and state inside the target
workspace, but cannot mutate ordinary workspace files.

## Formal Writing and Corpus Summaries

The source-grounded writing engine is available through a dedicated command:

```bash
oiec-stm-formal-write locate \
  --workspace . \
  --source research/paper.md \
  --task "Locate the definition of epistemic uncertainty."

oiec-stm-formal-write draft \
  --workspace . \
  --source research/paper-a.md \
  --source research/paper-b.md \
  --profile scientific-essay \
  --citation-style apa-7 \
  --task "Evaluate the evidence for the proposed mechanism."
```

Supported command groups are `inspect`, `locate`, `explain-reference`,
`source-map`, `argument-map`, `outline`, `draft`, `revise`, `validate`,
`write`, and `references`. Reflowable Markdown, text, RST, HTML, CSV, JSON,
and YAML sources receive exact line/section locators. PDF and OCR support are
optional extras and fail closed when their dependencies or explicit OCR
permission are absent.

The canonical agent command also exposes the governed reasoning pipeline:

```bash
oiec-stm-agent write plan \
  --task "Evaluate whether AI is beneficial for small businesses" \
  --profile argumentative-essay

oiec-stm-agent write draft \
  --workspace . \
  --source research/paper.md \
  --task "Evaluate whether AI is beneficial for small businesses" \
  --words 1800

oiec-stm-agent write audit \
  --draft <draft-id> \
  --why \
  --require-qualified
```

The pipeline persists signed `WritingTask`, `ConceptDefinition`, `Claim`,
`EvidenceLink`, `ReasoningEdge`, `ArgumentGraph`, `DocumentPlan`,
`ParagraphPlan`, `DraftSection`, `WritingAudit`, novelty, falsification, and
review-bound SAA algorithm-proposal artifacts. Prose is compiled from the
selected graph under `NoNewMaterialClaims`; unsupported, disconnected,
semantically drifting, over-strong, or citation-untraceable claims fail closed.

Profiles now include `scientific-essay`, `argumentative-essay`,
`engineering-report`, `literature-review`, `business-analysis`,
`research-proposal`, and `lab-report`. The deterministic OIEC-Bench track is
available with `python3 tools/run_formal_writing_benchmark.py`.

The same engine is available through a standalone Tk workbench without opening
the complete AgentICPI GUI:

```bash
oiec-stm-formal-writing-gui --workspace /path/to/workspace
python3 -m ourd_gui.formal_writing_gui --repo /path/to/workspace
```

Optional startup fields include `--task`, `--profile`, repeatable `--source`
and `--rubric`, `--network-policy`, `--require-page-accuracy`, `--allow-ocr`,
`--ocr-language`, `--authority`, and `--open-result`. Startup is observational:
it initializes the visible form and selected persisted identity but does not
automatically run a job. The reusable workbench supports Research, Argument,
Plan, Draft, Audit, Revise, Inspect Sources, Locate Passage, Explain Reference,
and Export References through the canonical compiler and service.

The document is selection-only. Graph, evidence, audit, SAA proposal, and
novelty panels preserve exact signed IDs and statuses. `Prepare Governed Write`
requires a selected persisted draft and audit, explicit output and authority
paths, and exact request-signature confirmation. It prepares a transaction and
EON action with `PREPARED_PENDING_EVIDENCE_AND_HUMAN_APPROVAL`; it cannot
approve, apply, certify, or release the document.

`write` never silently edits the workspace. It requires an exact-snapshot
authority manifest and the exact signed request confirmation, then prepares a
transaction and EON action for evidence and human approval. The existing
`oiec-stm-agent --write` command accepts `--source`, `--rubric`, `--draft`,
`--citation-style`, `--word-target`, and page/OCR policy flags and compiles the
same `FormalWritingRequest` as the dedicated command.

Natural-language ICPI references include `@source[...]`,
`@sourcefolder[...]`, `@rubric[...]`, `@draft[...]`, `@output[...]`, and
`@style[...]`. British and US summary requests such as
`Summarise each /docs/ markdown file.` and `Summarize @folder[docs]` compile to
a read-only corpus policy. Completion requires exact manifest set equality,
complete line coverage, and source-bound summary artifacts; summary turns do
not require or expose super reasoning.

## Local Qwen3.8

The verified local profile on August 30, 2026 is **not** a `qwen3.8:16b` tag.
It is:

- `llama_cpp_process`;
- `qwen3.8-27b-direct`;
- based on `../Neuro-llama/Qwen3.8-27B-Q2_K.gguf`;
- configured for an 8192-token llama.cpp context.

The exact case-sensitive product launcher now performs automatic startup and
verification when it is invoked without an explicit provider configuration:

```bash
oiec-stm-sr-AgentICPI --repo .
```

It resolves the product label `qwen3.8:27B-Fast` to
`qwen3.8-27b-direct`, selects the direct provider, binds
`../Neuro-llama/Qwen3.8-27B-Q2_K.gguf`, verifies its configured digest, and
records any configured runner path. It never pulls, starts a model service, or
silently substitutes a model. Use `--no-auto-qwen` to disable the profile or
`--auto-qwen` with the source-tree/lowercase launchers.

Revalidate the current host before every governed run:

```bash
mkdir -p /tmp/ourd-preflight
oiec-stm-agent /tmp/ourd-preflight \
  --provider llama_cpp_process \
  --model qwen3.8-27b-direct \
  --runner-path /absolute/path/to/oiec-llama-runner \
  --model-path ../Neuro-llama/Qwen3.8-27B-Q2_K.gguf \
  --expected-model-sha256 028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9 \
  --llama-cpp-root /absolute/path/to/llama.cpp \
  --llama-cpp-build-dir /absolute/path/to/llama.cpp/build \
  --llama-grammar-dir "$PWD/grammars/providers" \
  --llama-context 8192 \
  --reasoning-effort none \
  --context-budget 6000 \
  --max-output-tokens 1400 \
  --preflight
```

Run the agent:

```bash
export OURD_PROVIDER=llama_cpp_process
export OURD_MODEL=qwen3.8-27b-direct
export OURD_LLAMA_RUNNER=/absolute/path/to/oiec-llama-runner
export OURD_LLAMA_MODEL_PATH=../Neuro-llama/Qwen3.8-27B-Q2_K.gguf
export OURD_LLAMA_MODEL_SHA256=028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9
export OURD_LLAMA_CPP_ROOT=/absolute/path/to/llama.cpp
export OURD_LLAMA_CPP_BUILD_DIR=/absolute/path/to/llama.cpp/build
export OURD_REASONING_EFFORT=none
export OURD_CONTEXT_BUDGET=6000
export OURD_MAX_OUTPUT_TOKENS=700
export OURD_TRANSPORT_RETRIES=0

oiec-stm-agent /path/to/repo --task "Inspect the repository read-only."
```

The provider refuses requests estimated to exceed its configured context budget
rather than silently increasing the verified model context.

### Direct llama.cpp Qwen3.8

OIEC-STM-Agent uses the Qwen3.8 GGUF through the native
`oiec-llama-runner` process. This provider uses a bounded
JSONL protocol, validates GBNF-constrained output, starts a fresh llama.cpp
context for every completion, performs zero hidden retries, and leaves all
authority, policy, EON, transaction, and approval decisions in OIEC-STM-Agent.
The reviewed grammar set includes ordinary message output, ordinary tool output,
and a compact no-whitespace function-call-only grammar. Every machine-readable
benchmark answer and individual proposer, verifier, falsifier, or synthesizer
object uses that structured tool channel, so JSON syntax is enforced before the
existing deterministic semantic validators run. Provider tool schemas declare
the allowed top-level vocabulary but intentionally leave role fields optional;
required semantics remain owned by the role parser, verifier, evidence gate,
and progress certificate rather than being misclassified as transport failure.
Micro-batch array entries likewise remain semantically untyped at the transport
boundary. A missing, extra, or non-object entry is rejected by the ordered role
parser, recorded as a reasoning-validation repair, and may consume one bounded
repair pass through independent structured object calls. The original response
hash and repair record remain in benchmark telemetry; no retry is hidden and no
malformed entry is accepted as evidence.
The default OIEC-SR profile
keeps proposers and falsifiers independent while verifying two candidates per
structured model call; those batch sizes are part of the signed reasoning
configuration rather than a prompt side effect.

Build the runner against an existing llama.cpp checkout as described in
`native/oiec_llama_runner/README.md`, then bind the exact runner, GGUF,
llama.cpp source, build directory, grammar directory, and model digest:

```bash
export OURD_PROVIDER=llama_cpp_process
export OURD_MODEL=qwen3.8-27b-direct
export OURD_LLAMA_RUNNER=/absolute/path/to/oiec-llama-runner
export OURD_LLAMA_MODEL_PATH=../Neuro-llama/Qwen3.8-27B-Q2_K.gguf
export OURD_LLAMA_MODEL_SHA256=028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9
export OURD_LLAMA_CPP_ROOT=/absolute/path/to/llama.cpp
export OURD_LLAMA_CPP_BUILD_DIR=/absolute/path/to/llama.cpp/build
export OURD_LLAMA_GRAMMAR_DIR="$PWD/grammars/providers"
export OURD_LLAMA_CONTEXT=4096
export OURD_LLAMA_GPU_LAYERS=32
export OURD_LLAMA_THREADS=12
export OURD_LLAMA_SEED=1234
export OURD_CONTEXT_BUDGET=2000
export OURD_MAX_OUTPUT_TOKENS=700
export OURD_TRANSPORT_RETRIES=0

oiec-stm-agent /path/to/repo --preflight
oiec-stm-agent /path/to/repo --task "Inspect the repository read-only."
```

The SHA-256 value above identifies the GGUF verified on August 28, 2026; it is
not permission to trust a different file with a similar name. Recompute and
review the digest, runner hash, llama.cpp commit, shared-library hashes, device
identity, context, sampler, and grammar hashes before qualification. The
benchmark harness shares one direct model process across the base, OIEC, and
OIEC-SR arms to avoid duplicate model residency, while the runner still creates
a fresh bounded context for each completion.

The provider-neutral local-model contract is adapted from the interface shape
reviewed in `../Neuro-main/include/neuro/local_model.hpp`. OIEC keeps the typed
status, descriptor, completion controls, metrics, streaming, chat-template, and
cancellation concepts, but fixes `max_attempts` to one and retains process
isolation so no retry can bypass CFEL or `AttemptKey`. See
`docs/NEURO_LLAMA_CPP_INTEGRATION.md` for the logic topology, reuse boundary,
tutorial, and live Qwen3.8 evidence.

Omit `--task` for a multi-turn terminal chat. `/new` starts a fresh model
context while preserving the repository audit trail, `/help` lists the local
commands, and `/exit` or `/quit` closes the session:

```bash
oiec-stm-agent /path/to/repo
```

### Optional legacy VisualGrammar2d Qwen 16B drafting path

`../VisualGrammar2d/qwen_cli.py` can be reused as a bounded, read-only drafting
helper for documentation, GUI labels, candidate explanations, and critique. It
supports an Ollama backend, repository-constrained study context, explicit
included files, deterministic decoding, input-character limits, output-token
limits, context limits, and request timeouts. This is a legacy external helper,
not the Agent Chat provider; Agent Chat uses `llama_cpp_process`.

On **August 21, 2026**, this host does not contain an Ollama model named
`qwen3.8:16b`; `ollama show qwen3.8:16b` returns "model not found". Do not
silently substitute another model. If that exact tag is installed and its
digest, quantization, context, GPU residency, latency, memory use, and task
quality are validated, a bounded README drafting invocation would look like:

```bash
python3 ../VisualGrammar2d/qwen_cli.py \
  --backend ollama \
  --model qwen3.8:16b \
  --ollama-model qwen3.8:16b \
  --project-root . \
  --study-project \
  --study-include README.md \
  --input-prompt-limit 8000 \
  --num-ctx 8192 \
  --max-new-tokens 700 \
  --response-style precise \
  --no-sample \
  "Draft a candidate README section describing the OIEC-STM-Agent GUI. Preserve all governance limits and mark unsupported claims."
```

The generated text is a proposal only. Source inspection, deterministic tests,
artifact hashes, exact-snapshot human approval, and rollback remain
authoritative. The GUI Model panel therefore reports backend/model facts as
observational metadata and explicitly marks model output non-authoritative.

## OIEC-STM-SR-AgentICPI Workbench

The `oiec-stm-sr-agent-icpi` entry point opens the Tkinter engineering
workbench and its Codex-like governed command prompt:

```bash
oiec-stm-sr-agent-icpi --repo /path/to/repository
```

For the currently verified local Qwen profile:

```bash
oiec-stm-sr-agent-icpi --repo /path/to/repository \
  --provider llama_cpp_process \
  --model qwen3.8-27b-direct \
  --runner-path /absolute/path/to/oiec-llama-runner \
  --model-path ../Neuro-llama/Qwen3.8-27B-Q2_K.gguf \
  --expected-model-sha256 028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9 \
  --llama-cpp-root /absolute/path/to/llama.cpp \
  --llama-cpp-build-dir /absolute/path/to/llama.cpp/build \
  --llama-grammar-dir "$PWD/grammars/providers" \
  --llama-context 8192 \
  --reasoning-effort none \
  --context-budget 6000 \
  --max-output-tokens 1400
```

The GUI is an observability and request surface over EGCF. It does not write
repository files directly or grant capability. Its principal panels are:

- **Selection Trace:** intent, required capabilities, candidates, exclusions,
  score components, exact qualification/evidence links, winner, and tie-break.
- **AgentICPI Prompt:** bounded multi-turn conversation, deterministic
  natural-language intent routing, live risk/ambiguity preview, slash-command
  completion, bounded `Ctrl+Up`/`Ctrl+Down` history, cooperative Stop, New Chat
  context boundaries, content-addressed bounded file/folder context envelopes,
  and an append-only replayable transcript. The transcript keeps the original
  request while the model receives a snapshot-bound structured projection.
  A read-only Context Inspector exposes exact envelope and source-snapshot
  identities, bounded attachment/file metadata, hash and truncation status, and
  redacted-by-default in-memory previews. Confirmation-required turns build that
  exact envelope first and issue a non-authoritative accepted/rejected receipt
  bound to the route, snapshot, envelope, budget, model-input SHA-256, counts,
  and pinned draft. Accepted receipts are verified before task creation and
  again immediately before provider invocation; rejection or drift starts no
  model turn. `/attach` adds up to 32 canonical
  workspace paths to a content-addressed pinned set and validates the resulting
  draft envelope without calling the model; `/detach` removes selected paths or
  clears all. `/context` reports a bounded file delta and `/context --refresh`
  explicitly accepts the observed snapshot; stale pins block model turns and
  are never silently refreshed. Pinned count/signature are visible in route
  previews, `/status`, the Context Inspector, and journal metadata. `/new` clears pins. GUI and core
  run-start audit records keep hashes and counts, not preview or structured-task
  bodies.
  Agent tools still pass through the normal authority, evidence, EON, and
  transaction controls.
- **Workflow / EON:** compiled DAG, risk, scope, pre/postconditions, rollback,
  exact source snapshot, matching approval, and execution state.
- **Evidence / Governance:** IEPS coverage dimensions, evidence classes,
  confidence gaps, invariants, decisions, assurance, live C0-C5 grant state,
  and non-authoritative JSON/Markdown evidence exports.
- **OURD / IURM:** canonical semantic graph output, clearly labelled GUI-only
  fallback links, returned dimensions, baselines, interactions, and MVD.
- **CFEL / Replay:** failure hypotheses, retry comparison, proposed regression
  commands, deterministic GUI event playback, and explicit dry-run plan replay.
- **Artifacts / Assurance:** passive text/image previews, bounded OBJ/STL/PLY
  metadata, provenance, and non-authoritative JSON/Markdown/HTML exports.
- **Semantic Terminal:** registered semantic commands plus one JSON input object;
  shell pipes, redirects, substitutions, and arbitrary executables are rejected.
- **Performance:** bounded timing telemetry, incremental task loading, and
  bounded immutable-object caching for large sessions.

Use `Ctrl+L` to focus AgentICPI and `Ctrl+K` for the command palette. Press
Enter to send, Shift+Enter to insert a newline, and type `/` for deterministic
command suggestions; Tab accepts the first matching command without submitting
it. GUI-only preferences, chat
events, and replay projection are stored under `.ourd-agent/gui/`; canonical
agent and EGCF state remain under `.ourd-agent/` and `.ourd-agent/egcf/`.

Headless launch validation is available for CI and packaging checks:

```bash
xvfb-run -a python3 -m ourd_gui --repo /tmp/fixture --smoke-test
```

`tools/validate.py` uses an isolated authenticated TCP Xvfb transport because
sandboxed runners may not own `/tmp/.X11-unix`; the application still connects
only through the validator's loopback display and temporary authority cookie.

See `docs/OIEC_STM_SR_AGENTICPI.md`, `docs/OURD_AGENT_GUI.md`, and the
`docs/GUI_*.md` contracts for prompt semantics, architecture, events, selection
semantics, safety, testing, migrations, and current limits.

## EGCFv1 Semantic Command Fabric

Version `0.7.0` adds grounded ReasoningTopology schema v2 on top of the
first-class bounded hypothesis state and RuntimeState schema v4 foundation under the
OIEC-STM-Agent name and OIEC-STMv1.2 bounded-transition layer. The Evidence
Governed Command Fabric remains available as the separate `egcf` entry point
above the existing OURD/EON primitives:

```text
Intent
  -> Typed Command
  -> Capability Resolution
  -> Qualified Algorithm Selection
  -> Evidence Gate
  -> Compiled Workflow
  -> Approval
  -> Executor/EON
  -> Verification
  -> Record and CFEL Learning
```

The shell is one executor, not the command abstraction. Command definitions are
strict data objects and cannot contain callbacks or executable fragments. C0-C2
support observation, analysis, and simulation. C3 local mutation remains
exclusive to EON and exact candidate transactions. C4 external mutation and C5
critical/destructive mutation fail closed in EGCFv1.

Inspect a read-only command without executing it:

```bash
python egcf.py capability list --repo . \
  --dry-run --why --json --graph --trace --record
```

Every command shares these modifiers:

```text
--dry-run --why --scope --evidence --approval --risk --rollback
--budget --timeout --trace --json --graph --record --replay
--strict --simulate
```

The first vertical slice includes versioned command and algorithm registries,
content-addressed records, capability narrowing, deterministic workflow DAGs,
evidence confidence and conflict checks, append-only invariants and decisions,
simulation, exact EON approval/execution/rollback, replay, assurance cases,
host adapters, generated typed command references, and governed grammar,
physics, geometry, vision, robotics, and CAD domain packs.

Legacy Qwen integration remains proposal-only. `tools/evaluate_egcf_qwen.py`
records the neighboring VisualGrammar2d wrapper and low-level CLI hashes for
historical EGCF evaluation. That path is not the Agent Chat provider; current
Agent Chat uses `llama_cpp_process`. The legacy evaluator binds the exact tag,
blob digests, meaningful-output checks, and source snapshot. It never converts
model output into authority, qualification, approval, or certification, and
refuses silent substitution when `qwen3.8:16b` is absent.

Generate an exact-snapshot deterministic validation bundle:

```bash
python3 tools/validate_egcf.py
```

See `docs/EGCFV1_COMMAND_REFERENCE.md`,
`docs/EGCFV1_GENERATED_REFERENCE.md`,
`docs/EGCFV1_REQUIREMENTS_MATRIX.md`, `docs/EGCFV1_MIGRATION.md`, and
`docs/EGCFV1_THREAT_MODEL.md` for the complete contract and current limits.

Regenerate and verify the checked-in schemas and command contracts with:

```bash
python3 tools/generate_egcf_reference.py --check
```

## Mutation Authority

First capture the source snapshot:

```bash
oiec-stm-agent /path/to/repo --snapshot
```

Generate an example manifest **outside the target repository** so writing the
manifest does not invalidate its own snapshot:

```bash
oiec-stm-agent /path/to/repo \
  --write-authority-example /tmp/ourd-authority.json
```

Review and narrow every field before use. The manifest follows
`schemas/authority-v1.schema.json` and includes:

- task ID and human goal;
- exact source snapshot hash;
- allowed and forbidden paths;
- read and command capabilities;
- maximum retries per action;
- maximum automatic risk;
- L1, L2, and `--yolo` policy;
- mandatory test commands;
- mandatory evidence requirements;
- expiry and operator identity.

Then run:

```bash
oiec-stm-agent /path/to/repo \
  --authority /tmp/ourd-authority.json \
  --task "Implement the authorized task and preserve the listed invariants."
```

An authority manifest becomes stale after a verified mutation. Issue a new
manifest bound to the new snapshot before starting another transaction.

## Mutation Lifecycle

1. Inspect authorized files and gather observations.
2. Establish HRT, OURD, and IURM governance within the external authority.
3. Prepare a single-file or multi-file candidate transaction. Workspace files
   remain unchanged.
4. Propose an EON action bound to the transaction, exact source snapshot,
   canonical command argv, and command capability IDs.
5. Gather evidence artifacts from read tools and authorized commands.
6. Submit evidence IDs with invariant, boundary, counterexample, test, or
   observation categories and the requirements they satisfy.
7. Apply only after the deterministic gate approves the exact action.
8. Run authorized verification commands.
9. Finalize using successful command evidence, or roll back exact original
   bytes and modes.
10. On a collision, revise the action or evidence; do not repeat the unchanged
    failed call.

Prepared transactions may be discarded through `rollback_transaction` before
application. Applied or verified transactions use the same operation to restore
their recorded originals.

## Command Capabilities

`run_command` supports only deterministic capabilities currently implemented by
`ourd/policy.py`:

- `git.status`;
- `git.diff`;
- `python.unittest`;
- `python.py_compile`;
- `ctest.run`;
- `cmake.build`;
- `compiler.syntax_check`.

Commands such as `python -c`, `sed -i`, `find -delete`, `git add`, `git restore`,
`git push`, response files, shell chaining, environment assignments, unsafe
compiler flags, and unknown executables are blocked. A capability must be
present in the authority manifest, every referenced command path must remain
inside authority scope, and the canonical argv must be present in the current
EON action. Changing an argument requires a different action identity.

## Risk Classes

- **L0:** read-only operation.
- **L1:** bounded workspace mutation or verification command.
- **L2:** structural, broad, dependency, configuration, build-system, or
  difficult-to-reverse change.

The effective risk is the greater of the model proposal and the deterministic
minimum. The model cannot classify a file write as L0.

## State and Evidence

The internal directory contains:

- `.ourd-agent/events.jsonl`: append-only hash-chained events with run, action,
  and transaction lineage;
- `.ourd-agent/state.json`: atomic, rebuildable current-state projection;
- `.ourd-agent/transactions/`: candidate content, transaction metadata, and
  rollback originals;
- `.ourd-agent/evidence/`: explicit validation reports and full redacted command
  output artifacts bound by SHA-256;
- `.ourd-agent/lock`: one-writer lock.

If `state.json` is invalid JSON or differs from the latest valid state event, it
is rebuilt from the event chain. Runtime schema 1 is migrated to schema 2 by
appending a new hash-chained state snapshot; historical events are never
rewritten. A broken event hash chain or unknown runtime schema fails closed.

## Validation

Run deterministic validation:

```bash
python3 tools/validate.py
```

Run deterministic validation plus the optional live Qwen read-only tool loop
when a direct runner and GGUF are configured:

```bash
python3 tools/validate.py --live-llama-cpp
```

Validation writes a JSON evidence report under `.ourd-agent/evidence/` unless
`--no-report` is supplied. Live-model success is reported separately and cannot
override deterministic failures.

## Claim-to-Test Matrix

| Enforcement claim | Primary proof |
| --- | --- |
| Canonical paths and internal-state protection | `tests/test_workspace.py` |
| External authority and risk floors | `tests/test_authority.py`, `tests/test_policy.py` |
| Exact action, grounded gates, limits, expiry | `tests/test_actions.py` |
| Atomic apply, multi-file recovery, mode rollback | `tests/test_actions.py` |
| State restoration, chain validation, locking, redaction | `tests/test_persistence.py` |
| Non-stateful tool loop and direct llama.cpp process transport | `tests/test_provider.py`, `tests/providers/test_llama_cpp_process.py` |
| CLI contract and strict tool schemas | `tests/test_cli.py` |
| Empty reads and escaping-symlink listing | `tests/test_reads.py` |
| Versioned schema artifacts | `tests/test_schemas.py` |

## Current Limitations

1. There is no OS, container, network, seccomp, namespace, or hypervisor
   sandbox. Run untrusted repositories in a separate sandbox.
2. Command capabilities are intentionally narrow and must be extended in code
   with adversarial tests.
3. Evidence artifacts are grounded to actual tool results, but semantic mapping
   from an artifact to an invariant remains model-proposed and should be reviewed
   for high-impact work.
4. Atomic multi-file application is implemented as ordered atomic file replaces
   plus complete rollback on failure; it is not a filesystem-wide atomic commit.
5. The event log is tamper-evident, not cryptographically signed by an external
   authority.
6. Exact human identity and signature verification are represented in the
   authority record but not integrated with an external identity provider.
7. Certification, commit, push, deployment, and release remain external human or
   governance actions.
8. Provider transport retries default to zero and are capped at five. Mutation
   retries are separately constrained by exact action identity, evidence
   revision, risk, and authority.
9. The GUI uses Tkinter and bounded native previews. JPEG, GLTF, GLB, live
   OpenGL geometry, unrestricted PTY behavior, and remote model lifecycle
   control are not enabled in this candidate.

The implementation state remains a governed candidate until its exact source
hashes, deterministic validation report, optional live-model evidence, rollback
evidence, and unresolved risks are reviewed by a human authority.
