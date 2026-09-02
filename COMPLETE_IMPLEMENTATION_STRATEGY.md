# OIEC-STM-Agent Complete Implementation Strategy

**Strategy date:** August 28, 2026  
**Repository:** `pghauff73/OIEC-STM-Agent`  
**Purpose:** complete, integrate, qualify, document, and release every accepted
implementation without weakening authority, evidence, retry, persistence, or
mutation invariants.

## 1. Objective

This strategy is the program-level execution authority for completing the
accepted implementation plans already present in the repository:

- `IMPLEMENTATION_PLAN.md`;
- `OIEC_STMV1_2_IMPLEMENTATION_PLAN.md`;
- `OIEC_SR_V1_IMPLEMENTATION_PLAN.md`;
- `EGCFV1_IMPLEMENTATION_PLAN.md`;
- `OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md`;
- `DOCS_RELATIONAL_TREE_REFACTOR_PLAN.md`; and
- `DOCS_BEGINNER_ESSAY_REWRITE_PLAN.md`.

It also incorporates the requested direct `llama.cpp` interface extracted from
`../Neuro-main`, the verified Qwen3.8 model profile, and the implementations that
already landed on GitHub `main` after the current local branch diverged.

The target end state is:

```text
Human authority
    -> OURD semantic problem model
    -> OIEC-STM boundary and dimension control
    -> OIEC-SR bounded competing explanations
    -> IURM discriminating experiment
    -> EON exact action identity
    -> EGCF evidence and capability gates
    -> governed transaction/execution
    -> CFEL collision learning
    -> GUI and documentation projections
    -> deterministic qualification
    -> exact-snapshot human approval
    -> public MIT release on GitHub main
```

No narrower milestone, focused test run, generated report, model response, or
successful push is sufficient to claim this objective complete.

## 2. Non-Negotiable Completion Rules

1. **External authority remains supreme.** Models, SR, GUI, documentation,
   adapters, benchmarks, and generated evidence cannot create approval or expand
   authority.
2. **There is one mutation path.** Repository writes and governed commands remain
   transaction-, EON-, policy-, and evidence-gated.
3. **Canonical ownership remains singular.** Add missing projections and adapters;
   do not create duplicate authority, evidence, topology, state, or executor
   owners.
4. **Current source is authoritative.** Historical reports become stale after any
   relevant source, generated artifact, model, runtime, or workflow change.
5. **Generated documentation follows source freeze.** Documentation is rebuilt
   after implementation integration, not used to freeze an intermediate API.
6. **Failures remain evidence.** Do not rewrite fixtures, lower thresholds,
   suppress errors, or change expected behavior merely to obtain green output.
7. **Local-model output remains advisory.** Qwen3.8 may propose, compare, verify,
   falsify, or draft; deterministic code and human approval decide.
8. **Every completion claim needs requirement-level evidence.** A plan is complete
   only when every named deliverable and gate has a current evidence owner.

## 3. Authoritative Current-State Snapshot

### 3.1 Repository and remote

Current observations on August 28, 2026:

- GitHub repository: `pghauff73/OIEC-STM-Agent`;
- visibility: `PUBLIC`;
- default branch: `main`;
- license: MIT;
- local branch: `codex/rewrite-beginner-essays` at `2fd90c9`;
- remote `main`: `2faa4d5`;
- local base is eleven commits behind remote `main`;
- local worktree contains 179 modified and 108 untracked paths;
- five upstream-changed files overlap the local dirty set:
  `ourd/__init__.py`, `ourd/cli.py`, `ourd/providers/base.py`,
  the provider transport module, and `pyproject.toml`.

The upstream eleven-commit delta adds bounded writing modes, formal-writing
profiles, multimodal visual editing, visual similarity, mesh import, a headless
OpenGL vertical slice, and GitHub Actions qualification workflows. These are part
of the final integrated product and must not be lost when current SR and
documentation work is incorporated.

### 3.2 Current focused validation

