# OIEC-SR v1.0 Implementation Plan

## Super Reasoning Kernel for OIEC-STM-Agent

**Plan date:** August 28, 2026

**Repository:** `pghauff73/ourd-coding-agent`

**Target product version:** OIEC-STM-Agent `0.5.x` development line

**Plan status:** Approved design input converted into an executable repository roadmap

## 1. Objective

Extend OIEC-STM-Agent from a governed, bounded reasoning agent into a measured,
evidence-driven multi-hypothesis system without weakening any existing authority,
risk, evidence, persistence, transaction, or retry invariant.

The target reasoning-to-action path is:

```text
OURD
  -> Boundary Determination (BD)
  -> Dimension Limiting (DL)
  -> OIEC-SR
  -> IURM
  -> EON
  -> Evidence Gate
  -> Action
  -> CFEL
  -> revised hypothesis state
```

OIEC-SR performs:

```text
hypothesis generation
  -> bounded multi-path search
  -> independent verification
  -> adversarial falsification
  -> deterministic ranking
  -> bounded synthesis
  -> synthesis verification
  -> reasoning certificate
```

The architectural claim to prove is not that multiple model responses are
automatically better. The claim is that bounded competing explanations,
independent checks, explicit counterexamples, and measurable stopping rules can
improve difficult-task accuracy and failure recovery while preserving the
existing governed mutation boundary.

## 2. Non-Negotiable Invariants

### 2.1 Authority supremacy

OIEC-SR may propose hypotheses, evidence requests, experiments, candidate
reasoning paths, and actions. It may not expand `AuthorityManifest`, broaden
`GovernanceRecord`, lower `PolicyEngine.effective_risk()`, approve evidence, or
execute a mutation.

```text
SR(Xt) cannot enlarge external authority Omega(t).
```

### 2.2 Finite active reasoning state

The active state must remain bounded by deterministic limits:

```text
hypotheses <= max_hypotheses
candidate paths <= max_paths
steps per path <= max_steps_per_path
topology nodes <= max_topology_nodes
topology edges <= max_topology_edges
provider calls <= max_provider_calls
tool calls <= max_tool_calls
tokens <= max_tokens
```

No recursive or tree-search path may bypass these limits.

### 2.3 Structured artifacts, not hidden chain-of-thought

Persist only reviewable records such as claims, premises, evidence references,
inference modes, assumptions, predictions, falsifiers, verifier results,
counterexamples, scores, and conclusions. Provider prompts must request concise
structured outputs and must not request private chain-of-thought.

### 2.4 Evidence provenance

Every factual premise and empirical conclusion must bind to a declared evidence
artifact, observation, deterministic adapter result, or explicit assumption.
Reasoning prose alone cannot become evidence.

### 2.5 EON remains the mutation boundary

A `ReasoningCertificate` explains why a candidate was selected. It is not
mutation authority. Repository writes and governed commands still require exact
EON identity, evidence gating, policy checks, and any required human approval.

### 2.6 No blind retry

OIEC-SR must compose with `AttemptKey` and CFEL. Changed prose, reordered
hypotheses, or regenerated path IDs must not unlock a previously failed action
without relevant new evidence, a changed snapshot, a changed bounded experiment,
or another material epistemic change.

## 3. Current Repository Baseline

The repository already contains the first bounded OIEC-SR slice. This plan must
extend that implementation rather than restart it or report already completed
work as future work.

Current validation baseline on August 28, 2026:

- 36 focused OIEC-SR tests pass;
- 126 focused SR/OIEC/provider/persistence/CLI/GUI/docs compatibility tests pass;
- the complete discoverable suite passes: 282 tests in 802.205 seconds;
- `RuntimeState` is already schema version 3;
- the public package version is already `0.5.0` in the working tree.

### 3.1 Coverage and gaps

| Capability | Current status | Required next state |
| --- | --- | --- |
| `Hypothesis` | Implemented | Add predictions and deterministic update provenance |
| `HypothesisSet` | Missing | Add bounded canonical aggregate and uncertainty |
| Hypothesis normalization | Implemented for mutually exclusive proposals | Generalize into reusable deterministic update engine |
| CFEL hypothesis revision | Implemented | Bind revisions to predictions, counterexamples, and update records |
| `ReasoningTopology` | Implemented | Add inference metadata, stronger grounding, connectivity, and attack semantics |
| Candidate generation | Default four, adaptive cap sixteen | Add structural diversity measurement and duplicate collapse |
| `ReasoningPath` | Implemented with structured steps | Bind path-specific topology projection without duplicating canonical graph state |
| Independent verifier | Implemented | Add component scores, missing assumptions, and synthesis verification |
| Dedicated falsifier | Implemented for top candidates | Add alternative explanations and deterministic adapter hooks |
| Ranking | Implemented with fixed weights | Move weights into versioned configuration and add diversity contribution |
| Synthesis | Partial conclusion merge | Add `SynthesisResult` and mandatory post-synthesis verification |
| Adaptive compute | Candidate/provider-call budget exists | Add token, tool, pass, ambiguity, and interaction budgets |
| VOI stopping | Implemented in basic form | Generalize to typed next-operation selection |
| `ReasoningCertificate` | Implemented | Add hypothesis signature, survivor count, disagreement, residual risk, and terminal states |
| Runtime persistence | Schema v3 implemented | Use v3 to v4 migration for expanded durable state |
| EON binding | Implemented | Preserve and extend certificate integrity checks |
| Provider batching | `create_responses()` implemented | Add typed candidate adapter without breaking existing providers |
| Reasoning context compression | Missing | Add bounded canonical context projection |
| Contradiction records | Missing | Add first-class persistent contradiction lifecycle |
| Mathematical adapters | Missing | Add deterministic verifier adapters after core qualification |
| Causal module | Missing | Add causal claims, interventions, and counterfactual checks after core qualification |
| Benchmark harness | Missing | SR-0 is the next mandatory milestone |
| Release qualification | Missing | Require comparative benchmarks and ablations |

