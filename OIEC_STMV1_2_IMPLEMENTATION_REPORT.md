# OIEC-STMv1.2 Implementation Report

**Product:** OIEC-STM-Agent
**Implementation date:** August 28, 2026
**License:** MIT

## Result

OIEC-STMv1.2 is implemented as a thin deterministic control layer over the
existing governed agent architecture. It does not replace authority, evidence,
policy, EON transactions, CFEL records, or the executor. The implementation
adds a bounded pre-action and post-observation transition model while retaining
the existing rule that deterministic code and human authority outrank model
claims.

The six executable primitives are:

- `BoundaryState`
- `DimensionBudget`
- `FiniteEvidenceState`
- `AttemptKey`
- `ProgressCertificate`
- `BoundedTransitionKernel`

The repository and distribution are renamed to **OIEC-STM-Agent**. Canonical
commands are `oiec-stm-agent` and `oiec-stm-gui`. The `ourd` package,
`.ourd-agent/` state directory, `OURD_*` environment variables, `ourd-agent`,
`ourd-gui`, and `ourd_agent.py` remain compatibility interfaces.

## Architectural Integration

`ourd/models.py` owns the durable OIEC records beside `AuthorityManifest`,
`GovernanceRecord`, `EvidenceArtifact`, `EONAction`, `CollisionRecord`, and
`RuntimeState`. `RuntimeState` schema 2 adds the current boundary, dimension,
finite-evidence, progress, and transition projections without replacing the
append-only evidence registry, collisions, failed attempts, transactions, or
pending action.

`ourd/oiec.py` owns pure deterministic construction and transition functions.
Its `BoundedTransitionKernel` has no subprocess, shell, filesystem-write, or
transaction-apply method. It derives and validates state, creates a prepared
transition, measures collision severity, and accepts only observations with a
valid progress certificate.

`ourd/agent.py` invokes the kernel immediately before the existing transaction
apply and governed-command paths. The agent persists OIEC projections and
passes the pre-action attempt identity into CFEL when a significant collision
occurs. The transaction manager and command executor remain the only mutation
paths.

`ourd/policy.py` remains authoritative for L0, L1, and L2 risk floors. OIEC adds
boundary and dimension checks but cannot lower effective risk. `ourd/cfel.py`
retains the human-readable collision fingerprint and can additionally register
the stronger pre-action `AttemptKey`.

## Deterministic Control State

All operational scores use integer basis points from `0` through `10000`.
Canonical identities use sorted compact JSON encoded as UTF-8 and hashed with
SHA-256. Timestamps and UUIDs are excluded from deterministic signatures.

`BoundaryState` binds the human authority hash, exact source snapshot,
governance objects and relations, authority scope, governance scope,
experimental dimensions, membership scores, and boundary uncertainty. A
concrete target must independently satisfy both authority and governance.
Semantic relevance cannot enlarge operational authority.

`DimensionBudget` bounds active objects, relations, dimensions, hypotheses,
quantization levels, interaction order, candidate actions, evidence atoms,
decomposition depth, branch factor, and retries. Dimension ranking uses fixed
integer utility and lexical tie-breaking. Normal IURM operation permits one
varied dimension at a time.

`FiniteEvidenceState` is an action-scoped projection over a finite atom
universe. Presence and conflict are monotonic bit masks. Quality can only stay
equal or increase, and equal-quality representatives use lexical artifact-ID
tie-breaking. The durable evidence registry remains append-only and unbounded
as audit history.

`AttemptKey` binds the exact source snapshot, EON action ID, action-relevant
evidence signature, boundary signature, and dimension signature. Unrelated
evidence and changed prose do not unlock a failed attempt. A materially changed
snapshot, action, relevant evidence set, boundary, or dimension state creates a
different key.

`ProgressCertificate` does not treat a novel action as progress by itself. It
accepts a transition only for novel evidence with positive evidence gain,
material goal improvement, material residual-risk reduction, boundary
resolution, a discriminating experiment with sufficient expected information,
or a terminal stop. New evidence may reveal hidden uncertainty and still
constitute progress.

## Persistence Migration

Runtime schema 1 migrates to schema 2 by rebuilding the old projection,
supplying backward-compatible OIEC defaults, and appending a new hash-chained
state snapshot. Existing event entries are not rewritten. Unknown runtime
schemas and broken event chains fail closed.