Current focused evidence:

- `python3 -m compileall -q ourd ourd_gui tests tools` passes;
- 147 focused OIEC, persistence, provider, SR, benchmark, and topology tests pass;
- 24 focused EGCF, security, vertical, GUI validation, and packaging tests pass;
- `tests.test_docs_site` has 17 failures because generated concept-source hashes
  are stale relative to the newly changed SR source;
- the failure is synchronization evidence, not a documentation-design failure.

### 3.3 Workstream classification

| Workstream | Current state | Completion requirement |
| --- | --- | --- |
| Governed core | Implemented candidate | Revalidate after integration and bind a new exact-source report |
| OIEC-STMv1.2 | Implemented; focused tests green | Revalidate state migration, retry, progress, and mutation boundaries on integrated source |
| EGCFv1 | Feature-complete candidate | Run full validation, rebuild generated references, exact-snapshot approval |
| GUI v1 | Feature-complete candidate | Integrate upstream visual workbench, re-run headless, packaging, safety, and performance gates |
| Documentation tree | Implemented but stale | Regenerate after code freeze, prove deterministic equality and full source-hash coverage |
| OIEC-SR SR-0/SR-1 | Implemented and benchmarked | Preserve artifacts and rerun matched qualification after later SR work |
| OIEC-SR SR-2A | Deterministic implementation present | Close plan/report status and obtain live provider evidence without hidden retries |
| OIEC-SR SR-3 through SR-10 | Incomplete | Implement and pass every milestone gate and release comparison |
| Ollama Qwen3.8 | Existing provider path | Requalify exact model/runtime and isolate benchmark lifecycle |
| Direct llama.cpp Qwen3.8 | Design only | Add process adapter, exact hashes, structured output, tool-call translation, tests, and qualification |
| Upstream writing/visual/OpenGL | On remote `main`, absent locally | Integrate without regressing governance, SR, docs, packaging, or GUI safety |
| Release/certification | Not current | Produce new immutable candidate bundle and obtain exact-hash human approval |

## 4. Program Dependency Graph

```text
P0 Preserve current work and provenance
    |
    v
P1 Integrate remote main and resolve five overlap files
    |
    v
P2 Freeze requirement inventory and current-source baseline
    |
    +-----------------------+
    |                       |
    v                       v
P3 Requalify core/STM/EGCF  P4 Complete OIEC-SR core
    |                       |
    |                       v
    |                   P5 Add direct llama.cpp/Qwen3.8
    |                       |
    +-----------+-----------+
                |
                v
P6 Integrate GUI, visual, writing, and reasoning projections
                |
                v
P7 Regenerate the complete documentation system
                |
                v
P8 Run full qualification, benchmarks, ablations, and packaging
                |
                v
P9 Freeze release candidate, approve exact hashes, merge, tag, publish
```

Work may run in parallel only when write sets are disjoint and neither task
depends on generated artifacts from the other. Documentation regeneration,
release hashing, and final benchmarks are deliberately late-bound.

## 5. Phase P0 — Preserve Work and Establish Recovery

### Deliverables

1. Record `git status --porcelain=v2`, current `HEAD`, remote `main`, and all plan
   hashes.
2. Create an immutable patch bundle covering tracked modifications and a separate
   archive/manifest for untracked paths.
3. Record SHA-256 for both preservation artifacts.
4. Create a clean integration worktree from current `origin/main`.
5. Do not delete, reset, stash-drop, or overwrite the existing dirty worktree.

### Gate P0

Recovery is proven by reconstructing the local delta into a temporary worktree
and comparing its intended-file manifest with the original dirty worktree.

## 6. Phase P1 — Integrate Remote Main

### Integration order

