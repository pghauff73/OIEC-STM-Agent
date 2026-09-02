# OURD Summarization, Governance, and Reasoning Recovery Implementation Plan

**Plan version:** 1.0  
**Plan date:** 2026-08-30, Australia/Brisbane  
**Status:** Candidate implementation plan; not implementation authority, certification, or release approval  
**Primary incident:** A read-only Markdown summarization request was misclassified as certified reasoning, selected `run_super_reasoning` before governance existed, stopped at `NO_VERIFIED_PROGRESS`, and returned an evidence-only failure report instead of summaries  

## 1. Executive Decision

Fix the failure as an orchestration and evidence-projection problem rather than
weakening the governance gate.

The corrected behavior will be:

```text
"Summarise each /docs/ markdown file"
  -> SUMMARIZE intent
  -> exact Markdown corpus manifest
  -> bounded read-only tool surface
  -> complete per-file content coverage
  -> one source-bound summary artifact per file
  -> corpus coverage validation
  -> concise final answer
```

Certified super reasoning remains governed:

```text
explicit certified reasoning request
  -> inspect relevant evidence
  -> establish bounded governance within external authority
  -> expose run_super_reasoning only after its preconditions are true
  -> produce a source- and snapshot-bound reasoning certificate
```

A failed recoverable tool precondition will become deterministic negative
evidence that permits one corrective transition. It will not immediately force
terminal synthesis, and repeating the unchanged failure will still stop safely.

The GUI chat will show concise milestones. Full tool arguments, outputs,
collisions, coverage reports, and terminal diagnostics remain available in the
activity inspector and evidence projections.

## 2. Verified Failure Chain

The current source establishes the following sequence:

1. `ourd/interaction/interpreter.py` has no `summarise` or `summarize` intent
   pattern.
2. An unmatched request defaults to `REASON`.
3. `REASON` requests both `reasoned_answer` and `reasoning_certificate`.
4. The route still targets `agent.read_only`, so no mutation authority is
   created.
5. `OURDAgent.tool_specs()` advertises `run_super_reasoning` whenever the
   feature flag is enabled, regardless of governance state.
6. `run_super_reasoning()` calls `require_governance()` and fails when no
   governance record exists.
7. The error text says `mutation locked` even though the failed operation is a
   read-only reasoning operation that produces a certificate.
8. The failed call does not create evidence, control state, or a
   progress-relevant collision.
9. `LoopProgressController` classifies the step as `NO_VERIFIED_PROGRESS` and
   stops immediately.
10. Terminal synthesis retains only a bounded subset of recent tool
    observations.
11. Active evidence restoration is hard-coded to selected Python files and
    excludes Markdown documents.
12. Terminal projection places model-proposed tool arguments beside verified
    outputs inside a block labelled as system terminal evidence.
13. The final response therefore cannot summarize the complete corpus and may
    overinterpret model-generated hypotheses as runtime facts.

The plan addresses every link in this chain. A patch that fixes only the error
message or only adds `summarise` to one regex is incomplete.

## 3. Objectives

1. Add a first-class `SUMMARIZE` intent for content summarization.
2. Support British and US spelling and common summary language.
3. Recognize an exact repository-local Markdown corpus without relying on model
   inference from filenames.
4. Pass a restrictive, signed turn-execution policy from ICPI to the agent.
5. Advertise only tools whose deterministic preconditions currently hold.
6. Preserve the requirement that certified super reasoning needs established
   governance.
7. Return structured, actionable, provenance-bearing tool failures.
8. Permit one bounded correction after a new recoverable precondition failure.
9. Stop unchanged repeated failures without creating artificial progress.
10. Prove exact corpus coverage before claiming that every file was summarized.
11. Preserve per-file summary artifacts across context reduction.
12. Separate verified observations from model-proposed arguments in terminal
    projections.
13. Restore active evidence according to current task relevance and media type,
    not hard-coded source extensions.
14. Keep chat activity concise while retaining full inspectable evidence.
15. Preserve read-only authority, exact-snapshot mutation authority, EON,
    evidence gates, approval, apply, verification, rollback, and CFEL behavior.

## 4. Non-Goals

- Do not remove governance from `run_super_reasoning`.
- Do not make a reasoning certificate mandatory for ordinary summarization.
- Do not auto-create mutation authority from natural language.
- Do not let `InteractionRoute` or `TurnExecutionPolicy` broaden authority.
- Do not treat model-generated summaries as system-verified facts.
- Do not persist unrestricted copies of every repository file merely to support
  context recovery.
- Do not allow a recoverable failure to be retried indefinitely.
- Do not weaken `CYCLE_STOP`, context budgets, source-snapshot checks, or
  transaction safety.
- Do not replace the current `@file[...]`, `@folder[...]`, and `@path[...]`
  syntax.
- Do not rewrite unrelated EGCF, GUI, generated-document, or formal-writing
  functionality.

## 5. Non-Negotiable Invariants

### 5.1 Authority monotonicity

```text
TurnExecutionPolicy <= AgentAuthority
Governance.allowed_paths <= AgentAuthority.allowed_paths
GUIAuthority <= AgentAuthority
```

A turn policy may hide tools or narrow paths. It may not grant a capability,
path, risk level, approval, or execution permission.

### 5.2 Certified reasoning preconditions

