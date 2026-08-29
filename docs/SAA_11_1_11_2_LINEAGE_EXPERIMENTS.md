# SAA-11.1 and SAA-11.2: Adaptation lineage and controlled comparative experiments

## Purpose

SAA-11 introduced controlled algorithm adaptation from explicit SAA-10.3 fit gaps.
It established the rule that canonical algorithms are never mutated in place and that one declared adaptation dimension may change per candidate step.

SAA-11.1 and SAA-11.2 make those changes historically traceable and experimentally comparable.

```text
qualified canonical algorithm
        ↓
SAA-10.3 fit delta
        ↓
SAA-11 one-dimension adaptation
        ↓
unqualified candidate
        ↓
SAA-11.1 lineage registration
        ↓
SAA-11.2 controlled A/B experiment
        ↓
comparison result
        ↓
normal qualification gates
        ↓
optional canonical promotion
```

The governing distinction is:

```text
adapted from != better than != canonically qualified
```

Each proposition requires a separate artifact.

## SAA-11.1: persistent adaptation lineage

`AdaptationLineageStore` persists the evolutionary graph of algorithm candidates.

A candidate reference has the form:

```text
adapted-candidate:sha256:<candidate_signature>
```

The first generation points to the canonical algorithm from which adaptation started.
Later generations point to their immediate adapted parent.

```text
Canonical A
   │
   │ ADAPTED_FROM: DYNAMICS_CONTRACT
   ▼
Candidate A1
   │
   │ ADAPTED_FROM: BOUNDARY_CONTRACT
   ▼
Candidate A2
```

The edge binds:

- parent reference;
- child reference;
- original canonical base algorithm;
- mathematical or reasoning component;
- exactly one changed dimension;
- originating SAA-11 adaptation-step signature;
- originating SAA-10.3 explanation signature;
- child candidate signature;
- optional parent-candidate signature.

Therefore a lineage edge is not a free-form historical note. It is an exact derivation artifact.

### Lineage identity

The edge signature is derived from:

```text
Hash(
  parent,
  child,
  base algorithm,
  component,
  changed dimension,
  adaptation step,
  retrieval explanation
)
```

Display prose and timestamps are not part of the candidate's SAA-11 identity.

### Bounded ancestry

Lineage traversal is capped by `MAX_LINEAGE_DEPTH`.
Stored cycles are rejected.
A later-generation candidate cannot name an unregistered candidate as its parent.

This prevents malformed history such as:

```text
A1 -> A2 -> A1
```

or:

```text
unknown candidate -> A4
```

from becoming accepted evolutionary structure.

### Canonical promotion is separate

A candidate can later be associated with a canonical mathematical or reasoning algorithm using an `AdaptationPromotionRecord`.

Promotion requires:

- a registered adapted candidate;
- a canonical mathematical or reasoning target reference;
- an external qualification signature;
- successful non-simulated grounded evidence;
- deterministic or human evidence production.

The promotion record does not perform qualification itself.
It records that the normal qualification machinery has produced a canonical descendant.

```text
Candidate A2
    │
    │ qualified externally
    ▼
Canonical B
```

This preserves the rule:

```text
SAA-11 candidate creation cannot self-promote.
```

### Immutable persistent graph

The adaptation store maintains immutable objects for:

- candidates;
- lineage edges;
- promotions;
- experiment designs;
- experiment results.

SQLite tables are rebuildable indexes only.
The persistent content-addressed files are authoritative.

Indexes include:

- base algorithm;
- changed dimension;
- parent and child references;
- promotion source;
- experiment candidate;
- experiment context;
- result status.

A projection rebuild must recover the same ancestry and experiment records.

## SAA-11.2: controlled A/B algorithm experiments

SAA-11.2 answers a different question from lineage:

> Did the controlled adaptation produce a measurable improvement under the declared experiment contract?

An experiment has one baseline and one candidate.
The candidate must be a descendant of the baseline in SAA-11.1 lineage.

```text
baseline ─────┐
              ├── same experiment context ──> comparison
candidate ────┘
```

An unrelated candidate cannot be compared under a lineage claim that it does not actually possess.

## Experiment design

`AlgorithmABExperimentDesign` binds:

- baseline reference;
- candidate reference;
- exact context signature;
- bounded metric set;
- metric directions;
- minimum material effects;
- required invariants;
- evidence requirements;
- minimum trial count;
- paired-context policy.

The context signature is intentionally explicit.
An improvement proven in one environment is not automatically an improvement in another environment.

## Exact metrics

Experiment metrics use exact rational values.
Floats are not accepted for canonical comparison identity.

Examples:

```text
error = 1/20
throughput = 103
energy_per_operation = 7/10
```

A metric declares one of:

```text
HIGHER_IS_BETTER
LOWER_IS_BETTER
```

and an exact `minimum_material_effect`.

This prevents tiny numerical differences from automatically becoming semantic improvement claims.

For a higher-is-better metric:

```text
signed improvement = candidate - baseline
```

For a lower-is-better metric:

```text
signed improvement = baseline - candidate
```

A metric becomes `MATERIAL_IMPROVEMENT` only when the signed benefit is positive and at least the declared material-effect threshold.

