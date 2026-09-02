# SAA-9.1 through SAA-10.1: Evidence-grounded semantics and retrieve-first production

## Purpose

SAA-8.3 through SAA-8.6 made explicit reasoning procedures persistently reusable once their structure, semantics and outcomes were evidence-qualified. The next problem is semantic interoperability: a known algorithm can only be safely retrieved when the problem and the stored algorithm are expressed in meanings that are either identical or independently proven equivalent.

SAA-9.1 through SAA-9.3 create that semantic substrate. SAA-10 searches the mathematical and reasoning stores using one explicit problem contract. SAA-10.1 turns retrieval into a production policy.

The implemented path is:

```text
Evidence-grounded concept
        ↓
SAA-9.1 physical/unit/dimension constraints
        ↓
SAA-9.2 contradiction → revision → requalification
        ↓
SAA-9.3 cross-domain alignment without forced equivalence
        ↓
Persistent Semantic Ontology
        ↓
SAA-10 unified mathematical + reasoning retrieval
        ↓
SAA-10.1 retrieve-first production receipt
        ↓
reuse known solution | adapt only gap | generate only after confirmed gap
```

The central invariant is:

> Similar words, equal dimensions, repeated use, or model confidence never establish semantic equivalence. Exact substitution requires qualified semantic identity or a qualified exact ontology alignment.

## SAA-9.1: Physical units, dimensions and semantic constraints

SAA-9.1 represents SI dimensions as exact integer exponent vectors over the seven SI base dimensions:

```text
[length, mass, time, electric current,
 thermodynamic temperature, amount of substance,
 luminous intensity]
```

For example:

```text
velocity     = [ 1, 0,-1, 0, 0, 0, 0]
force        = [ 1, 1,-2, 0, 0, 0, 0]
energy       = [ 2, 1,-2, 0, 0, 0, 0]
torque       = [ 2, 1,-2, 0, 0, 0, 0]
pressure     = [-1, 1,-2, 0, 0, 0, 0]
```

The energy/torque example is intentional. Equal dimensions do not imply equal meaning.

### Physical units

`PhysicalUnit` contains:

- symbol;
- canonical name;
- dimension vector;
- exact rational scale to SI;
- exact rational affine offset to SI.

The first built-in unit set includes dimensionless, metre, millimetre, centimetre, kilometre, second, kilogram, ampere, kelvin, Celsius, mole, candela, hertz, newton, pascal, joule, watt, coulomb, volt and ohm.

Exact unit conversion uses rational arithmetic. Affine units such as Celsius are represented explicitly rather than treated as multiplicative units.

### Semantic concepts

A `SemanticConcept` binds:

```text
name
meaning
domain
quantity kind
aliases
physical dimension
canonical unit
evidence references
semantic status
```

Its canonical identity includes all meaning-bearing fields.

Therefore:

```text
same label + different quantity kind != same concept
same physical dimension + different meaning != same concept
same numeric unit + different semantic role != same concept
```

### Dimensional constraints

SAA-9.1 provides product and additive semantic checks.

For multiplication/division:

```text
Dimension(output)
    ?=
Σ exponent_i × Dimension(input_i)
```

For addition, both physical dimension and quantity kind must agree.

This prevents a dimensionally valid but semantically invalid operation from being certified merely because its SI exponents match.

## SAA-9.2: Contradiction-driven semantic revision

Canonical meaning is not permanent merely because it was previously qualified. New evidence can contradict it.

SAA-9.2 represents the contradiction explicitly:

```text
SemanticConcept
      ↓
SemanticContradiction
      ↓
MODEL_PROPOSED_SEMANTIC_REVISION
      ↓
new evidence + falsifier survival + independent review
      ↓
SEMANTIC_REQUALIFIED
```

### Immutability

The source concept is never silently edited.

A successful revision produces a new concept signature and an explicit requalification relation. The old concept remains historical evidence of what earlier equations and reasoning procedures meant at the time they were qualified.

This permits audit questions such as:

- Which algorithms still depend on the old meaning?
- What evidence caused the revision?
- Which falsifier differentiated the replacement meaning?
- Was the replacement independently reviewed?

### Requalification boundary

A model can propose a new meaning, but it cannot self-certify it.

Canonical replacement requires:

```text
grounded successful non-simulated evidence
AND deterministic/human producer
AND non-reported evidence method
AND all declared falsifiers survived
AND independent review
```

Contradictions propagate to:

```text
EON
OURD
IURM
CFEL
BD/DL
Hypothesis State
Algorithm Store
```

IURM and Algorithm Store are blocking consumers. Contradicted meaning cannot remain an independent canonical dimension or reusable algorithm input while requalification is unresolved.

## SAA-9.3: Cross-domain ontology alignment

Different disciplines often use different names for equivalent quantities, and identical words for different quantities.

SAA-9.3 therefore separates retrieval similarity from semantic equivalence.

Supported alignment relations include:

```text
EXACT_EQUIVALENT
SPECIALIZES
GENERALIZES
ANALOGOUS_TO
RELATED_TO
NOT_EQUIVALENT
```

Only `EXACT_EQUIVALENT` may authorize exact semantic substitution.

### Exact cross-domain equivalence

An exact alignment requires:

```text
both concepts canonically resolved
AND grounded alignment evidence
AND independent review
AND matching expected effects
AND all alignment falsifiers survived
AND no physical-semantic contradiction
```

For physical concepts, dimension mismatch is a hard contradiction.

However:

```text
same dimension != exact equivalence
```

If quantity kinds differ, SAA reports:

```text
DIMENSION_COMPATIBLE_SEMANTICALLY_DISTINCT
```

### Persistent ontology

`SemanticOntologyStore` persists:

- canonical semantic concepts;
- qualified alignments;
- semantic requalification lineage.

The public ontology store independently resolves every concept evidence ID back to `EvidenceArtifact` before admission.

Exact-equivalence edges form a substitution graph. Analogy/specialization/generalization edges remain search/navigation information and cannot be used for exact substitution.

The SQLite ontology tables are only rebuildable indexes. Immutable semantic objects are authoritative.

## SAA-10: Unified problem retrieval

SAA-10 does not merge mathematical and reasoning algorithms into one object type.

Instead it performs federated retrieval:

```text
UnifiedProblemRequirements
        │
        ├──> SAA-6 Canonical Mathematical Store
        │         ↓
        │    mathematical fit
        │
        └──> SAA-8 Canonical Reasoning Store
                  ↓
             reasoning fit
        ↓
UnifiedRetrievalDecision
```

This preserves the distinction:

```text
mathematical behavior != reasoning procedure
```

while allowing one task to select both.

### Explicit problem contract

`UnifiedProblemRequirements` contains:

- problem ID;
- canonically resolved input concepts;
- required mathematical output count;
- mathematical domain;
- desired reasoning outputs;
- reasoning applicability requirements;
- invariants;
- available evidence capabilities;
- reasoning step budget;
- whether mathematical and/or reasoning components are required.

Free-form prose is not itself a canonical retrieval contract.

### Mathematical fit

Canonical mathematical algorithms are evaluated using:

- representative input meaning coverage;
- qualified ontology equivalence where exact text differs;
- output shape;
- mathematical domain.

Hard semantic/domain/shape gaps make the candidate ineligible even when its aggregate score is otherwise high.

### Reasoning fit

SAA-10 reuses SAA-8.4's existing checks:

- semantic input availability;
- desired outputs;
- applicability;
- required invariants;
- available evidence requirements;
- bounded termination.

### Unified statuses

The first implementation emits:

```text
QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND
PARTIAL_QUALIFIED_KNOWN_SOLUTION_FOUND
NO_QUALIFIED_KNOWN_SOLUTION_FIT
```

The decision stores separate selected mathematical and reasoning IDs. It never claims that the two algorithms are equivalent objects.

## SAA-10.1: Retrieve-first production policy

`RetrieveFirstController` converts the unified retrieval decision into an enforceable policy receipt.

Possible outcomes include:

```text
REUSE_QUALIFIED_KNOWN_SOLUTION
ADAPT_OR_FILL_CONFIRMED_GAP
NOVEL_GENERATION_ALLOWED_AFTER_QUALIFIED_SEARCH
RETRIEVAL_INFRASTRUCTURE_MISSING
```

### Complete known solution

When every required component is found:

```text
new_algorithm_generation_allowed = False
```

The production instruction is to reuse the known qualified components.

### Partial known solution

If one required component is found and another is missing:

```text
reuse known component
AND generate/adapt only missing component
```

The receipt explicitly lists the missing generation scope.

### No qualified fit

Novel generation becomes permissible only after all required canonical stores were actually searched and no eligible fit was found.

This turns the earlier design principle:

```text
retrieve → evaluate fit → identify gap → generate missing algorithm
```

into a runtime policy.

### Missing retrieval infrastructure

If a required store is absent, SAA-10.1 does not say "nothing known exists".

It reports:

```text
RETRIEVAL_INFRASTRUCTURE_MISSING
```

and blocks novelty claims.

This distinction is essential:

```text
not searched != searched and absent
```

## RetrieveFirstProductionOURDAgent

The retrieve-first policy is exposed as an explicit production-agent class rather than silently changing legacy behavior.

When used, the agent requires `UnifiedProblemRequirements` before `run_task` can begin.

The runtime intentionally refuses to infer a canonical retrieval contract from the user's prose. This prevents a model-generated interpretation of a problem from being mislabeled as a system-verified search scope.

A successful preflight emits a deterministic `RetrieveFirstReceipt` and records it as:

```text
SYSTEM_VERIFIED_RETRIEVAL_POLICY
```

The current receipt is included in every model instruction set.

The model is therefore told whether it must:

- reuse a known qualified solution;
- adapt only a confirmed gap;
- or may create a novel candidate after search exhaustion.

The receipt does not make model prose verified. Existing OIEC belief/evidence/progress boundaries remain intact.

## Claim boundaries

This milestone does not claim that:

- dimensional equality establishes semantic equality;
- word embeddings or language similarity establish ontology equivalence;
- analogies permit exact substitution;
- a previously qualified meaning can ignore later contradictory evidence;
- a partial fit is a complete solution;
- a missing store proves no algorithm exists;
- a retrieved algorithm is valid outside its qualified domain;
- model-generated problem interpretation is system-verified retrieval scope.

## Further roadmap

### SAA-10.2: Evidence-bounded cross-domain algorithm transfer

Use qualified ontology relations to determine when an algorithm from one domain can be instantiated in another.

Required distinction:

```text
semantic equivalence
vs
structural analogy
vs
transfer hypothesis
```

Transfer must produce a candidate requiring new domain evidence unless exact equivalence of all meaning-bearing contracts is established.

### SAA-10.3: Retrieval explanations and counterfactual fit

For every selected/rejected candidate, produce a deterministic explanation of:

- matched meanings;
- ontology edges used;
- blocking constraints;
- missing evidence capabilities;
- exact delta required to become eligible.

Then test counterfactual questions such as:

```text
What additional evidence would make algorithm A eligible?
What semantic revision would invalidate algorithm B?
```

### SAA-11: Controlled algorithm adaptation

Given:

```text
Gap = Requirements - BestQualifiedFit
```

create a bounded adaptation candidate that changes only the dimensions needed to close that gap.

IURM should control one representative adaptation dimension at a time where practical.

### SAA-11.1: Evolutionary lineage

Persist:

```text
parent algorithm
adaptation delta
new candidate
qualification evidence
performance/result delta
```

A child algorithm must never silently replace its parent.

### SAA-11.2: Bounded A/B algorithm experiments

Compare known and adapted algorithms under controlled matched conditions.

Improvement becomes:

```text
BETTER_ALGORITHM_CANDIDATE
```

until independently qualified.

### SAA-12: Closed intelligence-improvement loop

The target loop becomes:

```text
Problem
→ Canonical meaning
→ Retrieve known math/reasoning
→ Evaluate fit
→ Reuse or isolate gap
→ Adapt/generate candidate
→ Falsify
→ Qualify
→ Canonicalize
→ Store
→ Reuse on future problems
```

### SAA-12.1: Canonical failed-algorithm algebra

Failures become searchable knowledge with canonical reason-for-failure, scope and evidence.

This allows OIEC to recognize that a newly proposed solution is equivalent to a previously falsified approach.

### SAA-12.2: OIEC-Bench qualification gate

Measure:

- factual precision;
- unsupported-claim rate;
- semantic misrepresentation detection;
- representation recovery;
- meaning-path integrity;
- false progress certification;
- error recurrence;
- grounded error reduction;
- known-algorithm reuse;
- false canonical admission.

### SAA-12.3: Longitudinal knowledge integrity

Measure whether increasing canonical knowledge causes:

```text
error rate ↓
semantic ambiguity ↓
repeated failure ↓
qualified reuse ↑
false equivalence ≈ 0
```

The key research question is no longer merely whether OIEC solves a fresh task. It becomes whether its qualified mathematical, semantic and reasoning substrate becomes measurably more reliable as grounded work accumulates.
