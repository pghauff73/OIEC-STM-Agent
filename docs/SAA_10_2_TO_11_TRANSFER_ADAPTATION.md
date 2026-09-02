# SAA-10.2 through SAA-11: Transfer, explainable fit and controlled adaptation

## Purpose

SAA-10 established federated retrieval across the qualified mathematical Algorithm Store and Canonical Reasoning Store. SAA-10.1 made retrieve-before-generate an explicit production policy.

SAA-10.2 through SAA-11 extend that policy from retrieval into controlled reuse and improvement:

```text
qualified known algorithm
        ↓
SAA-10.2 transfer assessment
        ↓
SAA-10.3 deterministic fit / transfer explanation
        ↓
explicit delta
        ↓
SAA-11 controlled one-dimension adaptation
        ↓
unqualified adapted candidate
        ↓
existing evidence / semantic / algorithm qualification gates
```

The governing principle is:

> A known algorithm may be reused in a new context only to the extent that its qualified contracts survive the context change. Any difference becomes an explicit fit gap. Adaptation may change only those gaps and never silently mutate canonical knowledge.

## SAA-10.2: Evidence-bounded cross-domain algorithm transfer

Semantic equivalence is necessary for algorithm transfer, but it is not sufficient.

Two domains can use the same concept while differing in:

- operating boundaries;
- invariants;
- dynamics;
- qualification evidence;
- evidence scope.

`AlgorithmDomainContract` therefore binds:

```text
domain
input semantic concepts
invariants
boundary signatures
dynamics signature
evidence requirements
qualification evidence signatures
evidence scope signature
```

### Transfer qualification

Given a source contract `S` and target contract `T`, SAA-10.2 independently checks:

```text
SemanticMatch(S,T)
BoundaryMatch(S,T)
InvariantMatch(S,T)
DynamicsMatch(S,T)
EvidenceMatch(S,T)
```

Exact transfer is permitted only when:

```text
SemanticMatch
AND BoundaryMatch
AND InvariantMatch
AND DynamicsMatch
AND EvidenceMatch
```

which produces:

```text
EXACT_TRANSFER_CONTRACT_MATCH
transfer_without_requalification = True
```

The human-readable domain name is not itself an equivalence criterion. A transfer from one named domain to another can be exact only when every proof-bearing contract remains the same.

### Evidence continuity

Matching evidence requirement names do not establish evidence continuity.

SAA-10.2 additionally requires:

```text
source qualification evidence signatures
    subset-of
 target qualification evidence signatures

AND

source evidence-scope signature
    ==
target evidence-scope signature
```

If the target domain has not inherited or independently re-established the source proof scope, transfer drops to:

```text
TRANSFER_REQUIRES_DOMAIN_REQUALIFICATION
```

This prevents an algorithm from being moved into a new context merely because both contexts say they require a "test" or "verification".

### Semantic mismatch

If the source and target semantic concepts are not exactly identical or linked by an ontology-qualified exact equivalence, transfer is blocked:

```text
TRANSFER_BLOCKED_SEMANTIC_MISMATCH
```

The mismatch is not treated as an ordinary adaptation dimension. Semantic identity must be resolved through the semantic ontology and evidence process first.

### Adaptable transfer gaps

After semantic identity has been established, differences are emitted as explicit dimensions:

```text
BOUNDARY_CONTRACT
INVARIANT_CONTRACT
DYNAMICS_CONTRACT
EVIDENCE_CONTRACT
```

These are target-domain requalification requirements rather than permission to pretend the original proof already applies.

## SAA-10.3: Deterministic retrieval explanations and counterfactual fit

SAA-10.3 explains SAA retrieval artifacts, not private model reasoning.

`RetrievalExplanation` contains:

```text
selected reasons
rejected reasons
counterfactual contract changes
fit-gap dimensions
source decision signature
explanation signature
```

The explanation is deterministic and derived from explicit fit assessments.

### Mathematical fit gaps

Current mathematical blockers are classified into dimensions such as:

```text
MATHEMATICAL_INPUT_SEMANTICS
MATHEMATICAL_OUTPUT_SHAPE
MATHEMATICAL_DOMAIN
MATHEMATICAL_CONTRACT
```

### Reasoning fit gaps

Reasoning blockers are classified into:

```text
REASONING_INPUT_SEMANTICS
REASONING_OUTPUT_SEMANTICS
REASONING_APPLICABILITY
REASONING_INVARIANTS
REASONING_EVIDENCE_CAPABILITY
REASONING_TERMINATION_BUDGET
REASONING_CONTRACT
```

Confirmed absent components remain explicit:

```text
MISSING_MATHEMATICAL_ALGORITHM
MISSING_REASONING_ALGORITHM
```

### Counterfactual fit

For each rejection, SAA-10.3 records the contract difference that would need to change for the blocker to disappear.

The counterfactual is not a recommendation to falsify the problem requirements. It serves two purposes:

1. explain why a candidate failed;
2. define the smallest admissible delta for SAA-11.

Therefore:

```text
Requirement - CandidateContract = FitDelta
```

is an explicit artifact rather than an informal model judgement.

### Transfer explanation

SAA-10.2 assessments also pass through SAA-10.3.

For example, unchanged semantics and boundaries with changed dynamics becomes:

```text
EXPLAINED_TRANSFER_REQUALIFICATION_DELTA
fit_gap_dimensions = [DYNAMICS_CONTRACT]
```

A semantic mismatch becomes:

```text
EXPLAINED_BLOCKED_TRANSFER
```

and is marked as requiring semantic resolution rather than algorithm adaptation.

### Production retrieve-first receipts

`RetrieveFirstReceipt` now includes:

```text
explanation_signature
fit_gap_dimensions
```

The retrieve-first production agent already surfaces the receipt as system-verified policy state in every model instruction set.

This lets the model see exactly which dimensions are available for adaptation without treating its own rationale as the authority for that scope.

## SAA-11: Controlled algorithm adaptation

SAA-11 converts explicit SAA-10.3 deltas into bounded adaptation candidates.

It deliberately does not mutate canonical algorithms.

Canonical knowledge is immutable:

```text
CanonicalAlgorithm A
        ↓
Measured Fit Delta
        ↓
Adaptation Candidate A'
```

`A'` is a new epistemic object.

### Allowed adaptation dimensions

The initial bounded vocabulary includes:

```text
MATHEMATICAL_INPUT_SEMANTICS
MATHEMATICAL_OUTPUT_SHAPE
MATHEMATICAL_DOMAIN
MATHEMATICAL_CONTRACT
REASONING_INPUT_SEMANTICS
REASONING_OUTPUT_SEMANTICS
REASONING_APPLICABILITY
REASONING_INVARIANTS
REASONING_EVIDENCE_CAPABILITY
REASONING_TERMINATION_BUDGET
REASONING_CONTRACT
BOUNDARY_CONTRACT
INVARIANT_CONTRACT
DYNAMICS_CONTRACT
EVIDENCE_CONTRACT
MISSING_MATHEMATICAL_ALGORITHM
MISSING_REASONING_ALGORITHM
```

Semantic transfer mismatch is intentionally absent. Semantic identity is governed by SAA-9 rather than repaired by algorithm editing.

### One dimension per step

Each `AdaptationStep` contains exactly one declared changed dimension.

The policy is:

```text
A_(n+1) = A_n + Delta_i
```

with all other qualified dimensions treated as invariant for that step.

`create_adapted_candidate` rejects change material that declares additional hidden dimensions.

This implements the IURM-style principle of changing one controlled dimension while preserving the rest of the known solution.

### Candidate identity

Every adapted result receives a new deterministic signature derived from:

```text
base algorithm ID
component type
changed dimension
explicit change material
parent candidate signature
```

The result is always:

```text
epistemic_status = UNQUALIFIED_ADAPTED_ALGORITHM_CANDIDATE
qualification_required = True
canonical_reuse_eligible = False
```