A sufficiently negative effect is `MATERIAL_REGRESSION`.
Anything inside the material-effect band is `NO_MATERIAL_CHANGE`.

## Evidence gate

Both baseline and candidate observations require registered `EvidenceArtifact` records.

Accepted evidence must be:

```text
success == True
simulated == False
producer starts deterministic- or human-
method != reported
```

Every side of the comparison must cover the experiment's declared evidence requirements.

The result records:

- grounded evidence IDs;
- independence groups;
- evidence-requirement coverage;
- invariant gate status;
- independent-review status.

A benchmark number without grounded evidence cannot qualify an improvement.

## Invariant gate

Every required invariant must hold for both variants.

If candidate performance improves while a required safety/correctness invariant fails, the result becomes:

```text
EXPERIMENT_INVARIANT_VIOLATION
```

rather than improvement.

This prevents optimization from silently trading away required correctness.

## Comparative statuses

Possible top-level results include:

```text
CANDIDATE_IMPROVEMENT_QUALIFIED
CANDIDATE_REGRESSION_DETECTED
EXPERIMENT_TRADEOFF_UNRESOLVED
NO_MATERIAL_IMPROVEMENT
EXPERIMENT_EVIDENCE_INCOMPLETE
EXPERIMENT_INVARIANT_VIOLATION
EXPERIMENT_REVIEW_REQUIRED
EXPERIMENT_EXECUTION_FAILED
```

### Qualified improvement

A candidate is a qualified comparative improvement only when:

```text
Both executions succeeded
AND evidence coverage == 100%
AND required invariants survived on both variants
AND independent review completed
AND at least one metric materially improved
AND no metric materially regressed
```

Formally:

```text
QualifiedImprovement =
    ExecutionA
    AND ExecutionB
    AND EvidenceComplete
    AND InvariantsPreserved
    AND IndependentReview
    AND Exists(MaterialImprovement)
    AND NOT Exists(MaterialRegression)
```

### Tradeoff

If one metric improves while another materially regresses:

```text
EXPERIMENT_TRADEOFF_UNRESOLVED
```

The implementation does not hide that tradeoff inside a weighted scalar score.
A policy layer or new problem objective must explicitly decide whether the tradeoff is acceptable.

### No material improvement

A numerically different candidate can still yield:

```text
NO_MATERIAL_IMPROVEMENT
```

when differences remain inside the declared material-effect thresholds.

This implements the intended distinction:

```text
change != progress
```

## A/B qualification is not canonical qualification

Even a result with:

```text
candidate_improvement_qualified == True
```

still carries:

```text
qualification_required_before_canonical_reuse == True
```

The experiment proves a bounded comparative claim.
It does not prove all mathematical, semantic, reasoning, authority, domain, or store-admission contracts required elsewhere in SAA.

The candidate must still return through the relevant canonical qualification pipeline.

## Epistemic graph

The resulting knowledge graph can distinguish:

```text
Canonical A
   │
   │ ADAPTED_FROM
   ▼
Candidate A1
   │
   ├── EXPERIMENT: no material improvement
   │
   └── further adaptation
         ▼
      Candidate A2
         │
         ├── EXPERIMENT: qualified improvement
         │
         └── external qualification
                ▼
            Canonical B
```

This graph is more informative than a simple version history because it separates:

- derivation;
- experimental comparison;
- canonical qualification.

## Why this matters for intelligence growth

Without SAA-11.1, OIEC could generate successive variants without being able to reconstruct exactly how its current method arose.

Without SAA-11.2, OIEC could mistake adaptation activity for improvement.

Together they create:

```text
KnownAlgorithm
  -> MeasuredGap
  -> OneDimensionChange
  -> PersistentLineage
  -> ControlledExperiment
  -> EvidenceBasedComparison
```

That is the foundation required before a closed improvement loop can safely prefer descendants over ancestors.

## Claim boundaries

SAA-11.1 does not claim:

- that an adapted descendant is better;
- that a candidate is canonically qualified;
- that later versions supersede earlier ones merely because they are newer.

SAA-11.2 does not claim:

- global superiority outside the experiment context;
- causal attribution beyond the bounded one-dimension adaptation and experiment design;
- automatic canonical admission;
- that a tradeoff is an improvement;
- that repeated experiments are independent unless their evidence actually is.

## Next milestones

The next logical milestones are:

### SAA-11.3: multi-step adaptation with invariant preservation

Permit bounded sequences of individually qualified adaptation steps while proving that unchanged dimensions and required invariants remain stable across the chain.

### SAA-11.4: comparative evidence aggregation

Combine repeated experiments only when contexts, independence groups, metric semantics, and evidence scopes are compatible.

### SAA-12: closed qualified intelligence-improvement loop

Integrate:

```text
retrieve
-> explain gap
-> adapt
-> experiment
-> qualify
-> promote/store
-> retrieve improved descendant next time
```

### SAA-12.1: failed-algorithm algebra

Make failed and regressed descendants first-class searchable knowledge so the system recognizes structurally repeated dead ends.

### SAA-12.2: OIEC-Bench admission gate

Use longitudinal benchmark evidence as an external qualification source for claims that the accumulated algorithm/reasoning system is becoming more reliable.