1. Start from `origin/main` at `2faa4d5` or its verified successor.
2. Apply OIEC-SR source and tests first, excluding generated documentation.
3. Resolve the five overlap files manually using canonical ownership:
   - `ourd/__init__.py`: preserve all public writing, visual, STM, and SR exports;
   - `ourd/cli.py`: preserve writing-mode and visual commands while adding SR and
     provider controls;
   - `ourd/providers/base.py`: preserve upstream provider additions and the bounded
     multi-response/SR contract;
   - `ourd/providers/llama_cpp_process.py`: preserve direct process transport,
     exact preflight evidence, task-bound runtime release, and SR batching;
   - `pyproject.toml`: preserve all entry points, dependencies, package data, and
     advance one coherent development version.
4. Apply documentation generator and source Markdown changes.
5. Do not apply generated HTML, SVG, or manifest files until Phase P7.

### Required tests

```text
python3 -m compileall -q ourd ourd_gui tests tools
python3 -m unittest -v tests.test_cli tests.test_provider
python3 -m unittest -v tests.test_oiec tests.test_persistence tests.test_reasoning
python3 -m unittest discover -s tests/gui -t . -v
```

### Gate P1

- all remote features remain discoverable;
- all local SR APIs remain discoverable;
- no duplicate command, provider, model, state, or GUI owner exists;
- no intended file from either side is omitted;
- the integration branch has a documented source manifest.

## 7. Phase P2 — Freeze the Complete Requirement Inventory

Create `reports/completion/<run-id>/requirements.json` and a Markdown projection
with one row for every explicit requirement in all seven plan documents plus this
strategy.

Each row must contain:

```text
requirement_id
source_plan
source_heading
requirement_text
canonical_owner
implementation_paths
test_or_evidence_owner
status
blocking_dependencies
last_verified_source_hash
```

Allowed status values:

```text
NOT_IMPLEMENTED
IMPLEMENTED_UNVERIFIED
FOCUSED_VALIDATED
FULLY_VALIDATED
HUMAN_APPROVAL_REQUIRED
CERTIFIED
RELEASED
EXPLICITLY_EXCLUDED
```

No requirement may disappear because it is difficult, duplicated in prose, or
already described as complete by an older report.

### Gate P2

- every numbered phase, milestone, test family, exit gate, release gate, and
  deliverable has exactly one requirement row;
- every row has a canonical implementation and evidence owner;
- duplicate wording maps to one requirement identity without losing provenance;
- all historical completion claims are classified against current source.

## 8. Phase P3 — Requalify Existing Foundations

### 8.1 Governed core and OIEC-STM

Re-run and inspect:

- authority expiry and exact-snapshot checks;
- deterministic risk floors;
- canonical path and capability validation;
- transaction preparation, atomic apply, rollback, and recovery;
- hash-chain persistence and migrations through RuntimeState v4;
- action-scoped finite evidence;
- AttemptKey no-blind-retry behavior;
- boundary and dimension limits;
- progress certification and small-state reachability/cycle proofs;
- CFEL collision identity and significant-failure registration.

### 8.2 EGCF

Re-run:

- schema and catalog generation;
- command compilation and selection;
- capability and adapter qualification;
- C0-C5 safety enforcement;
- exact approval use limits;
- simulation labelling;
- domain-pack contracts;
- EON authorization and execution path;
- assurance-case and completion-matrix generation.

### 8.3 GUI foundation

Re-run:

- read-only import and mutation-boundary checks;
- event projection and replay;
- selection trace;
- evidence, approval, CFEL, workflow, and assurance views;
- redaction and bounded rendering;
- headless Tk construction;
- wheel and source-distribution content checks.

### Gate P3

Every foundation requirement is `FULLY_VALIDATED` on one current source manifest.
External approval and certification may remain open, but implementation and
deterministic evidence may not.

## 9. Phase P4 — Complete OIEC-SR v1.0

### P4.1 Close SR-2A

The current topology v2 source and deterministic tests indicate implementation,
but the plan still labels SR-2A as next. Close the milestone by:

1. updating the plan status from actual evidence;
2. recording topology source and test hashes;
3. running a live provider-bound evaluation;
4. proving inference IDs, modes, evidence references, grounding paths,
   assumption-only hypotheses, connectivity, and attack semantics;
