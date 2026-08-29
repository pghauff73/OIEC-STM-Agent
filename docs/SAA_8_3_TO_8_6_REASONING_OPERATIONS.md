# SAA-8.3 through SAA-8.6: Operational canonical reasoning

## Purpose

SAA-8 made explicit public reasoning procedures canonical algorithm objects. SAA-8.1 separated reasoning topology from reasoning semantics, and SAA-8.2 prevented semantically misrepresented reasoning-state variables from entering trusted reasoning state.

SAA-8.3 through SAA-8.6 make that representation operational:

```text
explicit reasoning algorithm
        ↓
SAA-8.5 outcome qualification
        ↓
SAA-8.3 canonical reasoning store
        ↓
SAA-8.4 retrieve and evaluate task fit
        ↓
use known reasoning or identify fit gaps
        ↓
SAA-8.6 safe composition where needed
        ↓
new composite must return through SAA-8.5
```

The governing invariant is:

> A reasoning procedure is reusable canonical knowledge only when its representation is exact, its semantics are explicit, and at least one independently reviewed execution has satisfied its evidence, invariant, falsifier and termination contracts.

## SAA-8.3: Canonical Reasoning Store

`CanonicalReasoningStore` persists evidence-qualified `CanonicalReasoningAlgorithm` objects separately from the mathematical Canonical Algorithm Store.

The canonical identity is:

```text
canonical-reasoning:sha256:<canonical_reasoning_signature>
```

The store accepts only:

```text
canonicalization_strength == EXACT_BOUNDED_GRAPH_CANONICALIZATION
public_artifact_only == True
qualification.status == QUALIFIED_REASONING_OUTCOME
qualification.canonical_reuse_eligible == True
```

This deliberately excludes conservatively source-bound reasoning graphs from canonical reuse.

### De-duplication

If an admitted reasoning algorithm has the same canonical reasoning signature as an existing entry, the existing canonical object is reused. A new qualification record is attached as provenance.

Therefore:

```text
new successful execution != new knowledge generation
```

Store generation increases only when a genuinely new canonical reasoning algorithm is admitted.

### Persistent objects

The reasoning store maintains immutable objects for:

- canonical reasoning algorithms;
- reasoning outcome qualifications.

SQLite indexes are a rebuildable projection and include:

- canonical reasoning signature;
- topology signature;
- semantic signature;
- input semantics;
- output semantics;
- applicability;
- maximum step budget;
- qualification provenance.

The persistent object graph is authoritative. The SQLite projection can be rebuilt without changing canonical identity.

## SAA-8.4: Retrieve known reasoning and evaluate fit

Known does not imply suitable.

SAA-8.4 evaluates a stored reasoning algorithm against a `ReasoningTaskRequirements` contract containing:

- currently available input meanings;
- desired output meanings;
- required applicability constraints;
- required invariants;
- evidence capabilities available to the current task;
- maximum permitted reasoning steps.

The deterministic fit profile contains six dimensions:

```text
input fit          20%
output fit         25%
applicability      15%
invariants         15%
evidence capability 10%
termination budget 15%
```

Hard contract failures create blockers regardless of numeric score. Examples include:

- a required input is absent;
- a desired output is not produced;
- required applicability is missing;
- required invariants are absent;
- the current environment cannot satisfy a stored evidence requirement;
- the stored reasoning algorithm exceeds the current step budget.

Possible statuses are:

```text
GOOD_REASONING_FIT
PARTIAL_REASONING_FIT
POOR_REASONING_FIT
INELIGIBLE_REASONING_FIT
```

Retrieval searches only the qualified Canonical Reasoning Store.

### Qualification count is not fit

The number of previous successful executions is not included in the fit score.

Repeated use is useful reliability evidence, but it must not override semantic or operational mismatch. A highly tested algorithm for the wrong problem remains the wrong algorithm.

## SAA-8.5: Evidence-qualified reasoning outcomes

SAA-8.5 distinguishes:

```text
reasoning execution completed
```