`EvidenceArtifact` now supports requirement IDs, fixed-point quality, and
support, counterexample, or conflict polarity. `EONAction` records varied
dimensions. `CollisionRecord` can record fixed-point severity and the OIEC
attempt, boundary, and dimension identities.

## Machine-Checked Properties

`tests/test_oiec.py` verifies the requested boundary, dimension, evidence,
retry, progress, persistence, and kernel properties. It also includes exhaustive
small-state reachability and cycle tests for boundedness, monotonic evidence,
no-blind-retry behavior, and conditional convergence.

The verified invariants include:

- every accepted target is inside authority and governance;
- every varied dimension is admitted by the deterministic budget;
- interaction order is bounded;
- the EON source snapshot matches the prepared state;
- the action-scoped evidence universe is finite;
- unchanged exhausted attempts are blocked before execution;
- autonomous non-terminal continuation requires progress;
- OIEC cannot enlarge authority or lower the policy risk floor; and
- identical canonical inputs produce identical OIEC signatures and verdicts.

## Corrected Issues

Implementation and validation exposed and corrected these issues:

1. Empty established governance scope was initially rejected while deriving a
   boundary. It now represents a valid fail-closed read-only boundary, while
   every concrete mutation target remains blocked.
2. The package initially exposed only the historical OURD launchers. The build
   backend, wheel metadata, source distribution, tests, README, CLI, and GUI now
   expose canonical OIEC-STM-Agent names while preserving old aliases.
3. Renaming source documentation invalidated generated source hashes. The
   documentation site was regenerated and its manifest tests now bind the new
   source bytes.
4. The earlier implementation report described a standalone transition core
   and stale test counts. This report now describes the integrated v1.2 design
   and current validation evidence.
5. External EGCF algorithm registration previously refused safe reference-only
   definitions. It now permits non-executable `reference` records while still
   rejecting privileged executors, callbacks, shell markers, and self-certified
   definitions.
6. The BAB-CS importer now handles safe literal and set-union expressions
   without importing or executing external code, produces deterministic
   artifact identities, and preserves the external dirty worktree.

## BAB-CS Reference Receipt

The related BAB-CS work is retained as a reference-only EGCF algorithm:

- Algorithm ID: `reference.babcs.bounded-integrator@1`
- Definition ID: `algorithm-definition:sha256:a601e0df9528a44cb205ff9cae3025ea6a316a03afe58ac5c9bd0506d2ff3cf7`
- Source bundle SHA-256: `b85f1faa728fc39292f45dacabeb0a86d23e644f70004df362acad0400748e8a`
- Source license: MPL-2.0
- Receipt: `BABCS_ALGORITHM_STORE_RECEIPT.json`
- Analysis: `BABCS_ALGORITHM_STORE_ANALYSIS_REPORT.md`

The reference remains `PROPOSED` and cannot grant authority or execute BAB-CS.
Its focused receipt records `36` passing bounded-integrator tests. This is not
full BAB-CS qualification or release certification.

## Validation Evidence

Full renamed-source discovery:

```text
python3 -m unittest discover -s tests -v
Ran 234 tests in 820.104s
OK
```

Additional checks passed:

- Python bytecode compilation for `ourd`, `ourd_gui`, both launchers, and the
  documentation generator;
- `node --check docs/assets/site.js`;
- `git diff --check`;
- headless GUI startup and clean close with
  `xvfb-run -a python3 -m ourd_gui --repo . --smoke-test`;
- wheel and source-distribution construction using the repository build backend;
- archive inspection for the OIEC-STM-Agent metadata, canonical entry points,
  compatibility entry points, GUI package, and canonical launcher; and
- source-derived documentation manifest, essay, concept, SVG, and JavaScript
  interaction tests.

## Limits

- Passing tests are deterministic implementation evidence, not human approval,
  certification, or release authority.
- OIEC numeric risk is telemetry and cannot replace the L0/L1/L2 policy model.
- The kernel cannot execute commands or mutate repository files.
- Compatibility state paths and internal protocol source names intentionally
  retain OURD identifiers.
- The BAB-CS artifact remains governed by its MPL-2.0 license and is not
  relicensed by this MIT repository.
- No claim is made that finite active control state makes the append-only audit
  history finite.