### 3.2 Current-state corrections to the proposed design

1. **Runtime migration:** the repository is already at RuntimeState v3, so the
   expanded durable state must migrate v3 to v4, not v2 to v3.
2. **Existing topology owner:** `ourd/reasoning/topology.py` is already the
   canonical reasoning topology owner. Do not introduce another graph owner.
3. **Existing batching primitive:** `ModelProvider.create_responses()` already
   provides bounded ordered multi-response behavior. `create_candidates()` may
   be an optional convenience adapter, not a required breaking replacement.
4. **Existing synthesis:** synthesis currently returns a conclusion and source
   path IDs. It is not yet a verified `SynthesisResult` and must remain labelled
   partial.
5. **Existing tests:** the current coverage is in `tests/test_reasoning.py`.
   Split it only while preserving every existing assertion and discovery path.
6. **Benchmark-before-complexity:** because the initial SR slice already exists,
   freeze it as the SR-0 comparison candidate. No additional reasoning
   complexity lands until the benchmark harness records the baseline.

## 4. Canonical Package Ownership

Use one canonical owner for each semantic fact. Add modules only when they own a
distinct algorithm or record lifecycle.

```text
ourd/reasoning/
    __init__.py          public reasoning API
    models.py            all durable reasoning record schemas
    topology.py          graph construction and validation
    hypotheses.py        hypothesis-set validation and belief updates
    generator.py         structured proposer requests and path parsing
    verifier.py          step/path/synthesis verification
    falsifier.py         counterexample and alternative-explanation search
    scoring.py           versioned deterministic scoring
    search.py            bounded orchestration and diversity filtering
    synthesis.py         synthesis construction and compatibility checks
    budget.py            difficulty, compute allocation, and VOI
    certificate.py       certificate construction and integrity validation
    context.py           bounded reasoning-context projection
    contradictions.py    contradiction creation and resolution lifecycle
    adapters/
        base.py          deterministic verifier adapter protocol
        arithmetic.py    Python integer/decimal checks
        symbolic.py      optional SymPy integration
        dimensional.py   unit/dimension checks
        finite_domain.py exhaustive bounded checks
        causal.py        causal topology and intervention checks
    kernel.py            pure bounded state-machine orchestration
```

Durable dataclasses remain in `models.py` to avoid circular imports and multiple
serialization owners. Algorithm modules consume and return those records.

Tests migrate incrementally to:

```text
tests/reasoning/
    __init__.py
    test_models.py
    test_hypotheses.py
    test_topology.py
    test_generator.py
    test_verifier.py
    test_falsifier.py
    test_scoring.py
    test_search.py
    test_synthesis.py
    test_budget.py
    test_certificate.py
    test_context.py
    test_contradictions.py
    test_kernel.py
    test_integration.py
```

Do not delete `tests/test_reasoning.py` until equivalent split-suite coverage is
proven. It may temporarily import the split test cases as a compatibility shim.

Benchmarks live under:

```text
benchmarks/reasoning/
    README.md
    schema.json
    tasks/
        logical.jsonl
        mathematical.jsonl
        debugging.jsonl
        scientific.jsonl
        causal.jsonl
        adversarial.jsonl
    fixtures/
    runners/
    reports/
    baseline-v1.json
```

## 5. Expanded Durable Data Contracts

### 5.1 `HypothesisSet`

Add a canonical aggregate rather than treating the runtime dictionary as the
complete epistemic model.

```python
@dataclass(frozen=True)
class HypothesisSet:
    schema_version: int = 1
    hypotheses: tuple[Hypothesis, ...] = ()
    max_hypotheses: int = 16
    mutually_exclusive: bool = False
    uncertainty_bp: int = 0
    update_index: int = 0
    signature: str = ""
```

Invariants:

- count does not exceed `max_hypotheses`;
- IDs are unique and canonical;
- falsified hypotheses remain present for audit;
- mutually exclusive active posteriors sum to `SCORE_SCALE`;
- independent hypotheses are range-checked but not force-normalized;
- signatures are order-independent;
- the aggregate never deletes prior evidence bindings.

### 5.2 `HypothesisUpdateRecord`

Record deterministic belief transitions:

```text
update_id
hypothesis_id
previous_posterior_bp
proposed_likelihood_bp
validated_likelihood_bp
new_posterior_bp
evidence_ids
operation
reason
signature
```

The model may propose a likelihood. Deterministic code validates ranges,
normalizes where required, applies status rules, binds evidence, and records the
previous value. A falsified hypothesis cannot regain support unless relevant new
evidence is explicitly attached and a new update record is created.

### 5.3 Topology v2 fields

Extend `ReasoningEdge` compatibly with:

```text
inference_id
inference_mode
```

Supported modes:

```text
deductive
inductive
abductive
causal
analogical
probabilistic
authority
defeasible
constraint
computational
```

Do not embed a complete duplicate topology inside every `ReasoningPath`.
Instead, add path node/edge membership IDs or a path topology signature that
projects from the one canonical `ReasoningTopology`.

### 5.4 `SynthesisResult`

```python
@dataclass(frozen=True)
class SynthesisResult:
    schema_version: int = 1
    winning_path_id: str = ""
    source_path_ids: tuple[str, ...] = ()
    accepted_node_ids: tuple[str, ...] = ()
    rejected_node_ids: tuple[str, ...] = ()
    merged_conclusion: str = ""
    remaining_uncertainties: tuple[str, ...] = ()
    confidence_bp: int = 0
    verifier_report_id: str = ""
    signature: str = ""
```