No adaptation operation can certify its own success.

### Qualification path

An adapted mathematical algorithm must return through the applicable SAA representation, semantic and evidence qualification layers before canonical admission.

An adapted reasoning algorithm must return through SAA-8.5 outcome qualification before SAA-8.3 canonical storage.

A target-domain transfer adaptation additionally requires the target-domain evidence contract to be satisfied.

## Claim boundaries

This milestone does not claim:

- that semantic equivalence guarantees algorithm transfer validity;
- that a similar domain has compatible dynamics;
- that matching dimensions prove matching meanings;
- that a counterfactual fit change is automatically desirable;
- that adapting a known algorithm improves it;
- that an adapted candidate is safe or correct before qualification;
- that several fit gaps may be changed together without losing causal attribution.

The cost of false reuse remains higher than the cost of conservative requalification.

## Current SAA pipeline

```text
SAA-1..6.4    canonical mathematical algorithms
SAA-7..7.11   bounded nonlinear representation and proof
SAA-8..8.6    canonical evidence-qualified reasoning algorithms
SAA-9.1..9.3  evidence-grounded semantic ontology
SAA-10         unified mathematical + reasoning retrieval
SAA-10.1      retrieve-first production policy
SAA-10.2      evidence-bounded cross-domain transfer
SAA-10.3      deterministic explanation and counterfactual fit
SAA-11         controlled one-dimension adaptation
```

## Further roadmap

### SAA-11.1: Persistent adaptation lineage

Persist the evolution graph:

```text
A0
 ├─[DYNAMICS_CONTRACT]→ A1
 ├─[BOUNDARY_CONTRACT]→ A2
 └─[EVIDENCE_CONTRACT]→ A3
```

Each edge should preserve:

- exact parent identity;
- fit delta that justified the change;
- changed dimension;
- unchanged dimensions;
- qualification outcome;
- failure evidence;
- supersedence status.

Failed branches must remain queryable rather than disappearing.

### SAA-11.2: Bounded A/B algorithm experiments

Compare base and adapted candidates under matched conditions:

```text
A vs A'
```

with:

- identical input/evidence fixtures;
- explicit primary metric;
- invariant checks;
- failure-rate comparison;
- resource cost;
- uncertainty;
- independent qualification.

A candidate can be called improved only after measured evidence supports the relevant improvement claim.

### SAA-11.3: Multi-step adaptation with invariant preservation

Permit sequences of one-dimensional changes while proving that already-qualified dimensions remain invariant after each step.

If a later change invalidates an earlier proof, the lineage must automatically require requalification of affected dimensions.

### SAA-12: Closed intelligence-improvement loop

Integrate:

```text
Problem
→ Meaning
→ Retrieve
→ Explain fit
→ Transfer if valid
→ Isolate gap
→ Adapt one dimension
→ Experiment
→ Falsify
→ Qualify
→ Canonicalize
→ Store
→ Reuse
```

No step may self-certify the next.

### SAA-12.1: Canonical failed-algorithm and failed-reasoning algebra

Normalize failed candidates so OIEC can detect that a new proposal is equivalent to a previously falsified approach.

### SAA-12.2: OIEC-Bench as an admission gate

Use benchmark tasks to qualify claims such as:

- factual grounding;
- semantic representation recovery;
- meaning-path integrity;
- repeated-error suppression;
- false progress certification;
- grounded error reduction;
- transfer validity;
- adaptation improvement.

### SAA-12.3: Longitudinal knowledge-integrity measurement

Measure whether expanding canonical knowledge makes future work more reliable rather than merely larger.

Candidate metrics include:

```text
FalseCanonicalAdmissionRate
RepeatedErrorRate
SemanticAmbiguityRate
TransferFailureRate
AdaptationRegressionRate
GroundedErrorReduction
QualifiedReuseRate
```

The long-term objective remains:

> New work expands OIEC intelligence only when it contributes new evidence-qualified semantic, mathematical or reasoning structure.