`run_super_reasoning` remains unavailable unless all of the following are true:

```text
super_reasoning_enabled
governance.established
governance.authority_hash == authority.authority_hash
authority is unexpired
pending_action is absent
current source snapshot is available
```

The method repeats these checks at dispatch time even when tool advertisement
already filtered it out.

### 5.3 Summary coverage

The phrase “each file,” “all files,” or an equivalent whole-corpus request may
be satisfied only when:

```text
manifest_expected_paths == completed_summary_paths
and no expected path is unresolved
and every completed summary has complete source coverage
and every summary is bound to the manifest source snapshot and file hash
```

Otherwise the response must say `PARTIAL` and list exact missing or truncated
files.

### 5.4 Epistemic separation

The runtime must distinguish:

```text
SYSTEM_VERIFIED_TOOL_OBSERVATION
SYSTEM_VERIFIED_COVERAGE
SYSTEM_VERIFIED_POLICY_FAILURE
MODEL_PROPOSED_TOOL_ARGUMENTS
MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE
MODEL_INTERPRETATION_UNVERIFIED
```

Model-generated hypotheses, arguments, summaries, and explanations remain
model artifacts even when source-bound.

### 5.5 Bounded recovery

A new recoverable precondition failure may justify one corrective step because
it is new deterministic negative evidence. The identical failure under the
same state and arguments must not create a new collision or new progress.

### 5.6 Context preservation

Context reduction may compact raw read outputs only after an evidence-bound
replacement preserves the task-relevant meaning required for final synthesis.
For corpus summarization, that replacement is a validated per-file summary
artifact plus source coverage, hashes, and bounded source excerpts.

### 5.7 Concise chat, complete evidence

Reducing the chat display must never delete, overwrite, or omit canonical
events or evidence. The chat surface is a projection; the activity inspector
and event/evidence stores retain the full detail permitted by existing
retention rules.

## 6. Corrected Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│ ICPI input                                                         │
│ natural language | explicit @folder | slash command                │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│ Interaction interpretation                                        │
│ SUMMARIZE | INSPECT | REASON | ...                                 │
│ exact references | requested outputs | ambiguity | risk            │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│ TurnExecutionPolicy compiler                                      │
│ tool classes | target paths | certificate requirement | signature │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ restrictive only
┌──────────────────────────────▼─────────────────────────────────────┐
│ ProductionOURDAgent                                               │
│ state-aware tool advertisement | runtime precondition checks       │
└──────────────┬───────────────────────────────┬─────────────────────┘
               │                               │
┌──────────────▼───────────────┐  ┌────────────▼────────────────────┐
│ Corpus summary path         │  │ Certified reasoning path        │
│ manifest -> reads ->        │  │ reads -> governance -> SR       │
│ per-file summaries ->       │  │ -> certificate                  │
│ coverage report             │  │                                 │
└──────────────┬───────────────┘  └────────────┬────────────────────┘
               │                               │
┌──────────────▼───────────────────────────────▼────────────────────┐
│ Progress and recovery controller                                  │
│ new evidence | new collision | bounded control | cycle stop       │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│ Output projections                                                 │
│ concise chat | activity details | coverage | terminal evidence     │
└────────────────────────────────────────────────────────────────────┘
```

## 7. New and Extended Data Contracts

### 7.1 `SUMMARIZE` intent

Extend `INTENT_MODES` and routing with:

```text
mode: SUMMARIZE
target: agent.read_only
requested_outputs:
  - summary
  - evidence
  - corpus_coverage
proposed_risk: L0
requires_confirmation: false unless references are unresolved or ambiguous
```

Initial patterns should include:

```text
summarise
summarize
summarised
summarized
summarising
summarizing
summary of
give an overview of
digest
abstract each
```

Intent precedence must ensure that “write a summary to `@path[...]`” remains a
mutating `WRITE` request, while “summarise `@folder[docs]`” remains read-only.

### 7.2 `TurnExecutionPolicy`

Add an immutable, non-authoritative policy compiled from the exact route and
context envelope:

```text
schema_version
policy_id
route_id
route_signature
source_snapshot_hash
intent_mode
route_target
target_paths
allowed_tool_groups
requires_reasoning_certificate
allows_candidate_preparation
allows_action_tools
corpus_request
context_envelope_signature
signature
authoritative: false
```

Tool groups:

```text
repository_discovery
workspace_read
corpus_read
hypothesis_control
governance_proposal
certified_reasoning
candidate_preparation
eon_proposal
evidence_gate
transaction_apply
verification
```

Examples:

```text
SUMMARIZE:
  repository_discovery, workspace_read, corpus_read

REASON with certificate:
  repository_discovery, workspace_read, hypothesis_control,
  governance_proposal, certified_reasoning

WRITE:
  existing governed candidate tool groups, further narrowed by authority