The synthesizer may combine only compatible survivor components. The merged
topology must pass the same grounding, cycle, evidence, assumption, verifier,
and falsifier gates as ordinary paths. An unverified synthesis cannot win.

### 5.5 `ContradictionRecord`

```text
contradiction_id
left_claim_id
right_claim_id
evidence_left
evidence_right
conflict_type
severity_bp
resolution_status
resolution_evidence_ids
signature
```

Conflict types are `logical`, `empirical`, `causal`, `scope`, `temporal`,
`definition`, and `measurement`. High-severity unresolved contradictions cap
derived confidence and prevent a `SOLUTION` terminal state.

### 5.6 Reasoning certificate v2

Extend the current certificate without discarding existing fields:

```text
problem_hash
hypothesis_signature
topology_signature
candidate_set_signature
synthesis_signature
candidate_count
surviving_candidate_count
winning_path_id
evidence_coverage_bp
verifier_score_bp
falsification_score_bp
uncertainty_before_bp
uncertainty_after_bp
disagreement_bp
residual_risk_bp
unresolved_assumptions
unresolved_contradiction_ids
terminal_state
reasons
signature
```

Terminal states:

```text
SOLUTION
EPISTEMIC_STOP
INSUFFICIENT_EVIDENCE
GOVERNANCE_STOP
COMPUTE_BUDGET_EXHAUSTED
NO_SURVIVING_HYPOTHESIS
```

### 5.7 RuntimeState v4 migration

Add:

```text
hypothesis_state
hypothesis_updates
reasoning_context
contradictions
last_synthesis
reasoning_qualification
```

Migration requirements:

1. Rebuild the current v3 projection without modifying old events.
2. Convert `hypothesis_pool` into `HypothesisSet` deterministically.
3. Preserve existing v3 candidate, topology, and certificate records.
4. Add new defaults without inventing evidence or contradiction resolutions.
5. Append one migration event after the v4 projection is built.
6. Prove v1 through v4, v2 through v4, and v3 through v4 paths.

## 6. Milestone Plan

## SR-0: Benchmark Baseline and Harness

**Status:** SR-0A, SR-0B, and SR-1A complete; SR-2A is the next implementation slice.

### Work

1. Define strict JSON schema for benchmark tasks and results.
2. Freeze at least a small development set in every required category.
3. Record exact repository snapshot, package version, provider configuration,
   model identity, reasoning effort, context limit, output limit, decoding
   settings, hardware metadata, seed where supported, and wall-clock source.
4. Implement runners for:
   - base provider with no OIEC reasoning;
   - current governed OIEC path;
   - current four-path OIEC-SR foundation.
5. Record per problem:
   - correctness and oracle method;
   - evidence coverage;
   - counterexample detection;
   - calibration;
   - token and tool usage;
   - collisions and retries;
   - wall time;
   - terminal state;
   - artifact hashes.
6. Write `benchmarks/reasoning/baseline-v1.json` from one frozen run.

### Tests

```text
test_benchmark_schema_is_strict
test_task_ids_are_unique
test_runner_preserves_task_order
test_result_binds_snapshot_and_provider
test_correctness_oracle_is_explicit
test_baseline_file_is_reproducible
test_benchmark_does_not_mutate_workspace
```

### Exit gate

- Harness, schema, development tasks, and baseline result exist.
- Repeated deterministic fixtures produce byte-identical results.
- Model-backed results identify unavoidable nondeterminism rather than hiding it.
- The current SR foundation is frozen as comparison system C0.

### SR-0A completion evidence

- Added a strict benchmark schema and fail-closed runtime validators.
- Added eight frozen development tasks covering logic, arithmetic, debugging,
  evidence synthesis, scientific inference, causal reasoning, ambiguity
  resolution, and adversarial evidence.
- Added 24 ordered A/B/C observations and a typed executor protocol.
- Added deterministic scoring for correctness, evidence coverage,
  counterexample detection, calibration, tokens, tool calls, collisions,
  retries, and wall time.
- Bound the benchmark harness, tasks, fixtures, package version, OIEC-SR source
  owners, Git HEAD, dirty-state flag, and exact source hashes into the baseline.
- Added byte-identical generation and `--check` verification.
- Marked fixture output `development_fixture_only` and
  `performance_claim_allowed=false` so synthetic results cannot become release
  evidence.
- Generated `benchmarks/reasoning/baseline-v1.json` with eight tasks, 24 ordered
  observations, benchmark identifier
  `4ab1d3b6a1b56155a30045275ed61922bc0f6e4e20758a02366a1e3edf1c4d0a`,
  and canonical run signature
  `a26710c08f619536f0b128977a9f9f1dde3c186a2ffd9ef503a649f487462c87`.
- Passed 10 focused benchmark tests, benchmark packaging coverage, deterministic
  regeneration, compile checks, and the complete 293-test repository suite in
  847.294 seconds.

### SR-0 compensation plan

The current checkout cannot guarantee a portable live-model baseline because a
model-backed run depends on exact provider availability, model digest, context,
decoding, hardware, and runtime state. SR-0A therefore establishes the complete
deterministic harness and recorded-fixture baseline first. SR-0B will add
provider-backed executors and append a separately identified model-backed run;
it will not overwrite `baseline-v1.json`.

Source drift during SR-0B exposed a second issue: byte-identical regeneration
of a historical baseline conflicts with append-only evidence once the harness
itself changes. The implemented compensation preserves `baseline-v1.json`
byte-for-byte, pins its SHA-256 checksum in `baseline-v1.sha256`, verifies its
internal canonical signature, and exposes a separate `--check-current-source`
gate that reports drift without rewriting history.