from:

```text
reasoning outcome qualified for canonical reuse
```

`ReasoningExecutionOutcome` records only explicit public outcome artifacts:

- canonical reasoning algorithm identity;
- execution identifier;
- observed output semantics;
- evidence IDs;
- invariant results;
- falsifier results;
- termination result;
- steps used;
- execution success;
- independent-review status.

No private chain-of-thought is requested or persisted.

### Qualification requirements

A reasoning outcome becomes `QUALIFIED_REASONING_OUTCOME` only if all of the following hold:

1. the reasoning algorithm has exact bounded canonical identity;
2. observed output meanings exactly satisfy the algorithm output contract;
3. every declared invariant is present and satisfied;
4. every declared falsifier is explicitly tested and survived;
5. the execution terminated inside the algorithm's bounded step budget;
6. execution reports success;
7. evidence is registered as `EvidenceArtifact`;
8. evidence is successful and non-simulated;
9. evidence comes from deterministic or human grounding;
10. model-claimed or reported-only evidence is rejected;
11. all declared evidence requirements are covered;
12. at least one evidence independence group exists;
13. independent review is recorded.

Failure remains explicit through statuses such as:

```text
UNQUALIFIED_REASONING_CANONICALIZATION
UNQUALIFIED_REASONING_OUTPUT_CONTRACT
UNQUALIFIED_REASONING_INVARIANT_FAILURE
UNQUALIFIED_REASONING_FALSIFIER
UNQUALIFIED_REASONING_TERMINATION
UNQUALIFIED_REASONING_EVIDENCE
UNQUALIFIED_REASONING_INDEPENDENT_REVIEW
```

This qualification is evidence that the explicit reasoning procedure succeeded under that execution context. It is not a proof that the procedure is universally optimal.

## SAA-8.6: Safe reasoning composition

SAA-8.6 treats reasoning composition as a new algorithm, not as a free consequence of component validity.

For two reasoning algorithms `A` and `B`, automatic sequential composition requires:

```text
ExactCanonical(A)
AND ExactCanonical(B)
AND QualifiedOutcome(A)
AND QualifiedOutcome(B)
AND Inputs(B) subset Outputs(A)
AND CompatibleInvariants(A,B)
AND Steps(A)+Steps(B) <= bounded maximum
```

### Semantic interface

The downstream input meaning must be supplied by an upstream output with exactly the same canonical semantic label at the current SAA-8 level.

No synonym inference occurs in SAA-8.6. That belongs to the future evidence-grounded ontology layer.

### Invariant conflicts

The initial composition gate detects exact explicit negation conflicts such as:

```text
preserve source evidence
not preserve source evidence
```

More sophisticated semantic contradiction analysis belongs to SAA-9.2.

### Composition topology

The composition builder:

1. reconstructs each canonical public operator graph;
2. preserves node evidence requirements, assumptions and falsifiers;
3. connects upstream exit nodes to downstream entry nodes through an explicit qualified semantic handoff;
4. unions component invariants and applicability requirements;
5. sums bounded termination budgets;
6. canonicalizes the resulting graph again through SAA-8.

If the resulting graph exceeds exact canonicalization bounds, automatic safe composition fails closed.

### Qualification does not compose automatically

Even when `A` and `B` are individually qualified:

```text
Qualified(A) AND Qualified(B)
```

does not imply:

```text
Qualified(B o A)
```

The composite returns:

```text
qualification_required = True
canonical_reuse_eligible = False
```

It must execute and pass SAA-8.5 before SAA-8.3 can admit it.

This prevents interaction errors between individually sound reasoning procedures from becoming canonical knowledge without evidence.

## Operational retrieve-first loop

The implemented SAA reasoning path is now:

```text
Problem
  ↓
Explicit semantic requirements
  ↓
Canonical Reasoning Store
  ↓
Retrieve known qualified reasoning algorithms
  ↓
Evaluate fit
  ├─ good fit → execute
  ├─ partial fit → expose adaptation gap
  └─ no fit → search/generate candidate reasoning
  ↓
Evidence-qualified outcome
  ↓
Canonical admission or additional provenance
```