```

### 7.3 `ToolAvailability`

Add a deterministic internal projection:

```text
tool_name
available
reason_code
required_state
current_state_signature
authority_hash
governance_signature
turn_policy_signature
```

The projection decides advertisement only. Dispatch performs the authoritative
check again.

Reason codes include:

```text
AVAILABLE
FEATURE_DISABLED
TURN_POLICY_EXCLUDES_TOOL
GOVERNANCE_REQUIRED
GOVERNANCE_AUTHORITY_MISMATCH
AUTHORITY_EXPIRED
PENDING_ACTION_CONFLICT
READ_CAPABILITY_REQUIRED
MUTATION_AUTHORITY_REQUIRED
```

### 7.4 `ToolFailureEnvelope`

Normalize tool failures:

```text
ok: false
error_code
message
failure_class
recoverable
required_transition
tool_name
call_fingerprint
state_signature
collision_id
retry_disposition
```

Failure classes:

```text
PRECONDITION
POLICY
INPUT
NOT_FOUND
TRANSIENT
PROTOCOL
TERMINAL
```

Example:

```json
{
  "ok": false,
  "error_code": "GOVERNANCE_REQUIRED",
  "message": "Certified super reasoning requires bounded governance under the current authority.",
  "failure_class": "PRECONDITION",
  "recoverable": true,
  "required_transition": "establish_governance",
  "tool_name": "run_super_reasoning",
  "retry_disposition": "retry only after governance state changes"
}
```

### 7.5 `CorpusManifest`

```text
schema_version
manifest_id
root_path
include_patterns
exclude_patterns
source_snapshot_hash
files:
  path
  media_type
  byte_size
  line_count
  content_sha256