### Next slice: SR-0B model-backed executor

1. Add an executor that binds each observation to exact provider, model,
   reasoning effort, decoding, limits, hardware, and timing metadata.
2. Run the same frozen tasks through base, governed OIEC, and OIEC-SR paths.
3. Store the model-backed run as a separate dated artifact rather than changing
   the deterministic fixture baseline.
4. Fail closed when provider identity, model identity, source snapshot, or
   required runtime metadata is unavailable.
5. Add reproducibility and nondeterminism reporting before allowing any
   performance comparison.

### SR-0B implementation evidence

- Added base, governed single-path OIEC, and actual four-path
  `SuperReasoningKernel` benchmark executors.
- Added exact provider binding for endpoint, model digest, model metadata hash,
  reasoning effort, context/output limits, timeout, zero retries, and decoding.
- Added runtime binding for kernel, Python, CPU, memory, GPU identity, driver,
  GPU memory, Ollama allocation, runtime context, and monotonic clock source.
- Added per-response sanitized hashes and exact provider usage without
  persisting encrypted or private reasoning payloads.
- Added fail-closed checks for missing model identity, credential-bearing URLs,
  insufficient runtime context, and anything other than observed `100% GPU`
  allocation for local comparisons.
- Added a separate append-only model-run CLI that refuses to overwrite the
  deterministic baseline or an existing model artifact.
- Labelled the current evidence-handle development tasks as plumbing-only and
  prohibited performance claims until held-out non-leaking tasks and repeated
  runs exist.
- Recorded the failed medium-effort live probe: four proposer calls consumed
  12,867 tokens without final JSON. The compensation profile uses explicitly
  bound `low` reasoning effort, which produced valid proposer JSON, and halts a
  reasoning batch after its first empty or malformed structured response.
- A second live probe showed one low-effort perspective truncating at the
  2,048-token cap. The compensated profile uses a 4,000-token input budget,
  4,096 output tokens, and four reasoning steps inside the observed 8,192-token
  local runtime context.
- The first full run then exposed an Ollama OOM kill caused by 8K context
  checkpoints; the inherited `qwen3.8-27b-fast` template also hardcodes xhigh
  reasoning. The second compensation adds a repository-owned neutral-template
  4K derived model, limits input/output to 2,000/2,048 tokens, limits paths to
  two steps, and requires the combined budgets to fit the observed context.
- The 4K Qwen3.8 probe still exhausted proposer output. The installed
  `qwen2.5:14b` fallback completed all eight SR provider roles without transport
  or JSON failure when the unsupported Responses reasoning field was omitted.
  The compensated plumbing run therefore binds that exact digest and records
  `reasoning_effort=provider_default`; this is not a model-quality substitution
  or performance claim.

### SR-0B completion evidence

- Preserved the failed Qwen3.8 run with artifact SHA-256
  `5a1fbf194327f25ca5e00bbaa339c5ac5de58574fee734b245c46e07294c057c`
  and systemd OOM evidence from August 28, 2026.
- Produced a compensated current-source run at
  `benchmarks/reasoning/runs/model-bound-2026-08-28-qwen2.5-14b-provider-default-current-source.json`.
- Bound model digest
  `7cdf5a0187d5c58cc5d369b255592f7841d1c4696d45a8c8a9489440385b22f6`,
  source manifest
  `91cadc30758e37b383eb214aaceafcd32fbc55823653d543c1774b8e395167d4`,
  and run signature
  `54f046f7b43d677337da0d98f99d507748badb4bb0948f7961306e6de37a32a5`.
- Verified every source hash against the current checkout and verified artifact
  SHA-256 `87c9560e5cdf3f01c2dc5393873120457501051728c161fca3dcb9e36b2f1085`.
- Completed eight base calls, eight governed OIEC calls, and 67 OIEC-SR calls
  with zero provider failures, zero retries, observed `100% GPU`, and an
  8,192-token runtime context.
- Passed strict JSON schema validation and confirmed that no credential,
  authorization, encrypted-reasoning, or private-reasoning payload entered the
  artifact.
- Retained `development_model_plumbing_only` and
  `performance_claim_allowed=false`. The generic hypothesis bootstrap produced
  no accepted OIEC-SR survivor, so the run proves plumbing rather than improved
  reasoning quality.
- Passed the complete repository suite: 302 tests in 876.293 seconds. Also
  regenerated 187 HTML pages and 488 interactive SVG figures twice with the
  identical documentation tree digest
  `993152f435641c036669ab389d5d3662203ce4367ab8cd2d177052bdffcbc54d`.

### Next slice: SR-1A hypothesis state

1. Add immutable `HypothesisSet` and `HypothesisUpdateRecord` owners.
2. Implement fixed-point evidence-bound posterior updates without raw
   chain-of-thought.
3. Preserve current generic hypothesis pools only as a compatibility
   projection.
4. Add RuntimeState v4 migration and round-trip tests.
5. Re-run the provider-bound benchmark to determine whether first-class
   hypotheses produce surviving verified candidates.

## SR-1: Hypothesis Engine

**Dependencies:** SR-0.

### Work

- Add `HypothesisSet` and `HypothesisUpdateRecord`.
- Add predictions to `Hypothesis`.
- Move hypothesis validation/update algorithms into `hypotheses.py`.
- Implement fixed-point update and mutually exclusive normalization.
- Bind updates to evidence IDs and CFEL collision IDs.
- Add RuntimeState v4 migration and round-trip support.
- Preserve current `hypothesis_pool` as a compatibility projection until all
  callers use `hypothesis_state`.

### Tests