5. recording malformed/unsupported paths as collisions without retrying blindly.

### P4.2 SR-3 — Structural diversity

- add versioned structural similarity configuration;
- collapse prose-only duplicates;
- preserve genuinely different hypotheses, evidence sets, inference structures,
  and conclusions;
- bind diversity measurements into candidate records.

### P4.3 SR-4 — Verifier v2

- add premise, evidence, inference, consistency, completeness, and weakest-step
  scores;
- expose unsupported nodes, contradictions, and missing assumptions;
- prevent proposer confidence from overriding verifier evidence.

### P4.4 SR-5 — Falsifier v2

- add alternative explanations, boundary tests, assumption inversion, causal
  reversal checks, counterexamples, and deterministic adapter hooks;
- ensure falsification results update the relevant hypothesis and topology.

### P4.5 SR-6 — Ranking and verified synthesis

- move ranking weights into a signed versioned configuration;
- add `SynthesisResult`;
- merge only compatible grounded components;
- verify the synthesis independently before certification;
- reject synthesis that creates a stronger conclusion than its sources.

### P4.6 SR-7 — Adaptive compute and context

- enforce path, step, verifier, falsifier, token, tool, and provider-call budgets;
- add bounded `ReasoningContext` rather than replaying raw conversation history;
- implement typed VOI operations and deterministic stopping.

### P4.7 SR-8 — Certificates, contradictions, GUI, and export

- add reasoning certificate v2;
- add persistent `ContradictionRecord` lifecycle;
- cap confidence when critical contradictions remain;
- bind certificate, hypothesis state, score configuration, synthesis, and source;
- expose read-only GUI and bounded JSON/Markdown projections.

### P4.8 SR-9 — Mathematical and causal adapters

- add Decimal/Python arithmetic, SymPy, residual, dimensional, finite-domain, and
  constraint adapters where dependencies are available;
- add causal nodes, edges, interventions, counterfactuals, confounders, mediators,
  moderators, and observational/interventional distinction;
- fail closed when an adapter is unavailable or inconclusive.

### P4.9 SR-10 — Qualification

- run base, OIEC, and OIEC-SR comparisons;
- run ablations without verifier, falsifier, hypothesis state, adaptive compute,
  and multi-path search;
- use held-out tasks and repeated matched runs;
- report accuracy, calibration, evidence coverage, counterexample detection,
  failure recovery, tokens, tool cost, latency, memory, and confidence intervals;
- do not claim “super reasoning” unless measured results satisfy the release gate.

### Gate P4

Every SR-0 through SR-10 requirement is fully implemented, deterministic tests
pass, live provider runs are source/model/runtime bound, and the qualification
report states whether the performance claim passed or failed without rewriting
the target after seeing results.

## 10. Phase P5 — Direct llama.cpp and Qwen3.8

### 10.1 Extraction boundary

Extract only the provider-neutral interface logic from `../Neuro-main`:

- typed model request/result/status/metrics contracts;
- direct GGUF model loading;
- bounded context creation;
- GBNF structured-output sampling;
- cancellation, deadlines, and streaming;
- model-free grammar/schema/context/build preflight.

Do not import Neuro's domain protocol, transaction engine, governance owner, or
application state. Resolve the licensing/provenance status of Neuro-specific code
before copying it; retain llama.cpp's MIT notice for vendored or linked code.

### 10.2 Process architecture

Add:

```text
native/oiec_llama_runner/
ourd/providers/llama_cpp_process.py
schemas/providers/llama_cpp_request.schema.json
schemas/providers/llama_cpp_response.schema.json
grammars/providers/oiec_reasoning_response.gbnf
grammars/providers/oiec_tool_response.gbnf
tests/providers/test_llama_cpp_process.py
```

Use a bounded JSONL subprocess protocol with operations:

```text
describe
complete
cancel
reset_context
shutdown
```