If a composition is needed:

```text
qualified A + qualified B
        ↓
SAA-8.6 composition gate
        ↓
new unqualified composite C
        ↓
execute C
        ↓
SAA-8.5 qualification
        ↓
SAA-8.3 admission
```

## Non-goals

SAA-8.3 through SAA-8.6 do not yet claim:

- ontology-level synonym equivalence;
- semantic implication between differently worded concepts;
- automatic proof of generalization/specialization between reasoning algorithms;
- universal optimality of the highest-fit stored algorithm;
- reliability estimates merely from execution count;
- automatic adaptation of partially fitting algorithms;
- automatic promotion of composed reasoning without new evidence;
- access to or persistence of private model chain-of-thought.

## Further roadmap

### SAA-9: Evidence-grounded semantic ontology

Replace exact string-level semantic matching with evidence-grounded concept objects and explicit semantic relations.

A semantic relation must distinguish:

```text
SAME_MEANING
SPECIALIZES
GENERALIZES
PART_OF
CAUSES
MEASURES
CORRELATES_WITH
NEAR_MEANING
CONTRADICTS
UNRESOLVED
```

Similarity is candidate retrieval, not equivalence proof.

### SAA-9.1: Units, dimensions and physical meaning

Add dimensional/unit contracts to semantic concepts so physically incompatible meanings cannot be silently aligned.

### SAA-9.2: Contradiction-driven semantic revision

When new evidence contradicts a canonical meaning, create a governed revision and requalification process instead of mutating canonical semantics in place.

### SAA-9.3: Cross-domain ontology alignment

Support transfer between domains only when semantic relations are explicitly evidenced. Adjacent concepts must not be collapsed because their labels look similar.

### SAA-10: Unified problem-to-algorithm fit

Unify mathematical Algorithm Store retrieval and Canonical Reasoning Store retrieval under a representative problem contract.

The goal is:

```text
Problem
→ representative meanings
→ retrieve mathematical algorithms
→ retrieve reasoning algorithms
→ evaluate fit
→ construct qualified execution plan
```

### SAA-10.1: Retrieve-first runtime policy

Make retrieval of qualified known reasoning/algorithms the default production-agent action before free generation.

### SAA-10.2: Evidence-bounded cross-domain transfer

Allow known algorithms to migrate between domains only where ontology, units, bounds and evidence support the transfer.

### SAA-11: Controlled algorithm adaptation

Represent the difference between task requirements and best qualified fit as an explicit delta.

Use IURM to vary one representative dimension at a time and test whether the adaptation improves the result.

### SAA-11.1: Qualified evolutionary lineage

Persist parent/child relationships between algorithm variants, including what changed, why it changed, evidence, failures and supersedence.

### SAA-11.2: Bounded A/B algorithm experiments

Compare qualified alternatives under matched contexts without allowing an algorithm to self-certify its superiority.

### SAA-12: Closed intelligence-improvement loop

The target loop becomes:

```text
Problem
→ meaning
→ representation
→ retrieve
→ fit
→ execute
→ evidence
→ qualify
→ identify gap
→ adapt
→ falsify
→ requalify
→ canonicalize
→ store
→ reuse
```

### SAA-12.1: Canonical failure algebra

Persist failed reasoning and failed algorithmic structures so structurally equivalent mistakes are recognized instead of repeated.

### SAA-12.2: OIEC-Bench qualification gate

Use longitudinal grounding, factuality, semantic representation, meaning-path integrity, false-progress certification and repeated-error metrics as independent evidence for system-level claims.

### SAA-12.3: Canonical knowledge integrity

Measure whether store growth improves reasoning without increasing false canonical admission, semantic contradiction or repeated-error rates.

The central long-term metric is not the size of the store. It is the amount of unique, qualified and reusable structure that remains coherent as the store grows.