```text
test_hypothesis_count_is_bounded
test_mutually_exclusive_probabilities_normalize
test_independent_hypotheses_are_not_force_normalized
test_falsified_hypothesis_requires_new_evidence_to_recover
test_update_preserves_previous_posterior
test_evidence_binding_is_monotonic
test_hypothesis_set_signature_is_order_independent
test_runtime_v3_migrates_to_v4
```

### Exit gate

The active hypothesis set is finite, content-addressed, evidence-bound, and
replayable from persisted updates.

### SR-1A completion evidence

- Added immutable, content-addressed `HypothesisSet` and
  `HypothesisUpdateRecord` owners and added predictions to `Hypothesis`.
- Added `ourd/reasoning/hypotheses.py` with bounded construction,
  order-independent signatures, fixed-point Bayesian updates, deterministic
  mutually-exclusive normalization, monotonic evidence bindings, falsified
  recovery rules, and CFEL update integration.
- Made `RuntimeState.hypothesis_state` authoritative under schema v4 while
  preserving `hypothesis_pool` only as a validated derived compatibility
  projection.
- Added append-only v1-to-v4, v2-to-v4, and v3-to-v4 migrations without
  modifying historical events. Persisted update records rebuild the same state
  and fail closed when the compatibility projection drifts.
- Content-addressed CFEL collision identities and belief-update records so
  identical projected inputs replay to identical hypothesis signatures.
- Passed 109 focused hypothesis, model benchmark, SR/OIEC, persistence, and
  packaging tests, followed by the complete 316-test repository suite in
  821.893 seconds.
- Regenerated 189 HTML pages and 492 interactive SVG figures twice with the
  identical documentation tree digest
  `fad4a4a943aacbb2875990157c8a97b719436e11c5ab84e558ce816731b6e667`.
- Produced the source-bound provider artifact
  `benchmarks/reasoning/runs/model-bound-2026-08-28-qwen2.5-14b-sr1a-current-source.json`
  with source manifest
  `4c93486c3b3c3d18ce7809b6d7ca01e559dab1e67c50fbfe51b8ae1226554d15`,
  run signature
  `cd57a874cd75914ca91becca0f0632412b35e2445883c227fadaff8b61bf3649`,
  and artifact SHA-256
  `dc8d95bcc9913ef3c1c0a5728fd1a45d0988c8977fabf78b206e3954cd813abf`.
- The provider run completed 82 total calls with zero provider failures, zero
  retries, exact model identity, observed `100% GPU`, and an 8,192-token
  runtime context.
- First-class state did not by itself produce an accepted OIEC-SR survivor:
  all eight tasks stopped with `INSUFFICIENT_EVIDENCE`. This is retained as a
  measured limitation rather than described as a reasoning improvement.

### SR-1A compensation record

- Added the missing canonical serialization import exposed by the first
  focused run.
- Corrected the mutually-exclusive one-hypothesis collision case so a
  zero-likelihood falsifier can produce an all-falsified zero-mass terminal
  state instead of being normalized back to certainty.
- Preserved qualitative `WEAKENED` status when counterevidence challenges a
  lone currently exhaustive hypothesis before an alternative is generated.
- Updated the generated-documentation inventory assertion from 298 to 300 only
  after the two new canonical type owners appeared in the authoritative
  manifest.

### Next slice: SR-2A topology grounding

1. Add content-addressed inference IDs and explicit inference modes.
2. Validate every evidence node against the finite declared evidence universe.
3. Require each material conclusion to trace to evidence, observation,
   validated premise, or an explicitly labelled assumption.
4. Keep attack edges separate from positive support and reject disconnected
   reasoning branches.
5. Rerun the provider-bound benchmark to measure whether grounded topology
   produces any surviving verified candidate.

## SR-2: Reasoning Topology v2

**Dependencies:** SR-1.

### Work

- Add inference IDs and modes.
- Validate evidence references against the declared finite evidence universe.
- Require every material conclusion to trace to evidence, observation,
  validated premise, or explicit assumption.
- Keep assumption-only conclusions hypothetical.
- Reject disconnected branches that do not contribute to a hypothesis,
  conclusion, contradiction, falsifier, or decision.
- Treat positive support/entailment as acyclic while allowing typed attack edges
  to point backward without creating support.
- Bind counterexamples to the hypotheses or steps they falsify.

### Tests

```text
test_positive_reasoning_cycle_rejected
test_unknown_evidence_reference_rejected
test_conclusion_traces_to_grounding
test_assumption_only_conclusion_remains_hypothetical
test_counterexample_falsifies_hypothesis
test_attack_edges_do_not_create_support
test_unconnected_reasoning_branch_rejected
test_topology_signature_is_order_independent
```

### Exit gate

Every accepted conclusion has a machine-checkable grounding path and every
attack relation remains distinct from positive justification.

## SR-3: Bounded Multi-Path Diversity

**Dependencies:** SR-2.

### Work

- Preserve the current default of four paths and hard cap of sixteen.
- Use distinct strategies: direct, mechanistic, counterexample-first,
  assumption-inversion, causal, mathematical, evidence-synthesis, and abductive.
- Define structural path features:
  - hypothesis IDs;
  - evidence IDs;
  - inference-mode sequence;
  - assumptions;
  - falsifiers;
  - normalized conclusion claim.
- Implement deterministic similarity and duplicate threshold configuration.
- Collapse semantic duplicates or regenerate within the same fixed budget.
- Content-address path IDs from canonical structure, not provider prose order.

### Tests

```text
test_candidate_count_is_bounded
test_semantic_duplicates_are_collapsed
test_prose_only_difference_is_not_diversity
test_distinct_strategies_are_retained
test_regeneration_does_not_exceed_budget
test_path_ids_are_content_addressed
```