The runner may load the model once, but each completion receives a fresh bounded
context. Benchmarks must be able to shut down the runner at task/system boundaries.

### 10.3 Exact identity

Preflight must bind:

- GGUF SHA-256 and size;
- model architecture, parameter count, and quantization;
- llama.cpp source/build manifest;
- shared-library hashes;
- CUDA/backend capability and device identity;
- context, KV, sampler, grammar, seed, and output limits.

The verified local Qwen3.8 GGUF digest is:

```text
028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9
```

Reverify it before qualification rather than treating this strategy as runtime
evidence.

### 10.4 OIEC compatibility

- configure one provider attempt per OIEC AttemptKey;
- do not hide semantic retries inside the runner;
- translate structured message/function-call envelopes into the existing
  Responses-compatible `output` list;
- validate every tool name and argument schema before returning a call;
- keep dispatch, policy, EON, transactions, and approval in OIEC;
- persist concise structured records, not private reasoning traces.

### 10.5 Qualification order

1. model-free preflight;
2. fake-runner protocol tests;
3. real GGUF descriptor smoke;
4. one tool-free structured OIEC-SR response;
5. four sequential OIEC-SR candidates;
6. read-only tool proposal;
7. governed candidate-transaction proposal;
8. cancellation/deadline/context-overflow/OOM recovery;
9. matched Ollama versus direct llama.cpp benchmark.

### Gate P5

The direct provider passes all protocol and governance tests, exposes exact
identity, performs no hidden retry, cannot mutate the workspace, and completes a
source/model/runtime-bound Qwen3.8 qualification run.

## 11. Phase P6 — Integrate Product Surfaces

### 11.1 GUI

Integrate upstream writing, multimodal, visual-similarity, mesh, and OpenGL
features with current evidence-governed views. Preserve:

- one `CoreGateway` mutation boundary;
- read-only SR and provider observability;
- passive HTML/SVG handling;
- explicit authority for writing mode;
- bounded geometry and image handling;
- optional OpenGL capability with fail-closed fallback;
- reduced motion, keyboard access, non-color status, and bounded resource use.

### 11.2 CLI and providers

Expose coherent commands and configuration for:

- governed coding;
- bounded writing mode;
- formal writing profile;
- Ollama provider;
- direct llama.cpp provider;
- SR enablement and budgets;
- visual matching and headless rendering;
- preflight and qualification.

### 11.3 Persistence and migrations

Define and test migration ownership for all new durable SR/provider/GUI fields.
Historical hash-chain events remain immutable; projections migrate forward and
append a migration event.

### Gate P6

The combined application exposes all accepted features without duplicated
authority, broken compatibility aliases, unsafe GUI execution, or ambiguous
provider ownership.

## 12. Phase P7 — Regenerate Documentation Last

### Required sequence

1. freeze integrated source for documentation generation;
2. run `tools/build_docs_site.py`;
3. verify every source SHA in `docs/site-manifest.json`;
4. rebuild into a second clean output tree;
5. compare every generated byte and tree hash;
6. parse every SVG as XML;
7. validate JavaScript syntax;
8. verify every local page, anchor, asset, relational ID, and symbol;
9. run accessibility-oriented structural checks;
10. run `tests.test_docs_site` and the complete suite.

The generated tree must include all newly integrated SR, provider, writing,
visual, mesh, OpenGL, CI, and qualification concepts. Every heading essay and
concept essay retains the required five five-paragraph logic-topology blocks,
beginner definitions, references, argumentative position, decisive conclusion,
interactive SVG, and 1980s purple-and-white systems-architect design.

### Gate P7

- zero stale source hashes;
- zero missing concepts or relations;
- zero unresolved local links;
- byte-identical repeated generation;
- all documentation tests pass;
- any unavailable browser screenshot is recorded as a limitation, not silently
  treated as evidence.

## 13. Phase P8 — Full Qualification

### 13.1 Deterministic validation order

