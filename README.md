# OURD Coding Agent

A compact Python coding agent with a deterministic governance and transaction
boundary:

**HRTv1 → OURD → IURMv1.1.1 → EONv1 → Evidence Gate → Action → CFEL feedback**

The model may inspect, reason, propose, generate candidate patches, and analyze
failures. It cannot grant itself mutation authority, lower deterministic risk,
approve its own unsupported evidence, write internal evidence, or certify a
release.

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

## Install

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The local Ollama transport uses the Python standard library. For OpenAI or
another remote OpenAI-compatible provider, install the optional SDK:

```bash
pip install -e '.[openai]'
```

## Read-Only Use

Without `--authority`, the agent is deliberately read-only:

```bash
python ourd_agent.py /path/to/repo \
  --task "Inspect the parser and report the likely regression. Do not modify files."
```

Read-only runs may create `.ourd-agent/` evidence and state inside the target
workspace, but cannot mutate ordinary workspace files.

## Local Qwen3.8

The verified local profile on August 21, 2026 is **not** a `qwen3.8:16b` tag.
It is:

- Ollama `0.32.14`;
- `qwen3.8-27b-fast:latest`;
- based on `hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_S`;
- configured for an 8192-token context and `draft_num_predict 2`.

Revalidate the current host before every governed run:

```bash
mkdir -p /tmp/ourd-preflight
python ourd_agent.py /tmp/ourd-preflight \
  --base-url http://127.0.0.1:11434/v1 \
  --api-key ollama \
  --model qwen3.8-27b-fast \
  --reasoning-effort none \
  --context-budget 6000 \
  --max-output-tokens 700 \
  --preflight
```

Run the agent:

```bash
export OURD_BASE_URL=http://127.0.0.1:11434/v1
export OURD_API_KEY=ollama
export OURD_MODEL=qwen3.8-27b-fast
export OURD_REASONING_EFFORT=none
export OURD_CONTEXT_BUDGET=6000
export OURD_MAX_OUTPUT_TOKENS=700
export OURD_TRANSPORT_RETRIES=0

python ourd_agent.py /path/to/repo --task "Inspect the repository read-only."
```

The provider refuses requests estimated to exceed its configured context budget
rather than silently increasing the verified model context.

Omit `--task` for a multi-turn terminal chat. `/new` starts a fresh model
context while preserving the repository audit trail, `/help` lists the local
commands, and `/exit` or `/quit` closes the session:

```bash
python ourd_agent.py /path/to/repo
```

### Optional VisualGrammar2d Qwen 16B drafting path

`../VisualGrammar2d/qwen_cli.py` can be reused as a bounded, read-only drafting
helper for documentation, GUI labels, candidate explanations, and critique. It
supports an Ollama backend, repository-constrained study context, explicit
included files, deterministic decoding, input-character limits, output-token
limits, context limits, and request timeouts.

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
  "Draft a candidate README section describing the OURD GUI. Preserve all governance limits and mark unsupported claims."
```

The generated text is a proposal only. Source inspection, deterministic tests,
artifact hashes, exact-snapshot human approval, and rollback remain
authoritative. The GUI Model panel therefore reports backend/model facts as
observational metadata and explicitly marks model output non-authoritative.

## Evidence-Governed GUI Workbench

The `ourd-gui` entry point opens the Tkinter engineering workbench:

```bash
ourd-gui --repo /path/to/repository
```

For the currently verified local Qwen profile:

```bash
ourd-gui --repo /path/to/repository \
  --model qwen3.8-27b-fast \
  --base-url http://127.0.0.1:11434/v1 \
  --api-key ollama \
  --reasoning-effort none \
  --context-budget 6000 \
  --max-output-tokens 700
```

The GUI is an observability and request surface over EGCF. It does not write
repository files directly or grant capability. Its principal panels are:

- **Selection Trace:** intent, required capabilities, candidates, exclusions,
  score components, exact qualification/evidence links, winner, and tie-break.
- **Agent Chat:** bounded multi-turn conversation, multiline composer, live
  model/tool activity, cooperative Stop, New Chat context boundaries, and an
  append-only replayable transcript. Agent tools still pass through the normal
  authority, evidence, EON, and transaction controls.
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

Use `Ctrl+L` to focus Agent Chat and `Ctrl+K` for the command palette. Press
Enter to send and Shift+Enter to insert a newline. GUI-only preferences, chat
events, and replay projection are stored under `.ourd-agent/gui/`; canonical
agent and EGCF state remain under `.ourd-agent/` and `.ourd-agent/egcf/`.

Headless launch validation is available for CI and packaging checks:

```bash
xvfb-run -a python3 -m ourd_gui --repo /tmp/fixture --smoke-test
```

`tools/validate.py` uses an isolated authenticated TCP Xvfb transport because
sandboxed runners may not own `/tmp/.X11-unix`; the application still connects
only through the validator's loopback display and temporary authority cookie.

See `docs/OURD_AGENT_GUI.md` and the `docs/GUI_*.md` contracts for architecture,
events, selection semantics, safety, testing, migrations, and current limits.

## EGCFv1 Semantic Command Fabric

Version `0.3.1` adds the Evidence Governed Command Fabric as a separate `egcf`
entry point above the existing OURD/EON primitives:

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

Qwen integration remains proposal-only. `tools/evaluate_egcf_qwen.py` records
the neighboring VisualGrammar2d wrapper and low-level CLI hashes, but uses a
bounded raw Ollama request because the current wrapper routes its advertised
model option to the default Ollama model and the direct CLI produces an empty
fallback with this alias's stop-token template. The evaluator binds the exact
tag, full Ollama blob digests, meaningful-output checks, and post-run 100% GPU
residency, and verifies that the source snapshot remains unchanged. It never
converts model output into authority, qualification, approval, or
certification, and refuses silent substitution when `qwen3.8:16b` is absent.

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
python ourd_agent.py /path/to/repo --snapshot
```

Generate an example manifest **outside the target repository** so writing the
manifest does not invalidate its own snapshot:

```bash
python ourd_agent.py /path/to/repo \
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
python ourd_agent.py /path/to/repo \
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
is rebuilt from the event chain. A broken event hash chain fails closed.

## Validation

Run deterministic validation:

```bash
python3 tools/validate.py
```

Run deterministic validation plus the optional live Qwen read-only tool loop:

```bash
python3 tools/validate.py --live-ollama
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
| Non-stateful tool loop and direct Ollama transport | `tests/test_provider.py` |
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