### Exit gate

Four generated paths represent materially different explanatory structures,
not four paraphrases.

## SR-4: Independent Verifier v2

**Dependencies:** SR-3.

### Work

- Expand `VerifierReport` with premise validity, evidence support, inference
  quality, consistency, completeness, unsupported nodes, and missing
  assumptions.
- Continue using the minimum step score as the conservative path score.
- Make critical invalid inference a categorical rejection.
- Ignore proposer confidence during verification.
- Verify deterministic adapter outputs as evidence, not as authority.
- Add a verifier mode for `SynthesisResult`.

### Tests

```text
test_weakest_step_controls_path_score
test_missing_factual_evidence_rejects_step
test_missing_assumption_is_reported
test_overstrong_conclusion_is_rejected
test_provider_confidence_cannot_override_verifier
test_critical_invalid_inference_rejects_path
test_synthesis_uses_same_verifier_contract
```

### Exit gate

Every survivor has a complete step-level report and no critical unsupported
inference.

## SR-5: Dedicated Falsifier v2

**Dependencies:** SR-4.

### Work

- Keep falsifier requests separate from proposer and verifier requests.
- Add alternative explanations, boundary cases, reversed causal direction,
  incorrect invariants, and evidence-reversal conditions.
- Falsify at least the top two verifier-ranked candidates.
- Invoke deterministic adapters for arithmetic, code, and finite boundary cases
  when available.
- Attach discovered counterexamples to hypotheses and contradiction records.

### Tests

```text
test_top_two_candidates_are_falsified
test_falsifier_receives_no_proposer_confidence_authority
test_boundary_counterexample_is_recorded
test_alternative_explanation_reduces_survival
test_critical_counterexample_prevents_selection
test_counterexample_updates_hypothesis_state
```

### Exit gate

No candidate can win solely because it passed its own proposer narrative.

## SR-6: Versioned Ranking and Verified Synthesis

**Dependencies:** SR-5.

### Work

- Add versioned score configuration, initially:

```text
verifier                  30
evidence                  25
consistency               15
falsification survival    15
goal relevance            10
diversity                   5
uncertainty penalty       -15 maximum
compute penalty            -5 maximum
```

- Bind the score configuration ID and hash into `CandidateSet` and the
  certificate.
- Preserve lexical path ID as the final deterministic tie-break.
- Build `SynthesisResult` from compatible survivors above a configured floor.
- Reject synthesized components that are absent from source survivors.
- Rebuild and verify the synthesized topology.
- Fall back to the winning verified path when synthesis fails.

### Tests

```text
test_score_config_is_versioned_and_hashed
test_candidate_ties_use_lexical_path_id
test_diversity_contributes_only_for_structural_difference
test_synthesis_cannot_invent_source_path
test_incompatible_components_are_not_merged
test_unverified_synthesis_cannot_win
test_failed_synthesis_falls_back_to_verified_winner
```

### Exit gate

The selected output is either a verified synthesis or the best verified
surviving path, with deterministic score provenance.

## SR-7: Adaptive Compute, Context, and VOI

**Dependencies:** SR-6.

### Work

- Extend `ReasoningBudget` with minimum/maximum paths, verifier/falsifier passes,
  tokens, tool calls, and per-operation costs.
- Estimate difficulty from uncertainty, ambiguity, constraint complexity,
  interacting dimensions, and prior verifier disagreement.
- Clamp every derived value against human/OIEC/provider limits.
- Create bounded `ReasoningContext` containing only the current problem,
  constraints, active hypotheses, top evidence, topology summary, collisions,
  unresolved questions, and candidate summaries.
- Do not resend full conversation history as reasoning memory.
- Generalize VOI to typed operations:

```text
GENERATE_HYPOTHESIS
RETRIEVE_EVIDENCE
RUN_READ_ONLY_EXPERIMENT
VERIFY_AGAIN
SEARCH_COUNTEREXAMPLE
REFINE_DIMENSION
STOP
```

- Permit only read-only or IURM-governed experiments. The SR kernel itself does
  not execute tools.

### Tests

```text
test_model_cannot_raise_compute_budget
test_candidate_count_increases_only_within_cap
test_token_and_tool_budgets_are_enforced
test_context_projection_is_bounded
test_context_excludes_raw_conversation_history
test_no_positive_voi_stops_reasoning
test_voi_operation_cannot_bypass_iurm_or_eon
test_identical_state_selects_identical_next_operation
```

### Exit gate

Reasoning consumes only bounded canonical context and stops when no allowed
operation has positive expected value.

## SR-8: Certificates, Contradictions, GUI, and Exports

**Dependencies:** SR-7.

### Work

- Add certificate v2 and terminal states.
- Add contradiction lifecycle and confidence caps.
- Recompute all linked signatures before EON binding.
- Display problem, hypotheses, candidate comparison, weakest verifier step,
  falsifiers, synthesis provenance, contradictions, budgets, and terminal state
  in the GUI as read-only observability.
- Add bounded JSON and Markdown exports under `.ourd-agent/gui/`.
- Label exports non-authoritative and preserve exact IDs and hashes.

### Tests

```text
test_identical_state_has_identical_certificate
test_unresolved_critical_contradiction_blocks_solution
test_certificate_binds_hypothesis_and_score_config
test_tampered_synthesis_blocks_eon_binding
test_gui_reasoning_projection_is_read_only
test_exports_preserve_ids_hashes_and_limits
test_exports_do_not_create_approval_or_evidence
```

### Exit gate

The complete reasoning decision can be inspected and reproduced without giving
the GUI or export path mutation authority.

## SR-9: Mathematical and Causal Adapters