```text
1. compileall
2. focused changed-module tests
3. OIEC/CFEL/persistence/property tests
4. SR/topology/provider/benchmark tests
5. EGCF schema/security/vertical tests
6. complete GUI suite
7. documentation generation and tests
8. full unittest discovery
9. headless GUI smoke
10. optional OpenGL headless smoke
11. wheel and sdist build
12. clean-environment wheel install and command smoke
13. validation tools and generated-reference checks
14. Git whitespace and untracked-artifact audit
```

Every command records start/end time, exit status, interpreter/runtime versions,
source manifest, and output hash. Interrupted tests are not passes.

### 13.2 Live-model qualification

For Ollama and direct llama.cpp separately:

- bind exact model SHA-256/tag, runtime version, GPU, context, KV and sampler;
- unload unrelated competing model processes;
- require sequential GPU-heavy work;
- preserve failed/OOM results;
- run repeated matched benchmark seeds/configurations;
- record provider failures and zero-blind-retry evidence;
- distinguish correctness, host performance eligibility, governance eligibility,
  and release eligibility.

### 13.3 CI qualification

GitHub Actions must run deterministic non-GPU gates on clean checkouts. GPU and
local-model qualification remains a signed external artifact referenced by the
release candidate, unless an appropriately controlled runner is available.

### Gate P8

One immutable qualification directory contains:

```text
source_manifest.json
requirements.json
validation_report.json
test_logs/
package_hashes.sha256
docs_manifest.json
benchmark_reports/
limitations.json
rollback_manifest.json
candidate_summary.md
```

Every accepted claim points to one or more artifacts in that directory.

## 14. Phase P9 — Release, Merge, and Publication

### Candidate freeze

1. Ensure the worktree contains only intended source and generated artifacts.
2. Regenerate all current reports from the frozen source.
3. Record the candidate commit SHA and qualification directory hashes.
4. Obtain explicit human approval naming those exact hashes.
5. Do not edit the candidate after approval.

### Git and GitHub sequence

```text
integration branch
    -> reviewed commits by workstream
    -> pull request against current main
    -> CI green on exact head
    -> exact-hash approval recorded
    -> merge to main
    -> verify remote main SHA equals merged SHA
    -> tag release candidate/version
    -> verify public repository and MIT license
    -> publish package/release artifacts
```

A successful `git push` is not proof of publication. Verify the target remote ref
with both local Git and GitHub after the push/merge.

### Release states

```text
IMPLEMENTED
    -> DETERMINISTICALLY_VALIDATED
    -> MODEL_QUALIFIED
    -> HUMAN_APPROVAL_REQUIRED
    -> APPROVED_CANDIDATE
    -> MERGED
    -> RELEASED
```

Certification, if required, remains a separate external state after release.

## 15. Error-Countering and Continuation Protocol

### Merge or source conflict

- stop applying generated artifacts;
- identify the canonical owner for each semantic fact;
- preserve both independently valid capabilities;
- add compatibility migrations rather than dropping one side;
- rerun the smallest relevant tests, then the broad dependency suite.

### Stale generated artifacts

- never patch source hashes manually;
- rebuild from the canonical generator after source stabilization;
- compare regenerated output twice;
- treat mismatched hashes as source drift until proven otherwise.

### Malformed provider output

- reject it as `InvalidOutput`/`ProviderError` evidence;
- record a collision and exact AttemptKey;
- do not silently parse prose or retry with changed wording;
- retry only after relevant evidence, action, boundary, dimension, model, or
  snapshot state changes.

### GPU OOM or contention

- terminate and verify removal of the selected model process;
- inspect competing processes and GPU allocation;
- reduce one declared dimension at a time: concurrency, context, KV precision,
  output budget, or quantization;
- retain the failed profile as evidence;
- do not report release-grade latency under contention.

### Test failure

- preserve the failing command and log;
- reproduce with the narrowest owner test;
- fix root cause rather than changing the expected result;
- rerun focused, dependency, then full suites;
- update the requirement row and collision record.

