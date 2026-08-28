# OIEC-STM-Agent Implementation Plan

The `ourd` package and legacy `ourd-agent` command remain compatibility
interfaces for the OURD semantic layer within OIEC-STM-Agent.

**Plan status:** Candidate implementation plan; not authority-approved, certified, or released  
**Plan date:** 2026-08-21, Australia/Brisbane  
**Target:** Bring the implementation into defensible correspondence with `README.md` while adding a bounded local Qwen3.8 provider path  
**Promotion state:** `false` until every phase-specific gate and final human approval is complete

## 1. Objective

Implement a compact coding agent in which the governance chain is enforced by
deterministic code rather than trusted model statements:

**HRTv1 → OURD → IURMv1.1.1 → EONv1 → Evidence Gate → Action → CFEL feedback**

Qwen may inspect, reason, propose governance records, author candidate patches,
generate tests, and analyze collisions. Qwen must not be the final authority for
scope, risk, evidence sufficiency, approval, certification, or release.

## 2. Verified Baseline

### 2.1 Source snapshot

This repository is not currently a Git checkout, so the plan binds its baseline
to filesystem SHA-256 hashes:

| File | SHA-256 |
| --- | --- |
| `README.md` | `b6e76c236600f1eadba31672fe5ac058d285dc3bb02cbce974687b4623f83a63` |
| `ourd_agent.py` | `9a4c0e5ada391fe8d4a3187727e26dc9a9f68a0aa0ea6aff4147d9616abe2968` |
| `pyproject.toml` | `5b6e51030afb0a67f1b428c1cd22a280b5f8f7f1fee6c921281b8a93525bb149` |
| `test_policy.py` | `6ecbad2d710c1f36afe239afda260e129c89a6a74dc48b3240b336357724c3c4` |

Before implementation begins, regenerate these hashes. If any hash differs,
record the new snapshot and review the delta before applying this plan.

### 2.2 Current validation

- `python3 -m py_compile ourd_agent.py test_policy.py` passes.
- `python3 test_policy.py` passes.
- The existing tests cover only workspace escape and a simple scope match.
- The `openai` package is not installed in the current Python environment, so a
  complete `OURDAgent` live run has not been executed in this repository.

### 2.3 Verified local-model profile

The requested label `Qwen3.8:16b` is unresolved. The verified local profile is:

| Field | Verified value |
| --- | --- |
| Ollama version | `0.32.14` |
| Model alias | `qwen3.8-27b-fast:latest` |
| Base model | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_S` |
| Alias size | approximately 13 GB as reported by `ollama list` |
| Context | `8192` |
| Draft prediction | `draft_num_predict 2` |
| Responses function call | Live initial tool call passed |
| Function-result round trip | Live non-stateful round trip passed |

Do not silently rename this model to `qwen3.8:16b`. If a separate 16B model is
intended, stop and verify its exact Ollama tag, model digest, quantization,
context, tool-call behavior, and residency before adding another profile.

## 3. Scope

### 3.1 Included

- Local Ollama and OpenAI-compatible Responses provider support.
- Deterministic authority, scope, risk, EON, evidence, and approval enforcement.
- Canonical path and command capability controls.
- Candidate patch preparation, exact-hash approval, atomic application, and
  rollback.
- Persistent, validated, append-only governance and execution evidence.
- CFEL collision records and bounded retry behavior.
- Tests that substantiate each material enforcement claim in `README.md`.
- Documentation for the verified Qwen3.8 profile and provider limits.

### 3.2 Excluded

- OS, container, network, seccomp, namespace, or hypervisor sandboxing.
- Autonomous certification, merging, pushing, deployment, or release.
- Writing canonical EON history without separate authority approval.
- Importing VisualGrammar2d as a runtime dependency.
- General-purpose arbitrary shell execution.
- Multi-agent consensus as a substitute for deterministic evidence.

## 4. Preserved Invariants

1. The human-authored authority boundary is never broadened by the model.
2. Model risk estimates are advisory; deterministic minimum risk always wins.
3. File and command mutations require a current, exact action identity.
4. Evidence and approval are bound to the exact candidate and source snapshot.
5. Unknown or uncovered evidence remains explicit and cannot become full approval.
6. `APPROVE_WITH_LIMITS` is executable only within machine-readable limits.
7. L2 approval presents the exact candidate diff, hash, commands, and rollback.
8. Internal state and evidence files cannot be mutated through model tools.
9. One transaction owns a target path set at a time.
10. A successful focused test does not erase unrelated failures or uncertainty.
11. Collision evidence remains append-only.
12. `--yolo` may skip an interactive prompt only where pre-authorized; it cannot
    disable policy, evidence, scope, hashes, or rollback.

## 5. Target Architecture

Implementation should proceed behind characterization tests, then extract the
current monolith into a small package without changing the CLI contract.

```text
ourd_agent.py                 compatibility launcher
ourd/
  __init__.py
  cli.py                      argument parsing and interactive entry point
  agent.py                    model/tool loop
  authority.py                human authority manifest and effective scope
  models.py                   typed governance/action/evidence records
  policy.py                   deterministic risk and capability decisions
  workspace.py                canonical path and repository operations
  actions.py                  action identity, candidate, gate, transaction
  executor.py                 atomic apply, commands, verification, rollback
  persistence.py              schema validation and append-only event storage
  cfel.py                     collision records and retry constraints
  providers/
    base.py                   provider interface
    openai_responses.py       OpenAI and Ollama Responses implementation