**Dependencies:** SR-8 and core SR benchmark evidence showing remaining gaps.

### Work

Implement optional deterministic adapters for:

```text
Python arithmetic and Decimal
SymPy symbolic equivalence
constraint solving
dimensional analysis
numerical residual checks
finite-domain exhaustive checks
repository test execution through existing governed paths
```

Add causal records:

```text
CausalNode
CausalEdge
Intervention
Counterfactual
```

Distinguish observational association from intervention:

```text
P(Y | X) is not P(Y | do(X)).
```

Require causal claims to identify confounders, mediators, moderators, temporal
ordering, intervention assumptions, and alternative explanations.

### Tests

```text
test_symbolic_equivalence_uses_adapter_result
test_numerical_residual_has_declared_tolerance
test_dimensional_mismatch_rejects_equation
test_finite_domain_counterexample_is_recorded
test_correlation_does_not_imply_intervention
test_confounder_blocks_high_confidence_causal_claim
test_adapter_failure_remains_explicit_uncertainty
```

### Exit gate

Mathematical and causal claims use deterministic checks where available and
fail closed when an adapter is unavailable or inconclusive.

## SR-10: Qualification and Release Evidence

**Dependencies:** SR-0 through SR-9 as applicable.

### Work

Run matched comparisons:

```text
A = base model
B = governed OIEC without SR
C = OIEC-SR
```

Use at least 100 held-out examples per required class:

```text
logic
mathematics
programming/debugging
scientific inference
causal reasoning
adversarial reasoning
```

Measure:

```text
accuracy
calibration
evidence coverage
counterexample detection
unsupported empirical claims
reasoning cost
token and tool efficiency
failure recovery
blind retries
certificate reproducibility
wall time
```

Run ablations:

```text
one path only
without hypothesis state
without verifier
without falsifier
without diversity filter
without synthesis verification
without adaptive compute
full SR
```

### Initial qualification targets

```text
difficult-task accuracy gain >= 10 percentage points over base
counterexample detection >= 90 percent
blind retries = 0
unsupported empirical claims in SOLUTION certificates = 0
identical canonical-state certificate reproducibility = 100 percent
```

Report confidence intervals and task-level failures. Do not hide regressions
behind aggregate averages.

### Exit gate

Publish a frozen qualification bundle containing benchmark inputs, exact
configuration, source and artifact hashes, raw results, statistical comparison,
ablation results, token/cost comparison, failure taxonomy, and reproducibility
run. Only then may release documentation describe OIEC-SR as delivering measured
reasoning improvement.

## 7. Integration Contracts

### 7.1 IURM

OIEC-SR supplies unresolved hypotheses and candidate discriminating operations.
IURM remains the owner of controlled variation. Experiment selection should
maximize expected discrimination and goal gain divided by bounded risk and cost.

The selected experiment must name:

```text
hypotheses discriminated
dimension varied
dimensions held invariant
expected observations
evidence atoms produced
risk and cost estimates
stopping condition
```

### 7.2 CFEL

CFEL maps failed predictions and observations to the responsible hypothesis,
step, evidence atom, contradiction, and attempted action. Severity selects one
of:

```text
REVERIFY
REFALSIFY
REGENERATE
EPISTEMIC_STOP
```

Existing support evidence remains append-only. Revision changes the active
projection, not history.

### 7.3 EON

An SR-bound EON action must include:

```text
reasoning certificate signature
winning path ID
synthesis signature when used
current problem hash
current boundary signature
current dimension signature
score configuration hash
```

EON must recompute these identities and continue to enforce exact targets,
snapshot, candidate hash, risk, evidence, approval, expiry, and use limits.

### 7.4 Provider abstraction

Keep `create_responses()` as the required bounded primitive. Add an optional
typed candidate helper that accepts role, count, strategy, and diversity seed.
Fallback order is:

1. provider-specific `create_candidates()` when implemented;
2. bounded ordered `create_responses()`;
3. sequential `create_response()` calls.

Every request still receives empty mutation tools and the normal context,
timeout, output-token, sample, and transport-retry limits.

## 8. Benchmark Integrity Rules

1. Separate development tasks from held-out qualification tasks.
2. Content-address every task and oracle.
3. Record prompt templates and role instructions by hash.
4. Keep model, context, decoding, tool access, source snapshot, and hardware
   fixed across A/B/C comparisons.
5. Randomize task order deterministically when order effects matter.
6. Record failures and timeouts as results, not missing data.
7. Prevent benchmark answers from entering provider context.
8. Report per-category and aggregate metrics.
9. Use paired statistical comparisons for identical task sets.
10. Keep qualification reports append-only; supersede rather than rewrite.

## 9. Requirement-to-Evidence Matrix

| Requirement | Primary owner | Required evidence |
| --- | --- | --- |
| Bounded hypothesis count | `hypotheses.py` | property tests and persisted limit |
| Fixed-point updates | `hypotheses.py` | normalization and replay tests |
| Grounded topology | `topology.py` | cycle, evidence, trace, connectivity tests |
| Four diverse paths | `generator.py`, `search.py` | structural similarity tests |
| Independent verification | `verifier.py` | weakest-step and confidence-isolation tests |
| Dedicated falsification | `falsifier.py` | counterexample and alternative tests |
| Deterministic ranking | `scoring.py` | score-config and tie-break tests |
| Verified synthesis | `synthesis.py`, `verifier.py` | invention and re-verification tests |
| Bounded compute | `budget.py` | token/tool/path/pass cap tests |
| VOI stopping | `budget.py`, `kernel.py` | no-value stop and deterministic choice tests |
| Contradiction blocking | `contradictions.py` | severity/confidence/terminal-state tests |
| Replayable certificate | `certificate.py` | identical-input signature tests |
| Runtime migration | `persistence.py` | v1/v2/v3 to v4 migration tests |
| EON integrity | `agent.py`, `models.py` | stale/tampered certificate tests |
| CFEL learning | `cfel.py`, `hypotheses.py` | prediction-to-update tests |
| Mathematical verification | `adapters/` | oracle-specific deterministic tests |
| Causal discipline | `adapters/causal.py` | confounding/intervention tests |
| Measured gain | benchmark harness | frozen A/B/C comparison and ablations |

