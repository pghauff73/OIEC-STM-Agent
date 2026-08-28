# OIEC-STMv1.2 Implementation Plan

## Objective

Implement OIEC-STMv1.2 as a deterministic control layer over the existing
OURD coding-agent architecture. The layer must bound active reasoning state,
scope every concrete target through both human authority and established
governance, prevent blind repetition with a pre-action epistemic identity, and
require machine-checkable progress after observation.

OIEC does not replace or duplicate:

- `AuthorityManifest` or authority validation;
- `GovernanceRecord` or OURD problem decomposition;
- `EvidenceArtifact` or the durable evidence registry;
- `EONAction` or exact candidate/action identity;
- `PolicyEngine.effective_risk()` or deterministic risk floors;
- the existing evidence gate;
- `TransactionManager` or command execution; or
- the append-only event chain.

The `BoundedTransitionKernel` must never execute a subprocess or write a
repository file.

## Architecture

```text
GovernanceRecord + AuthorityManifest + exact snapshot
                         |
                         v
                  BoundaryState
                         |
                         v
                  DimensionBudget
                         |
                         v
            action-scoped FiniteEvidenceState
                         |
                         v
                   AttemptKey
                         |
                         v
      PolicyEngine + existing evidence gate + EON
                         |
                 BLOCK or PREPARE
                         |
               existing environment path
                         |
                     observation
                         |
                   CFEL collision
                         |
               ProgressCertificate
                         |
                 ACCEPT or STOP
```

## Canonical ownership

| File | Additive responsibility |
| --- | --- |
| `ourd/models.py` | Durable OIEC dataclasses and runtime projection fields |
| `ourd/oiec.py` | Fixed-point algorithms and pure two-phase kernel |
| `ourd/policy.py` | Boundary and dimension checks delegated from OIEC |
| `ourd/cfel.py` | Collision severity metadata and `AttemptKey` registration |
| `ourd/persistence.py` | Runtime schema v1 to v2 migration and serialization |
| `ourd/agent.py` | Preflight integration at existing apply/command edges |
| `tests/test_oiec.py` | Deterministic, migration, integration, and proof tests |

## Phase 1: Durable primitives

Add the six required primitives with backward-compatible defaults:

1. `BoundaryState`
2. `DimensionBudget`
3. `FiniteEvidenceState`
4. `AttemptKey`
5. `ProgressCertificate`
6. `BoundedTransitionKernel`

Use `SCORE_SCALE = 10_000` for all control-state quantities. Preserve the
authoritative `L0`, `L1`, and `L2` risk classes.

Extend existing records additively:

- `EvidenceArtifact.requirement_ids`
- `EvidenceArtifact.quality_bp`
- `EvidenceArtifact.polarity`
- `EONAction.varied_dimensions`
- `CollisionRecord.severity_bp`
- `CollisionRecord.attempt_key`
- `CollisionRecord.boundary_signature`
- `CollisionRecord.dimension_signature`

Extend `RuntimeState` with:

- `boundary_state`
- `dimension_budget`
- `finite_evidence`
- `last_progress`
- `transition_index`

Do not remove or reinterpret the durable evidence registry, collisions,
failed-attempt map, transactions, pending action, or gate decision.

## Phase 2: Boundary determination

Build `BoundaryState` from the exact authority hash, exact source snapshot,
semantic objects and relations, authority patterns, governance patterns,
experimental dimensions, and fixed-point membership values.

For each concrete target:

1. canonicalize it through `Workspace`;
2. require authority allowed scope;
3. reject authority forbidden scope;
4. require governance allowed scope; and
5. reject governance excluded scope.

Do not synthesize an approximate wildcard intersection. Semantic expansion
must never enlarge operational authority. Empty governance scope is a valid
fail-closed state; it is rejected only when a mutation target is proposed.

## Phase 3: Dimension limiting

Derive a finite `DimensionBudget` independently of boundary membership.
Deterministically rank dimensions by descending fixed-point utility and lexical
name as the final tie-break.

Enforce:

- active-object and active-relation caps;
- active-dimension and hypothesis caps;
- quantization-level cap;
- evidence-atom cap;
- candidate-action cap;
- decomposition and branch caps;
- interaction order; and
- retries capped by both OIEC configuration and human authority.

The default interaction order is one.

## Phase 4: Finite evidence projection

Keep the durable evidence registry append-only. Project only evidence atoms
relevant to the current action's evidence requirements and exact required test
commands.

For every atom:

- presence is monotonic;
- conflict is monotonic;
- quality is non-decreasing; and
- equal-quality representatives use lexical artifact ID tie-breaking.

Irrelevant evidence must not change the action-scoped evidence signature.
Overflow must fail closed rather than discard earlier evidence.

## Phase 5: Attempt identity and CFEL

Construct `AttemptKey` from:

```text
exact current snapshot
exact EON action ID
action-scoped finite evidence signature
boundary signature
dimension signature
```

Register the attempt key only for a significant collision. Preserve the
existing observation-oriented CFEL fingerprint for readable collision
identity and compatibility.

The retry rule is:

```text
failed_count > min(OIEC retry cap, authority retry cap) => BLOCK
```

Changing prose or unrelated evidence cannot unlock a retry.

## Phase 6: Two-phase kernel integration

`prepare()` performs only deterministic checks and projections:

1. verify the current snapshot;
2. verify action authority binding;
3. derive BD;
4. derive DL;
5. enforce finite state caps;
6. verify all targets through `PolicyEngine`;
7. verify all varied dimensions through `PolicyEngine`;
8. recompute the authoritative risk floor;
9. require the existing evidence gate for L1/L2;
10. project action-scoped evidence;
11. construct `AttemptKey`; and
12. enforce retry budget.

Integrate this preflight immediately before:

- `TransactionManager.apply()`; and
- governed `subprocess.run()` calls.

Preserve the existing transaction lifecycle in which verification commands run
against the exact applied snapshot. The direct kernel remains strict by
default; the agent may supply the transaction's recorded
`applied_snapshot_hash` only after `TransactionManager.verify_applied()` proves
that exact state.

## Phase 7: Observation and progress

`accept_observation()` must:

1. compare evidence mass before and after;
2. register significant failed attempts;
3. compute a fixed-point `ProgressCertificate`;
4. reject non-terminal no-progress transitions;
5. recompute BD and DL after accepted evidence; and
6. persist the new projections and transition index.

Novel action identity alone is not progress. Valid reasons are:

- novel evidence with positive evidence gain;
- material goal improvement;
- material residual-risk reduction;
- material boundary resolution;
- a discriminating experiment with sufficient expected information gain; or
- a terminal stop.

## Phase 8: Persistence migration

Advance `RuntimeState` from schema 1 to schema 2.

Migration procedure:

1. read the latest valid v1 projection from state or event replay;
2. add only backward-compatible defaults;
3. construct and validate a v2 `RuntimeState`;
4. append a new hash-chained `state_snapshot` carrying migration metadata; and
5. atomically write the v2 projection.

Never rewrite old event entries. Reject unknown runtime schema versions.

## Phase 9: Test and proof layer

Implement the requested test families:

- boundary composition and fixed-point uncertainty;
- deterministic dimension limiting and interaction order;
- evidence monotonicity, conflicts, projection, and overflow;
- pre-action retry identity and relevant-evidence behavior;
- progress certification;
- deterministic signatures and no workspace mutation;
- policy-risk supremacy;
- runtime v1 to v2 migration;
- real agent apply integration;
- CFEL attempt-key registration; and
- exhaustive small-state reachability, cycle, monotonicity, and conditional
  convergence checks.

## Compatibility countermeasures

1. **Empty governance scope**: allow construction but block every concrete
   mutation target.
2. **Post-apply verification**: require the transaction's exact recorded
   applied snapshot rather than weakening snapshot checks.
3. **Existing CFEL callers**: preserve fingerprint-based counting when no OIEC
   key is available.
4. **Existing evidence records**: migrate missing requirement, quality, and
   polarity fields to deterministic defaults.
5. **Existing EON callers**: default `varied_dimensions` to an empty list.
6. **Historical state**: append a migration snapshot; do not mutate history.
7. **Risk estimates**: allow OIEC telemetry only to preserve or raise the
   existing effective risk, never lower it.

## Completion gates

Implementation is complete only when all of the following hold:

- the six required primitives are importable from canonical modules;
- runtime schema v2 round-trips and v1 migration is hash-chain preserving;
- existing action, authority, policy, persistence, provider, GUI, EGCF, and
  documentation tests remain green;
- the complete discoverable `unittest` suite passes from the current source;
- `compileall`, JavaScript syntax, SVG parsing, local-link validation, and
  `git diff --check` pass;
- generated documentation is rebuilt from the final source; and
- the report distinguishes implementation evidence from human approval,
  certification, and release.