manifest_signature
```

The manifest is deterministic, sorted by canonical path, and excludes
`.ourd-agent/**` plus authority-forbidden paths.

### 7.6 `DocumentReadCoverage`

```text
path
content_sha256
line_count
covered_line_ranges
uncovered_line_ranges
read_evidence_ids
coverage_complete
coverage_signature
```

Line ranges must be merged deterministically. Duplicate reads do not create
additional coverage or progress.

### 7.7 `DocumentSummaryArtifact`

```text
schema_version
summary_id
manifest_id
path
content_sha256
source_snapshot_hash
summary_text
summary_sha256
source_read_evidence_ids
coverage_signature
coverage_complete
model_identity
prompt_signature
epistemic_status: MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE
signature
```

The runtime verifies identity and coverage. It does not certify the semantic
truth or completeness of the prose beyond the declared source coverage.

### 7.8 `CorpusSummaryReport`

```text
manifest_id
expected_paths
summarized_paths
missing_paths
partial_paths
stale_paths
summary_ids
coverage_status: COMPLETE | PARTIAL | STALE
source_snapshot_hash
signature
```

### 7.9 `TerminalEvidenceProjection`

Replace the mixed observation structure with explicit categories:

```text
verified_tool_observations
verified_policy_failures
model_proposed_tool_calls
restored_source_excerpts
document_summary_artifacts
corpus_coverage
material_limits
projection_signature
```

Tool arguments must never appear inside `verified_tool_observations`.

## 8. Repository Change Map

| File or area | Planned responsibility |
| --- | --- |
| `ourd/interaction/models.py` | Add `SUMMARIZE`, requested-output types, and `TurnExecutionPolicy` |
| `ourd/interaction/interpreter.py` | Add summary language, precedence rules, and corpus semantics |
| `ourd/interaction/context.py` | Resolve explicit corpus references and bounded repository-root shorthand |
| `ourd/interaction/routing.py` | Route `SUMMARIZE` to `agent.read_only` |
| `ourd/interaction/envelope.py` | Include summary operation, corpus request, and turn-policy signature |
| `ourd/interaction/session.py` | Add `/scope` and `/summarize` local/route behavior if adopted |
| `ourd_gui/controller.py` | Compile and pass the exact turn policy to the gateway |
| `ourd_gui/core_gateway.py` | Pass the restrictive policy into the short-lived production agent |
| `ourd/agent.py` | State-aware tool availability, structured failures, corpus tools, summary artifacts |
| `ourd/production_agent.py` | Mode-aware tools, bounded failure recovery, task-relevant terminal projection |
| `ourd/loop_control.py` | Count new deterministic policy collisions while rejecting duplicates |
| `ourd/context_budget.py` | Preserve source-bound summaries and corpus coverage during reduction |
| `ourd/models.py` | Persist versioned summary, coverage, and failure records if RuntimeState ownership is chosen |
| `ourd/persistence.py` | Schema migration and replay validation for new records |
| `ourd_gui/activity_projection.py` | Aggregate concise corpus progress and structured failure messages |
| `ourd_gui/views/activity.py` or current owner | Display full details without expanding main chat |
| `README.md` | Explain read-only scope, governance, certified reasoning, and summary behavior |
| `docs/OURD_AGENT_GUI.md` | Document ICPI summary and scope UX |
| `docs/PRODUCTION_EPISTEMIC_BOUNDARY.md` | Document model summary versus verified coverage |
| `tests/interaction/` | Intent, route, context, envelope, and turn-policy coverage |
| `tests/test_reads.py` | Corpus inventory, batching, hashes, and line coverage |
| `tests/test_reasoning.py` | State-aware super-reasoning exposure and governance transitions |
| `tests/test_provider.py` | Multi-step correction behavior and tool-surface updates |
| `tests/test_context_budget.py` | Summary preservation across compaction |
| `tests/gui/` | Concise activity and full detail projection |

## 9. Multi-Phase Implementation Roadmap

### Phase 0: Freeze the Incident and Compatibility Baseline

**Dependencies:** None.

**Work:**

1. Record the current source snapshot and unrelated dirty-worktree boundary.
2. Add a deterministic reproduction fixture for:

   ```text
   Summarise each /docs/ markdown file.
   ```

3. Assert current behavior in an incident test without making it a permanent
   compatibility requirement:
   - mode becomes `REASON`;
   - requested outputs include `reasoning_certificate`;
   - governance is absent;
   - `run_super_reasoning` is advertised;
   - direct dispatch returns the governance error.
4. Record public tool names, interaction modes, event schemas, persistence
   schema, and current activity projection behavior.
5. Identify all tests whose assertions intentionally change.

**Evidence:**

- incident reproduction output;
- source snapshot manifest;
- API and schema inventory;
- affected-test inventory;
- dirty-state boundary.

**Pass gate:**

```text
the complete failure chain is reproduced deterministically before correction
```

### Phase 1: Add First-Class `SUMMARIZE` Intent

**Dependencies:** Phase 0.

**Work:**

1. Add `SUMMARIZE` to `INTENT_MODES`.
2. Add summary patterns for British and US spellings.
3. Add requested outputs `summary`, `evidence`, and `corpus_coverage`.
4. Route `SUMMARIZE` to `agent.read_only`.
5. Define precedence between `SUMMARIZE`, `WRITE`, `EXPORT`, and `EXPLAIN`.
6. Treat “write/save/export a summary” as mutating or export behavior according
   to the existing deterministic risk rules.
7. Preserve default `REASON` for genuinely unclassified reasoning requests.
8. Update ICPI previews to show:

   ```text
   SUMMARIZE -> agent.read_only -> L0
   ```

**Tests:**

- `summarise each file`;
- `summarize every document`;
- `give an overview of these files`;
- `write a summary to @path[summary.md]`;
- `export the summary`;
- no regression for inspect, explain, compare, plan, propose, write, test,
  execute, recover, and export.

**Pass gate:**

```text
ordinary content summarization never requests a reasoning certificate
```

### Phase 2: Resolve Exact Corpus Scope

**Dependencies:** Phase 1.

**Work:**

1. Prefer explicit syntax:

   ```text
   @folder[docs]
   @file[docs/WRITING_MODE.md]
   ```

2. Add bounded recognition for repository-root shorthand such as `/docs/`
   only when:
   - it occurs inside a natural-language request rather than as a slash command;
   - the normalized workspace-relative path exists;
   - it remains inside the workspace;
   - authority permits it.
3. Do not reinterpret arbitrary absolute paths outside the workspace.
4. Compile corpus filters from phrases such as `markdown files`, `*.md`, or
   `each Markdown file`.
5. Record whether path and pattern were explicit or inferred.
6. Require confirmation when inferred path meaning remains ambiguous.
7. Bind resolved corpus scope to the exact context-envelope snapshot.

**Tests:**

- `@folder[docs]`;
- `docs/`;
- `/docs/` repository shorthand;
- real absolute path outside workspace;
- nonexistent folder;
- symlink escape;
- `docs/**/*.md` nested corpus;
- non-Markdown files excluded;
- path drift before invocation.

**Pass gate:**

```text
whole-corpus requests produce an exact, authority-bounded source set before model execution
```

### Phase 3: Compile and Propagate `TurnExecutionPolicy`

**Dependencies:** Phases 1-2.

**Work:**

1. Add the immutable policy contract from Section 7.2.
2. Compile it from `InteractionRoute` and `InteractionContextEnvelope`.
3. Bind it to route, snapshot, context, targets, and requested outputs.
4. Pass it through:

   ```text
   GUI controller
     -> CoreGateway.chat_turn
     -> ProductionOURDAgent.run_task
   ```

5. Preserve compatibility for direct CLI and API callers that have no ICPI
   route by deriving a conservative default policy.
6. Validate `TurnExecutionPolicy <= AuthorityManifest` before every model call.
7. Include the policy signature and allowed tool groups in trace metadata.
8. Include the exact policy in context-budget identity.

**Tests:**

- deterministic policy signature;
- route/context mismatch rejection;
- stale snapshot rejection;
- policy cannot add a path;
- policy cannot add mutation tools;
- GUI and CLI policy propagation;
- direct API compatibility.

**Pass gate:**

```text
the model receives only a restrictive tool policy derived from the exact current request
```

### Phase 4: Make Tool Advertisement State-Aware

**Dependencies:** Phase 3.

**Work:**

1. Add `_tool_availability(tool_name, turn_policy)`.
2. Filter tool specifications by both turn policy and live runtime state.
3. Advertise `establish_governance` only when the turn policy permits a
   governance proposal.
4. Advertise `run_super_reasoning` only when all Section 5.2 preconditions hold.
5. Hide candidate, EON, gate, apply, and command tools from `SUMMARIZE` turns.
6. Keep dispatch-time checks authoritative.
7. Add a bounded instruction projection that states which important tools are
   unavailable and which state transition unlocks them without exposing hidden
   implementation details.
8. Recompute tool specs at every model step, relying on the existing loop
   behavior so successful governance unlocks super reasoning on the next step.

**Tests:**

- summary tool surface contains read/corpus tools only;
- initial certified-reasoning surface contains governance but not super
  reasoning;
- successful governance exposes super reasoning on the next model request;
- authority mismatch hides it;
- expired authority hides it;
- pending EON action hides it;
- dispatch still rejects manually injected unavailable calls.

**Pass gate:**

```text
no provider request advertises a tool whose deterministic preconditions are false
```

### Phase 5: Add Structured Tool Failures

**Dependencies:** Phase 4.

**Work:**

1. Add stable error codes and failure classes.
2. Replace the super-reasoning error with a reasoning-specific message rather
   than `mutation locked`.
3. Preserve mutation-specific errors for actual mutation paths.
4. Return `required_transition` only when a deterministic correction exists.
5. Compute failure identity from tool name, canonical arguments, authority,
   governance, pending action, turn policy, and source snapshot.
6. Record one collision for each new deterministic failure identity.
7. Avoid persisting raw sensitive arguments in user-visible messages.
8. Project structured failure fields into the GUI activity stream.

**Tests:**

- governance-required failure;
- authority-expired failure;
- turn-policy-excluded tool;
- invalid arguments;
- unknown source path;
- identical failure deduplication;
- state change creates a new identity only when material.

**Pass gate:**

```text
every policy failure is actionable, typed, deterministic, and provenance-bound
```

### Phase 6: Permit One Bounded Corrective Transition

**Dependencies:** Phase 5.

**Work:**

1. Include newly recorded policy collisions in the verified projection.
2. Treat the first new recoverable precondition collision as negative epistemic
   evidence, permitting the next model step.
3. Do not count the same collision atom twice.
4. Block unchanged failed calls through the existing no-blind-retry mechanism
   or an equivalent generalized guard.
5. Permit the exact required transition, such as `establish_governance`, when
   allowed by the turn policy.
6. Stop if the model repeats the unavailable call, chooses an unrelated
   control-only loop, or exceeds the control-only allowance.
7. Preserve immediate stop for terminal policy failures.

**Tests:**

- failed precondition followed by correct governance;
- failed precondition followed by repeated identical call;
- failed precondition followed by broader-scope governance proposal;
- failed precondition under summary policy where governance is excluded;
- no infinite collision progress;
- existing cycle tests unchanged where semantics are unchanged.

**Pass gate:**

```text
one new recoverable failure permits correction; unchanged repetition reaches CYCLE_STOP
```

### Phase 7: Add Deterministic Corpus Inventory and Reading

**Dependencies:** Phases 2-3.

**Work:**

1. Add a read-only `inventory_text_corpus` tool.
2. Inputs:

   ```text
   root_path
   include_patterns
   exclude_patterns
   max_files
   ```

3. Return a signed `CorpusManifest` with exact paths, hashes, sizes, and line
   counts.
4. Add `read_text_batch` with:

   ```text
   manifest_id
   requests: path, start_line, end_line
   max_total_characters
   ```

5. Record one evidence artifact per file chunk.
6. Merge line coverage without counting duplicates.
7. Cap file count, lines per chunk, total output, and symlink traversal.
8. Reject files that changed after manifest creation.
9. Preserve existing `read_file` behavior for compatibility.

**Tests:**

- top-level Markdown corpus;
- nested Markdown corpus;
- deterministic path order;
- ignored internal state;
- forbidden paths;
- symlink escape;
- file drift after inventory;
- batch output budget;
- duplicate range reads;
- empty and unreadable files.

**Pass gate:**

```text
the runtime can prove the exact expected file set and exact read coverage for each file
```

### Phase 8: Add Source-Bound Per-File Summary Artifacts

**Dependencies:** Phase 7.

**Work:**

1. Add `record_document_summary` as an internal-state write permitted in
   read-only sessions but incapable of mutating ordinary workspace files.
2. Require manifest ID, path, file hash, source evidence IDs, coverage
   signature, and summary text.
3. Reject `coverage_complete=true` when deterministic line coverage has gaps.
4. Mark the artifact as model-generated and unverified interpretation.
5. Deduplicate identical summaries for identical source and prompt identity.
6. Permit revision of a summary only through a new immutable artifact linked to
   the previous summary.
7. Add a final `build_corpus_summary_report` operation.
8. Block `COMPLETE` when expected, summarized, and fully covered path sets differ.

**Tests:**

- complete one-file summary;
- incomplete line coverage;
- stale file hash;
- nonexistent evidence ID;
- duplicate artifact;
- revised artifact lineage;
- exact 16-of-16 coverage;
- partial corpus report.

**Pass gate:**

```text
every reported file summary is bound to complete verified source coverage and exact hashes
```

### Phase 9: Preserve Summary Meaning Across Context Reduction

**Dependencies:** Phase 8 and the existing context-recovery implementation.

**Work:**

1. Mark current-task corpus manifest, active read coverage, unresolved files,
   and completed summary artifacts as protected semantic context.
2. Compact raw completed read outputs only after a corresponding summary
   artifact exists or the raw text remains required for incomplete coverage.
3. Replace compacted file reads with:

   ```text
   path
   file hash
   covered ranges
   evidence IDs
   bounded head/tail excerpt
   summary ID when present
   ```

4. Never retire incomplete current-file reads needed to finish a summary.
5. Preserve exact corpus coverage and turn-policy signatures.
6. Fail closed with `INSUFFICIENT_CONTEXT_BUDGET` when the current corpus cannot
   be completed safely within budget.
7. Do not silently downgrade an all-files request to a subset.

**Tests:**

- multiple document summaries survive compaction;
- incomplete current file remains protected;
- old raw reads retire after summary creation;
- coverage report unchanged after recovery;
- all-files request cannot become partial silently;
- irreducible corpus fails with exact missing requirements.

**Pass gate:**

```text
context reduction preserves every completed summary and the exact remaining corpus work
```

### Phase 10: Correct Terminal Evidence Semantics

**Dependencies:** Phases 5, 8, and 9.

**Work:**

1. Replace mixed terminal observations with `TerminalEvidenceProjection`.
2. Place function-call arguments under `model_proposed_tool_calls`.
3. Place tool outputs and structured failures under verified categories only
   after deterministic runtime validation.
4. Restore source excerpts by task relevance, target path, media type, recency,
   and unresolved coverage rather than a Python-only allowlist.
5. Include per-file summary artifacts and corpus coverage directly.
6. Ensure terminal instructions prohibit deriving runtime architecture from
   model-proposed arguments.
7. If corpus coverage is complete, terminal synthesis may answer from the
   summary artifacts even when raw reads were compacted.
8. If coverage is partial, produce exact partial summaries and missing-file
   disclosure rather than claiming zero file evidence.

**Tests:**

- tool arguments cannot appear as verified observations;
- Markdown excerpts can be restored;
- complete summary artifacts support terminal synthesis;
- partial coverage is reported exactly;
- no content means no content claim;
- no unsupported `establish_governance` procedure claim from a hypothesis.

**Pass gate:**

```text
terminal answers cannot confuse model proposals with verified runtime or repository evidence
```

### Phase 11: Concise Chat Activity and Detailed Inspector

**Dependencies:** Phases 5, 7, 8, and 10.

**Work:**

1. Add activity projections for:

   ```text
   Corpus discovered: 16 Markdown files
   Reading docs: 6/16
   Summarizing docs: 4/16
   Coverage complete: 16/16
   Scope required for certified reasoning
   Corrective governance established
   Stopped: repeated unavailable tool request
   ```

2. Update an existing corpus-progress row in place instead of appending one row
   for every file and chunk.
3. Keep individual tool calls available in expanded details.
4. Limit the main-chat terminal failure projection to a short explanation,
   completed work, and exact next action.
5. Keep the full evidence-only report available through an inspector or export.
6. Preserve canonical events and evidence unchanged.
7. Ensure screen-reader text exposes status, counts, and failure reason.

**Tests:**

- progress aggregation;
- activity row replacement;
- concise structured failure;
- details retain full arguments and outputs under correct epistemic labels;
- terminal report not duplicated into chat;
- screen-reader projection;
- replay reconstructs identical activity.

**Pass gate:**

```text
chat shows only important milestones while full evidence remains inspectable and replayable
```

### Phase 12: Clarify Scope and Governance UX

**Dependencies:** Phases 3-5.

**Work:**

1. Document three separate concepts:

   ```text
   Authority: external maximum permission
   Governance scope: task-specific model/system record within authority
   Turn policy: non-authoritative tool restriction for one exact request
   ```

2. State that ordinary read-only summarization does not require the user to
   manually establish governance.
3. State that certified super reasoning requires governance but does not imply
   mutation authority.
4. State that file mutation still requires `--write` or a human-authored
   `--authority` manifest.
5. Add a read-only `/scope` projection showing current authority, governance,
   turn targets, and unavailable-tool reasons without changing state.
6. Add `/summarize` as an optional deterministic command alias compiling the
   same `SUMMARIZE` request.
7. Update help and ICPI preview text.

**Tests:**

- `/scope` is local/read-only;
- `/scope` does not establish governance;
- `/summarize` and natural language compile equivalent intent;
- help text distinguishes authority and governance;
- no command bypasses confirmation or authority.

**Pass gate:**

```text
users can understand current scope without being asked to perform an internal model-tool sequence
```

### Phase 13: Adversarial, Compatibility, and Release Qualification

**Dependencies:** Phases 0-12.

**Work:**

1. Add adversarial intent cases:
   - summarize versus write;
   - summarize versus export;
   - summarize versus explain;
   - prompt-injection text inside Markdown;
   - misleading filenames;
   - absolute paths and symlinks;
   - source drift;
   - oversized corpora;
   - repeated failed tool calls.
2. Run focused interaction, read, reasoning, provider, context-budget, and GUI
   suites.
3. Run full test discovery from one frozen snapshot.
4. Run compile, packaging, entry-point, headless GUI smoke, and replay tests.
5. Audit every requirement in Section 10 against current evidence.
6. Record source, schema, fixture, wheel, report, and test-output hashes.
7. Obtain exact human approval before any release or certification claim.

**Pass gate:**

```text
all requirements have exact-snapshot evidence and the original incident passes end to end
```

## 10. Requirement-to-Evidence Matrix

| ID | Requirement | Primary phase | Required evidence |
| --- | --- | --- | --- |
| SGR-001 | British and US summary language is recognized | 1 | interpreter fixtures |
| SGR-002 | Summary does not request a reasoning certificate | 1 | intent/output assertions |
| SGR-003 | Exact Markdown corpus is resolved | 2 | context and path fixtures |
| SGR-004 | Turn policy cannot broaden authority | 3 | property and rejection tests |
| SGR-005 | Summary receives read-only tools only | 4 | tool-name snapshot |
| SGR-006 | Super reasoning is hidden before governance | 4 | before/after tool tests |
| SGR-007 | Dispatch rechecks every precondition | 4-5 | injected-call tests |
| SGR-008 | Governance errors are reasoning-specific and structured | 5 | failure-envelope fixtures |
| SGR-009 | First new recoverable failure permits correction | 6 | fake-provider transition test |
| SGR-010 | Repeated identical failure stops | 6 | cycle/collision test |
| SGR-011 | Corpus manifest is exact and deterministic | 7 | golden manifest hashes |
| SGR-012 | Every source line is coverage-accounted | 7 | range-merging tests |
| SGR-013 | Per-file summaries are source-bound | 8 | summary artifact validation |
| SGR-014 | Whole-corpus completion is set equality | 8 | complete/partial report tests |
| SGR-015 | Context recovery preserves summary meaning | 9 | compaction tests |
| SGR-016 | Terminal projection separates proposals and observations | 10 | projection schema tests |
| SGR-017 | Markdown evidence can be restored | 10 | terminal source tests |
| SGR-018 | Chat activity is concise and aggregated | 11 | GUI projection tests |
| SGR-019 | Full evidence remains inspectable | 11 | detail/replay tests |
| SGR-020 | `/scope` is read-only and explanatory | 12 | session command tests |
| SGR-021 | Existing mutation governance remains unchanged | 0-13 | authority/action regression suite |
| SGR-022 | Original incident succeeds end to end | 13 | frozen end-to-end fixture |

## 11. End-to-End Acceptance Scenarios

### 11.1 Complete Markdown corpus summary

Input:

```text
Summarise each /docs/ markdown file.
```

Expected behavior:

1. ICPI classifies `SUMMARIZE`.
2. `/docs/` resolves to workspace-relative `docs`.
3. The corpus manifest contains every authorized `docs/**/*.md` file.
4. Only read/corpus tools are exposed.
5. Every file receives complete read coverage.
6. Every file receives one source-bound summary artifact.
7. Coverage status is `COMPLETE`.
8. The final answer contains one clearly identified summary per file.
9. No governance, EON, transaction, or approval is created.
10. The chat activity shows aggregated progress rather than every raw tool call.

### 11.2 Certified reasoning after inspection

Input:

```text
Read @file[docs/PRODUCTION_EPISTEMIC_BOUNDARY.md] and produce a certified
multi-hypothesis explanation of why terminal synthesis separates observations
from model belief.
```

Expected behavior:

1. The turn policy permits reads, governance proposal, and certified reasoning.
2. `run_super_reasoning` is initially absent.
3. Relevant file evidence is read.
4. Governance is established within exact read-only authority and source scope.
5. `run_super_reasoning` appears on the next model step.
6. The certificate binds current source snapshot and evidence IDs.
7. No mutation authority exists.

### 11.3 Incorrect premature reasoning call

Injected behavior:

```text
model calls run_super_reasoning before governance despite the unavailable tool surface
```

Expected behavior:

1. Dispatch rejects it with `GOVERNANCE_REQUIRED`.
2. One deduplicated collision is recorded.
3. One corrective step is permitted if the turn policy permits governance.
4. Repeating the exact call without governance produces no new progress and
   reaches `CYCLE_STOP`.

### 11.4 Oversized corpus

Expected behavior:

1. Exact manifest and budget requirements are reported.
2. Completed per-file summaries remain available.
3. Incomplete reads remain protected while possible.
4. If the corpus cannot fit safely, final status is `PARTIAL` or
   `INSUFFICIENT_CONTEXT_BUDGET` with exact unsatisfied files.
5. The system never claims that every file was summarized.

### 11.5 Source drift

Expected behavior:

1. A file changes after manifest creation.
2. Its read or summary artifact is rejected as stale.
3. The manifest and affected coverage must be refreshed.
4. Unchanged file summaries remain historically inspectable but cannot satisfy
   the new snapshot's completion set.

## 12. Test Inventory

### Interaction tests

```text
tests/interaction/test_models.py
tests/interaction/test_interpreter.py
tests/interaction/test_context.py
tests/interaction/test_routing.py
tests/interaction/test_envelope.py
tests/interaction/test_session.py
```

Required additions:

```text
summary spelling and precedence matrix
repository-root shorthand
corpus filter extraction
turn-policy signatures
route/policy monotonicity
/scope and /summarize behavior
```

### Agent and read tests

```text
tests/test_reads.py
tests/test_reasoning.py
tests/test_provider.py
tests/test_context_budget.py
```

Required additions:

```text
state-aware tool specs
structured failure envelopes
collision deduplication
corrective transition
corpus manifests
batch reads
line coverage
summary artifact validation
context compaction preservation
terminal projection separation
```

### GUI tests

```text
tests/gui/test_activity_projection.py
tests/gui/test_controller.py
tests/gui/test_icpi_controller.py
tests/gui/test_icpi_prompt.py
```

Required additions:

```text
aggregated corpus progress
short governance-required message
detail projection epistemic labels
terminal report link/export
replay identity
screen-reader status text
```

### Full validation

After focused tests pass:

```bash
python3 -m unittest discover -s tests/interaction -t . -v
python3 -m unittest tests.test_reads tests.test_reasoning tests.test_provider tests.test_context_budget -v
python3 -m unittest discover -s tests/gui -t . -v
python3 -m unittest discover -s tests -t . -v
python3 -m compileall -q ourd ourd_gui tests
python3 -m build --wheel --sdist
xvfb-run -a python3 -m ourd_gui --smoke-test
```

Commands must be revalidated against the current repository's documented
entry points before release execution. Passing focused tests does not establish
full completion.

## 13. Risk Register

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| `SUMMARIZE` captures a write request | Incorrect L0 route | Precedence tests and output-path detection |
| Implicit `/docs/` parsing accepts external path | Scope escape | Existing workspace canonicalization and exact existence checks |
| Turn policy becomes a second authority | Governance bypass | Non-authoritative schema and monotonic intersection with authority |
| Hidden tool prevents intended reasoning | Missing capability | Explicit unavailable-tool state and dynamic recomputation each step |
| Every failed call becomes artificial progress | Endless error loop | Collision atom deduplication and one-correction rule |
| Corpus batch output exceeds context | Provider failure | Deterministic batching and per-file summary artifacts |
| Summary artifacts are treated as verified truth | Epistemic overclaim | Explicit model-summary status and source coverage separation |
| Incomplete coverage is called complete | Missing documents | Exact set equality and line-range validation |
| Context compaction loses necessary source meaning | Unsupported final summary | Protect incomplete reads and persist source-bound summaries |
| Terminal projection still mixes arguments and evidence | Unsupported runtime explanation | Separate schema fields and projection tests |
| Concise GUI hides important failure | Poor auditability | Short chat plus expandable full evidence and replay |
| New persistence fields break old state | Startup failure | Versioned migration and legacy-state fixtures |
| Dynamic tool set changes provider context unexpectedly | Protocol/context instability | Include tool-set signature in request and context-budget reports |

## 14. Migration and Compatibility

### 14.1 Interaction compatibility

- Existing intent modes retain their identifiers and routes.
- `SUMMARIZE` is additive.
- Existing explicit context-reference syntax remains valid.
- `/scope` and `/summarize` are additive if implemented.

### 14.2 Agent API compatibility

- `run_task(task)` remains valid.
- `run_task` gains an optional `turn_execution_policy` keyword.
- Direct callers without a policy receive a conservative derived policy.
- `tool_specs()` may accept an optional policy but retains no-argument support.

### 14.3 Persistence compatibility

- Existing RuntimeState files load without corpus records.
- New summary and coverage collections default empty.
- Migration must not reinterpret old reasoning hypotheses as summary artifacts.
- Historical mixed terminal events remain readable but are labelled legacy in
  new projections.

### 14.4 Error compatibility

- Human-readable error text improves.
- New code must not require callers to parse message strings.
- Structured `error_code` and `failure_class` become the supported contract.
- Existing tests that assert a message substring should migrate to codes while
  retaining a minimal compatibility phrase where useful.

## 15. Definition of Done

This implementation is complete only when:

1. `Summarise each /docs/ markdown file.` is classified as `SUMMARIZE`.
2. The exact authorized Markdown corpus is manifested and hash-bound.
3. Ordinary summarization does not request or call super reasoning.
4. Summary turns expose no governance, candidate, EON, apply, or command tools.
5. Certified reasoning turns expose governance before super reasoning.
6. `run_super_reasoning` is never advertised while its preconditions are false.
7. Dispatch still rejects unavailable injected calls.
8. Governance-required errors are structured and do not say only `mutation
   locked`.
9. The first new recoverable precondition failure permits one correction.
10. Repeating the identical failure reaches deterministic cycle stop.
11. Every claimed file summary is bound to complete line coverage, file hash,
    source snapshot, and read evidence.
12. Whole-corpus completion uses exact set equality.
13. Context reduction preserves completed summary artifacts and remaining work.
14. Terminal synthesis separates verified outputs from model-proposed arguments.
15. Markdown source evidence can be restored when relevant.
16. Main chat activity is concise and aggregated.
17. Full evidence remains available through detail and replay projections.
18. Existing authority, EON, approval, transaction, verification, rollback, and
    CFEL tests pass.
19. Focused suites, full discovery, compile, packaging, and headless GUI smoke
    pass on one frozen source snapshot.
20. Requirement-to-evidence audit and exact human approval bind the release
    candidate and validation artifacts.

## 16. Recommended Delivery Slices

### Slice A: Correct Routing and Tool Safety

Phases 0-6.

Deliver:

- `SUMMARIZE` intent;
- exact corpus scope parsing;
- turn policy;
- state-aware tool surface;
- structured failures;
- bounded correction after new failures.

This slice eliminates the original governance error path even before advanced
corpus summarization is complete.

### Slice B: Complete Evidence-Bound Summarization

Phases 7-9.

Deliver:

- deterministic corpus manifests;
- batch reads and line coverage;
- per-file summary artifacts;
- complete corpus reports;
- context-recovery preservation.

### Slice C: Trustworthy Terminal and GUI Projections

Phases 10-12.

Deliver:

- epistemically separated terminal projections;
- task-relevant evidence restoration;
- concise chat activity;
- full inspector detail;
- clear scope and governance UX.

### Slice D: Qualification and Release

Phase 13 plus the full requirement audit.

Every slice must preserve the exact guarantees of prior slices. No slice may be
promoted from focused green tests alone.