## 10. Execution Order

The critical path is:

```text
SR-0 baseline
  -> SR-1 hypothesis state
  -> SR-2 topology v2
  -> SR-3 structural multi-path diversity
  -> SR-4 verifier v2
  -> SR-5 falsifier v2
  -> SR-6 ranking and verified synthesis
  -> SR-7 adaptive compute/context/VOI
  -> SR-8 certificates/contradictions/GUI
  -> SR-9 deterministic adapters
  -> SR-10 qualification
```

The recommended first implementation tranche is **SR-0 through SR-3**. It
creates the missing measurement baseline, canonical hypothesis set, stronger
reasoning graph, and true structural path diversity. Do not begin adapters,
causal reasoning, or release claims before this tranche is benchmarked.

## 11. Validation Strategy

For every milestone:

1. run the smallest changed-module tests;
2. run all reasoning tests;
3. run OIEC, provider, persistence, CLI, GUI, and docs compatibility tests;
4. run `python3 -m compileall -q ourd ourd_gui tools tests benchmarks`;
5. run the complete discoverable `unittest` suite;
6. rebuild generated docs when public types or fields change;
7. validate JavaScript, SVG XML, links, anchors, duplicate IDs, and deterministic
   documentation digest;
8. run `git diff --check`;
9. audit every milestone requirement against a named test or artifact.

Suggested commands:

```bash
python3 -m unittest discover -s tests/reasoning -t . -v
python3 -m unittest tests.test_oiec tests.test_persistence tests.test_provider -v
python3 -m unittest discover -v
python3 -m compileall -q ourd ourd_gui tools tests benchmarks
node --check docs/assets/site.js
git diff --check
```

Benchmark commands must write to a new content-addressed run directory and must
never overwrite the accepted baseline.

## 12. Risks and Countermeasures

| Risk | Countermeasure |
| --- | --- |
| Multi-path outputs are paraphrases | Structural similarity and duplicate collapse |
| Model sets its own budget | Clamp against deterministic OIEC/provider configuration |
| Verifier repeats proposer bias | Separate role request and ignore proposer confidence |
| Synthesis invents unsupported claims | Source-node binding plus mandatory re-verification |
| More compute lowers quality | VOI stopping and benchmarked cost/quality curves |
| Benchmark leakage | Held-out task store and content-addressed prompt/task hashes |
| Provider nondeterminism hides regressions | Exact configuration, repeated runs, confidence intervals |
| New state breaks old workspaces | Append-only v3 to v4 migration and compatibility projections |
| Certificate becomes authority | EON and policy remain independent mandatory gates |
| Contradictions are silently averaged away | First-class records and high-severity convergence block |
| Optional adapter failure becomes false proof | Explicit inconclusive result and retained uncertainty |
| GUI accidentally mutates reasoning state | Read-only projections and import-safety tests |
| Large test refactor loses coverage | Split tests incrementally with assertion-count audit |
| “Super reasoning” becomes a marketing claim | SR-10 comparative qualification release gate |

## 13. Definition of Implementation Complete

OIEC-SR v1.0 implementation is complete only when:

- SR-0 through SR-8 are implemented and fully validated;
- SR-9 adapters selected for v1.0 are either implemented or explicitly scoped
  out with retained uncertainty;
- RuntimeState v4 migrations preserve the hash-chained event history;
- hypothesis, contradiction, topology, candidate, synthesis, budget, and
  certificate signatures are reproducible from canonical inputs;
- no accepted empirical conclusion lacks evidence or an explicit assumption;
- no synthesis is accepted without another verifier pass;
- no provider or model can expand authority or compute limits;
- no unchanged failed attempt is automatically repeated;
- EON remains the only mutation path;
- focused, compatibility, full-suite, packaging, GUI, and generated-doc gates
  pass from the same final source snapshot;
- the requirement-to-evidence matrix has no unsupported mandatory row.

## 14. Definition of Release Qualified

Implementation completion does not authorize the phrase “super reasoning” as a
measured product claim. Release qualification additionally requires SR-10:

- frozen base, OIEC, and OIEC-SR benchmark results;
- at least 100 held-out examples per required task class;
- statistical and cost comparisons;
- failure taxonomy;
- all specified ablations;
- reproducibility run;
- exact source and artifact hashes;
- human review of the qualification evidence;
- explicit release approval.

Until that gate passes, documentation should say:

> OIEC-SR implements bounded multi-hypothesis reasoning and is undergoing
> comparative qualification.

It should not claim proven general reasoning superiority.

## 15. Immediate Next Actions

1. Freeze the current 282-test SR foundation as the SR-0 implementation baseline.
2. Add `benchmarks/reasoning/schema.json`, task schema tests, and a deterministic
   fixture runner.
3. Create representative development tasks in all required categories.
4. Generate `baseline-v1.json` for base, governed OIEC, and current OIEC-SR.
5. Review the baseline failure taxonomy before changing reasoning algorithms.
6. Begin SR-1 only after the SR-0 exit gate is satisfied.

The first decision checkpoint is therefore evidence-driven: benchmark the
existing four-path implementation before adding more search, more models, or
specialized adapters.