### External approval unavailable

- complete implementation, deterministic validation, packaging, and candidate
  hashing;
- stop at `HUMAN_APPROVAL_REQUIRED`;
- do not label the candidate certified or released.

## 16. Workstream Evidence Matrix

| Workstream | Primary implementation proof | Required acceptance evidence |
| --- | --- | --- |
| Core authority/policy | `ourd/authority.py`, `ourd/policy.py`, agent gates | authority, scope, expiry, risk, adversarial tests |
| Transactions/EON | `ourd/transactions.py`, action paths | atomicity, stale snapshot, rollback, recovery tests |
| Persistence | `ourd/persistence.py`, state models | migrations, hash-chain replay, corruption tests |
| OIEC-STM | `ourd/oiec.py`, OIEC records | finite-state, retry, monotonic evidence, progress properties |
| CFEL | `ourd/cfel.py` | collision identity, significant-failure and hypothesis-update tests |
| OIEC-SR | `ourd/reasoning/` | milestone tests, live model reports, ablations, qualification |
| EGCF | `ourd/egcf/` | schema, compiler, security, domain, vertical and completion reports |
| Providers | `ourd/providers/`, native runner | exact preflight, context, timeout, cancellation, identity, malformed-output tests |
| GUI | `ourd_gui/` | read-only boundary, headless construction, accessibility, packaging |
| Writing/visual | upstream source modules | authority, file safety, geometry/image bounds, optional-renderer tests |
| Documentation | generator and `docs/` | complete coverage, closed links, deterministic rebuild, source hashes |
| Packaging/CI | `pyproject.toml`, workflows | wheel/sdist/install smoke, clean CI, artifact hashes |
| Release | Git/GitHub and qualification bundle | exact approval, merged SHA parity, public MIT repository, tag/artifacts |

## 17. Definition of Done

The complete implementation program is done only when all of the following are
true on the same frozen source candidate:

1. all upstream and local intended features are integrated;
2. every plan requirement is represented in the completion inventory;
3. every non-excluded requirement is `FULLY_VALIDATED` or in an explicit external
   approval/release state;
4. SR-0 through SR-10 implementation and qualification gates are resolved;
5. direct llama.cpp and Ollama Qwen3.8 paths are both accurately qualified or one
   is explicitly rejected with evidence;
6. no provider can approve, mutate, lower risk, expand scope, or retry blindly;
7. all deterministic tests, full discovery, GUI smoke, packaging, and install
   checks pass;
8. generated documentation is current, complete, linked, source-bound, and byte
   reproducible;
9. all benchmark and release claims bind exact source/model/runtime hashes;
10. the release candidate has a rollback manifest;
11. exact-hash human approval is recorded where required;
12. GitHub `main` equals the approved merged commit;
13. the repository remains public under MIT; and
14. release artifacts and their hashes are publicly retrievable.

If any item is unverified, incomplete, stale, or supported only by indirect
evidence, the program remains incomplete.

## 18. Immediate Execution Sequence

The next implementation session should perform these steps in order:

1. create the P0 patch/archive recovery bundle;
2. create a clean worktree from `origin/main`;
3. integrate SR source and tests while manually resolving the five overlap files;
4. run the P1 focused gates;
5. generate the complete requirement inventory;
6. close SR-2A from current deterministic evidence and a new live provider run;
7. implement SR-3 through SR-8 before adding optional SR-9 adapters;
8. implement the direct llama.cpp/Qwen3.8 process provider;
9. integrate GUI projections and upstream visual/writing capabilities;
10. regenerate documentation only after source stabilization;
11. run P8 full qualification;
12. freeze, approve, merge, verify remote parity, tag, and release.

This order minimizes merge loss, prevents stale generated artifacts from
dominating integration, and keeps the highest-risk unfinished work—SR quality,
provider identity, hidden retry, and release evidence—on the critical path.