tests/
  test_authority.py
  test_workspace.py
  test_policy.py
  test_actions.py
  test_executor.py
  test_persistence.py
  test_provider.py
  test_agent_loop.py
```

The package extraction is an L2 structural change. Do not begin it until Phase
0 characterization tests pass against the existing monolith.

## 6. Work Packages

## Phase 0 — Characterize and Freeze Existing Behavior

**Purpose:** Establish a deterministic baseline before structural changes.

### Changes

- Move existing smoke assertions into `unittest` tests without changing runtime
  behavior.
- Add tests for current CLI parsing, tool schemas, governance establishment,
  EON creation, evidence submission, and simple read operations.
- Add a baseline snapshot command that records file hashes, Python version, and
  dependency availability under `.ourd-agent/evidence/` only during explicit
  validation runs.
- Document known unsafe behavior as expected failures rather than fixing it in
  the same test change.

### Required evidence

- Existing positive behavior passes.
- Each known security gap has a failing or expected-failure test.
- No production behavior changes.

### Exit gate

- Baseline tests pass from a clean temporary workspace.
- Test output and source hashes are saved as candidate evidence.

## Phase 1 — Provider Boundary and Qwen3.8 Profile

**Purpose:** Make model transport explicit, testable, and independent of
VisualGrammar2d-specific wrappers.

### Changes

- Add a `ModelProvider` interface with a non-stateful Responses implementation.
- Preserve OpenAI support and add explicit Ollama configuration:
  - `OURD_BASE_URL` or `OPENAI_BASE_URL`;
  - `OURD_API_KEY` or `OPENAI_API_KEY`;
  - `OURD_MODEL`;
  - `OURD_REASONING_EFFORT`;
  - `OURD_MAX_OUTPUT_TOKENS`;
  - `OURD_CONTEXT_BUDGET`;
  - request timeout and retry limits.
- Require an explicit local profile rather than guessing that every Qwen tag is
  an Ollama tag.
- Record provider, model tag, model digest when available, endpoint type,
  context budget, reasoning setting, and generation limits in every run header.
- Add a preflight health check that distinguishes:
  - dependency missing;
  - endpoint unreachable;
  - model absent;
  - context overflow;
  - malformed tool call;
  - provider protocol incompatibility.
- Keep Qwen tool-loop input below the configured context. For the verified 8K
  profile, target no more than about 6K input tokens and reserve capacity for
  output and tool results.
- Do not import `../VisualGrammar2d/qwen_cli.py`. Its project-study, timeout, and
  error-handling patterns may be adapted with attribution in development notes,
  but its character-response schema must not enter this agent.

### Tests

- Fake-provider initial response, function call, tool result, and final response.
- Missing API key and local ignored-key handling.
- Context-budget truncation/refusal.
- Invalid function arguments.
- Timeout and endpoint-unreachable reporting.
- Optional live Ollama smoke, disabled by default.

### Exit gate

- Unit tests pass without network access.
- Live Qwen read-only tool call and tool-result round trip pass when explicitly
  enabled.
- Provider failures do not mutate the workspace.

## Phase 2 — External Authority and Deterministic Risk Floors

**Purpose:** Prevent the acting model from granting itself authority.

### Changes

- Add a human-authored `AuthorityManifest` accepted by `--authority FILE`.
- Define a versioned JSON schema containing:
  - task identifier and goal;
  - source snapshot hash;
  - allowed and forbidden canonical paths;
  - permitted read operations;
  - permitted command capabilities;
  - maximum automatic risk;
  - mandatory tests and evidence;
  - whether L1 automatic application is allowed;
  - whether interactive L2 approval is allowed;
  - whether `--yolo` is allowed;
  - expiry and operator identity fields.
- Change `establish_governance` into a model proposal constrained by the
  authority manifest.
- Reject proposed scope broader than authority scope.
- Add deterministic minimum risk:
  - read-only tools: L0;
  - `write_file` and `replace_text`: at least L1;
  - structural, broad, configuration, dependency, or difficult-to-reverse
    changes: at least L2;
  - command risk: derived from exact capability rules.
- Effective risk is `max(model_risk, deterministic_minimum_risk)`.

### Tests

- Model proposes `allowed_paths=[]`; authority remains narrow.
- Model labels a write L0; effective risk becomes L1.
- Model labels a structural change L1; effective risk becomes L2.
- Expired or source-mismatched authority is rejected.
- `--yolo` is rejected unless explicitly enabled by authority.

### Exit gate

- No mutation can be authorized solely by model-supplied governance or risk.
- Existing read-only workflows remain usable without mutation authority.

## Phase 3 — Canonical Paths and Command Capabilities

**Purpose:** Replace lexical and executable-name heuristics with fail-closed
capability checks.

### Changes

- Resolve every requested path to a canonical workspace-relative path before
  EON, authority, or scope matching.
- Reject path traversal, symlink escape, invalid encodings, absolute paths, and
  ambiguous path aliases.
- Reserve `.ourd-agent/` as an internal namespace inaccessible to model file
  mutation tools.
- Replace `read_only_heads` with explicit command capabilities such as:
  - `git.status`;
  - `git.diff`;
  - `rg.search`;
  - `python.test_module`;
  - `ctest.run`;
  - `compiler.syntax_check`.
- Validate every argument. Do not infer safety from the executable name alone.
- Default-deny unrecognized executables, flags, subcommands, response files,
  environment assignments, output paths, and command chaining.
- Use a sanitized child environment rather than copying every parent variable.
- Keep `shell=False` and argv-based execution.

### Adversarial tests

- `src/../secret.txt` under an `src/*` scope.
- Symlink from an allowed directory to an excluded directory.
- `python -c` file mutation.
- `sed -i` mutation.
- `find -delete` and `find -exec`.
- `git add`, `git restore`, `git rm`, `git push`.
- Compiler or build-system output outside authorized paths.
- Access to `.ourd-agent/state.json` through model tools.

### Exit gate

- Every adversarial mutation is blocked before process execution or file write.
- Permitted read and test capabilities still function.

## Phase 4 — Exact EON Identity and Evidence Decisions

**Purpose:** Bind authorization to the exact proposed action and evidence.

### Changes

- Canonically serialize EON actions and assign `action_id = sha256(canonical_json)`.
- Include in the action identity:
  - authority manifest hash;
  - source snapshot hash;
  - operation type;
  - canonical target paths;
  - candidate content or patch hash;
  - command argv and environment capability IDs;
  - preconditions and postconditions;
  - preserved invariants;
  - required tests;
  - effective risk;
  - expiry and use count.
- Separate model evidence proposals from deterministic `GateDecision` records.
- Bind evidence to artifact hashes and action ID.
- Replace free-text `approval_scope` with machine-readable limits.
- Reject `APPROVE` with uncovered evidence.
- Permit `APPROVE_WITH_LIMITS` only when each operation is mechanically inside
  the declared limits.
- Consume or increment the action use count after each authorized operation.
- Refuse stale actions after any relevant source change.

### Tests

- Same summary, different content produces a different action ID.
- Changed source invalidates the gate.
- Approval for one file cannot authorize another file.
- Approval for one command cannot authorize altered arguments.
- Limited approval blocks operations beyond its limits.
- Exhausted or expired action is rejected.

### Exit gate

- No gate can authorize a candidate other than the exact candidate it reviewed.

## Phase 5 — Candidate Transactions, Atomic Apply, and Rollback

**Purpose:** Stop writing model output directly into the working tree.

### Changes

- Replace direct writes with a two-stage protocol:
  1. prepare candidate artifact;
  2. apply authorized transaction.
- Store candidate patches and complete replacement content under an internal
  transaction directory not writable through model tools.
- Produce a review summary containing:
  - transaction ID;
  - action ID;
  - source snapshot;
  - target paths;
  - unified diff;
  - candidate hash;
  - required commands and tests;
  - expected postconditions;
  - rollback manifest.
- For L2, display the exact summary and require interactive approval bound to
  the transaction hash.
- Apply writes atomically using temporary files and same-filesystem replacement.
- Capture original bytes, mode, existence, and hash for rollback.
- Refuse partial application unless an explicit multi-file transaction supports
  complete rollback.
- Verify post-write hashes before commands execute.
- Implement and test rollback rather than merely printing a rollback command.

### Tests

- New file, replacement, and bounded text change transactions.
- Mid-transaction failure restores all original files.
- Candidate hash mismatch blocks apply.
- Source drift blocks apply.
- L2 denial leaves the workspace unchanged.
- Rollback restores exact bytes and modes.

### Exit gate

- Every mutation has a prepared candidate, exact approval record where needed,
  atomic application evidence, and tested rollback.

## Phase 6 — Persistent State, Provenance, and Conflict Detection

**Purpose:** Make persisted state usable and trustworthy across processes.

### Changes

- Add versioned state schemas and explicit load/validation at startup.
- Store immutable events in append-only JSONL with event IDs, timestamps,
  previous-event hash, payload hash, run ID, action ID, and transaction ID.
- Treat `state.json` as a rebuildable projection of the append-only log.
- Write state atomically and use a workspace lock to enforce one writer.
- Record model request metadata without recording secrets.
- Redact sensitive environment values and configurable secret patterns from
  traces and command output.
- Detect conflicting active actions, source drift, expired authority, incomplete
  transactions, and unresolved rollback on startup.
- Preserve unknown or contradictory historical evidence instead of overwriting it.

### Tests

- Restart restores valid governance and pending transaction state.
- Corrupt projection rebuilds from valid event history.
- Broken event hash chain fails closed.
- Concurrent writer is rejected.
- Secrets are absent from traces.
- Unresolved transaction blocks unrelated mutation until reconciled.

### Exit gate

- State persistence means validated restoration, not only writing a JSON file.

## Phase 7 — CFEL Collision Feedback and Bounded Recovery

**Purpose:** Turn failures into explicit evidence without uncontrolled retries.

### Changes

- Add a typed collision record containing:
  - expected outcome;
  - observed outcome;
  - interacting objects and boundary;
  - active IURM dimension;
  - frozen dimensions;
  - raw evidence references;
  - proposed correction;
  - falsifier;
  - retry count and disposition.
- Require a materially revised action or evidence set after a significant failure.
- Block blind repetition of the same action ID.
- Cap automatic retries by authority and risk.
- Treat permission denials, context overflow, malformed tool calls, test failures,
  source drift, and rollback activation as collision evidence.
- Keep model diagnosis advisory and preserve raw command/test output separately.

### Tests

- Repeating an unchanged failed action is blocked.
- Revised action with new evidence receives a new ID.
- Critical invariant failure overrides passing nominal tests.
- Context overflow reduces or reselects context rather than increasing beyond
  the verified profile silently.

### Exit gate

- Every retry is traceable to new evidence or a changed candidate.

## Phase 8 — Documentation, Claim Tests, and Release Candidate

**Purpose:** Make every README enforcement claim demonstrably true or qualify it.

### Changes

- Update `README.md` with:
  - exact local Ollama setup;
  - the required ignored local API key;
  - verified and optional model profiles;
  - authority-manifest workflow;
  - candidate, approval, apply, verification, and rollback lifecycle;
  - limits of process-level safety;
  - context and reasoning controls;
  - evidence and trace locations;
  - recovery from incomplete transactions.
- Add a claim-to-test matrix.
- Add a deterministic validation command that runs unit, integration, and
  optional live-model tests separately.
- Keep live-model quality evidence separate from deterministic policy evidence.

### Exit gate

- Every material README claim maps to at least one deterministic test or is
  explicitly described as a limitation.
- Full test output, source hashes, model profile, candidate hash, rollback test,
  and unresolved risks are presented for human review.
- Promotion remains false until explicit approval of the exact release candidate.

## 7. README Claim-to-Test Matrix

| README claim | Required proof |
| --- | --- |
| Mutations are locked before governance | Write and command mutation tests without authority/governance |
| Governance records HRT/OURD/IURM fields | Schema and persistence round-trip tests |
| Every coherent mutation requires EON | Direct write, replace, and command refusal tests |
| L1/L2 require evidence | Deterministic risk-floor and missing-gate tests |
| `APPROVE` rejects uncovered evidence | Gate-decision unit test |
| Writes obey OURD scope and EON targets | Canonical traversal, symlink, and wrong-target tests |
| L2 requires human approval unless authorized skip | Denial, approval-hash, and unauthorized-`--yolo` tests |
| Commands use argv and not a shell | Executor construction and metacharacter tests |
| Destructive commands are blocked | Capability adversarial suite |
| Tool calls/results are traced | Event-log completeness and redaction tests |
| Governance/evidence state is stored | Restart, schema, hash-chain, and projection-rebuild tests |
| CFEL incorporates failure feedback | Collision and changed-action retry tests |

## 8. Qwen3.8 Operating Protocol

### Before a Qwen-assisted run

1. Revalidate `ollama --version`.
2. Revalidate `ollama show qwen3.8-27b-fast` and record the digest/profile.
3. Confirm no unintended competing model is resident with `ollama ps`.
4. Regenerate target source hashes.
5. Load a human-approved authority manifest.
6. Set an input and output budget compatible with the verified 8K context.
7. Use a disposable copy or transaction staging area for implementation work.

### Permitted Qwen roles

- Read-only repository inspection.
- HRT/OURD/IURM proposal generation.
- EON candidate generation.
- Candidate patch and test generation.
- Counterexample and boundary-case suggestions.
- CFEL collision diagnosis.
- Candidate report drafting.

### Prohibited Qwen authority

- Broadening allowed scope.
- Lowering deterministic risk.
- Declaring its own evidence sufficient.
- Approving its own L2 candidate.
- Altering approval, state, evidence, or rollback artifacts.
- Certifying, releasing, committing, pushing, or deploying without explicit
  external authority.

## 9. Validation Order

Run validation from narrowest to broadest:

1. Static syntax checks.
2. Focused unit tests for the changed component.
3. Policy adversarial tests.
4. Transaction and rollback tests in a temporary workspace.
5. Persistence restart tests.
6. Complete deterministic test suite.
7. Optional local Qwen read-only tool-loop smoke.
8. Optional local Qwen candidate transaction in a disposable workspace.
9. Source, evidence, candidate, and rollback hash review.
10. Explicit human release-candidate decision.

Live Qwen success cannot override deterministic test failure. Deterministic
success cannot establish model quality beyond the tested tasks.

## 10. Rollback Strategy

- Before each phase, save the exact source snapshot and validation output.
- Keep each phase in a separate candidate patch with disjoint acceptance evidence.
- Do not combine provider integration, authority changes, executor changes, and
  package extraction into one unreviewable patch.
- Preserve the original four-file implementation until the extracted package
  passes behavioral parity tests.
- For every applied transaction, retain original file bytes and metadata until
  postconditions and broader tests pass.
- A rollback is complete only when restored file hashes match the recorded
  pre-transaction hashes and the baseline tests pass.

## 11. Completion Criteria

Implementation is complete only when all of the following are true:

- The exact source snapshot and authority manifest are known.
- All model actions are constrained by external authority.
- Mutation risk has deterministic floors.
- Paths and commands are checked canonically and fail closed.
- EON, evidence, approval, and apply records share an exact action identity.
- L2 approval is bound to an exact candidate hash and rollback.
- Writes are staged, atomic, verified, and reversible.
- Persisted state loads, validates, and detects conflicts.
- CFEL retries require changed evidence or action.
- Every material README enforcement claim has deterministic proof.
- Local Qwen tests are reported separately from policy certification.
- No unresolved critical or high-severity policy gap remains.
- A human explicitly approves the exact final candidate and evidence bundle.

Until then, the correct advisory state is:

`candidate_implementation_pending_deterministic_validation_and_human_approval`

## 12. Implementation Evidence Status

**Implementation date:** 2026-08-21, Australia/Brisbane  
**Technical candidate state:** implemented; final deterministic and live reports
are generated by `tools/validate.py`  
**Promotion state:** `false`; explicit human approval remains external

The implementation now includes the extracted `ourd/` package, compatibility
launcher, external exact-snapshot authority, deterministic risk floors,
canonical path and command enforcement, exact EON command argv identity,
grounded evidence decisions, staged atomic transactions, tested rollback,
hash-chained lineage events, projection recovery, CFEL retry constraints, direct
local Ollama Responses transport, strict tool schemas, and the claim-oriented
test suite under `tests/`.

This appendix records candidate implementation progress only. It does not
rewrite the verified baseline, certify the implementation, or satisfy the final
human approval gate. The exact source hashes, model digest, validation output,
and unresolved limitations must be taken from the final generated evidence
report and reviewed together as one release candidate.
