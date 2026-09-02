# SAA-11.3, SAA-11.4 and SAA-12: Closed qualified improvement

## Purpose

SAA-11 introduced one-dimension-at-a-time adaptation. SAA-11.1 made adaptation lineage persistent and SAA-11.2 added bounded evidence-qualified A/B comparison. These milestones complete the first closed improvement cycle.

```text
retrieve known knowledge
        ↓
explain exact fit delta
        ↓
adapt one dimension at a time
        ↓
SAA-11.3 requalify frozen invariants after every step
        ↓
SAA-11.4 repeat and aggregate independent experiments
        ↓
normal canonical qualification
        ↓
record promotion
        ↓
re-run retrieval
        ↓
SAA-12 closes only if promoted knowledge is selected
```

The governing distinction is:

> Derivation, comparative improvement, canonical qualification and reusable knowledge are different epistemic events and must remain different artifacts.

## SAA-11.3: invariant-preserving multi-step evolution

A multi-step path is represented explicitly as:

```text
Canonical A
  └─ Δ1 → Candidate A1
       └─ Δ2 → Candidate A2
            └─ ...
```

`make_multistep_evolution_plan(...)` reconstructs the exact stored lineage from the final candidate back to its canonical root. The path is bounded to at most 16 steps.

Each step records:

- exact parent reference;
- exact candidate reference;
- changed adaptation dimension;
- lineage-edge signature;
- candidate signature.

The plan also declares frozen invariants and optionally the adaptation dimensions allowed inside this evolution attempt.

### Intermediate qualification

Every intermediate candidate must pass `qualify_evolution_step(...)` before the path can qualify.

For every frozen invariant the step must provide:

```text
invariant -> True/False
```

The evidence supporting those results must resolve to successful, non-simulated, deterministic or human-grounded `EvidenceArtifact` records with an independence group.

Independent review is required.

Therefore:

```text
final endpoint looks good
!=
intermediate path preserved its safety/meaning invariants
```

A violation at any intermediate point blocks the entire multi-step evolution assessment.

`assess_multistep_evolution(...)` binds the final assessment to the exact step-qualification signatures on which it depends.

## SAA-11.4: repeated experimental evidence

A single A/B experiment can establish bounded comparative evidence. It does not establish stability across repeated runs.

`aggregate_repeated_experiments(...)` accepts repeated `AlgorithmABExperimentResult` objects only when they have the exact same experiment design signature.

The aggregate rejects:

- duplicate result signatures;
- different designs or contexts;
- changed metric identities or directions;
- constituent invariant/evidence/review failures.

For each metric it records exact rational evidence including:

- number of experiments;
- material improvement count;
- material regression count;
- no-material-change count;
- exact mean signed improvement;
- minimum and maximum signed improvement.

Sustained improvement requires:

```text
minimum repeated experiments
AND minimum independent evidence groups
AND every constituent experiment is qualified
AND at least one material improvement
AND no material regression
AND no unresolved tradeoff
```

The success status is:

```text
SUSTAINED_CANDIDATE_IMPROVEMENT_QUALIFIED
```

Even this status does not make the candidate canonical. It still says:

```text
qualification_required_before_canonical_reuse = True
```

## SAA-12: closed qualified intelligence-improvement loop

SAA-12 is a deterministic phase controller over already explicit public artifacts.

It does not generate hidden reasoning and it cannot self-certify an algorithm.

The implemented phases are:

1. `RETRIEVE`
2. `EXPLAIN_GAP`
3. `PLAN_ADAPTATION`
4. `EVOLVE`
5. `EXPERIMENT`
6. `QUALIFY_AND_PROMOTE`
7. `RE_RETRIEVE`
8. `VERIFY_CLOSURE`

The controller consumes:

- SAA-10.1 `RetrieveFirstReceipt`;
- SAA-10.3 `RetrievalExplanation`;
- SAA-11 `ControlledAdaptationPlan`;
- SAA-11.3 `MultiStepEvolutionAssessment`;
- SAA-11.4 `RepeatedExperimentAggregate`;
- an external canonical promotion record;
- a new post-promotion retrieval receipt.

### Closure rule

The loop does not close merely because a promotion was recorded.

The post-promotion qualified retrieval must run again and select the exact promoted canonical algorithm.

Only then does SAA-12 emit:

```text
CLOSED_LOOP_IMPROVEMENT_VERIFIED
```

This makes knowledge growth operationally observable:

```text
old store could not satisfy problem completely
→ bounded candidate evolution
→ repeated comparative evidence
→ external canonical qualification
→ updated store
→ retrieval now selects promoted knowledge
```

That final retrieval is the proof that the improvement became reusable canonical knowledge rather than remaining an isolated experiment.

## Persistent improvement ledger

`ImprovementLoopStore` keeps immutable objects for:

- multi-step evolution plans;
- evolution-step qualifications;
- evolution assessments;
- repeated experiment aggregates;
- SAA-12 loop decisions.

Its SQLite indexes are a disposable projection. Rebuilding the projection does not change any content identity.

Store admission rechecks cross-artifact dependencies. In particular:

- qualified evolution must be backed by the exact registered step qualifications;
- every candidate in the plan must be covered;
- aggregates must bind the exact registered experiment results for their design;
- sustained improvement cannot be registered over an unqualified constituent result;
- loop decisions cannot reference missing evolution assessments, aggregates or promotions;
- closed-loop decisions require both promotion and post-promotion retrieval evidence.

## What SAA-12 does not claim

SAA-12 does not prove general intelligence or universal algorithm optimality.

It establishes a bounded auditable mechanism for a narrower claim:

> A previously incomplete qualified knowledge base can identify a fit gap, generate a controlled candidate, preserve declared invariants through its lineage, establish repeated comparative improvement in a fixed experiment contract, externally qualify/promote the candidate, and then demonstrate that the updated canonical store reuses the promoted knowledge on subsequent retrieval.

## Next milestones

The natural continuation is:

### SAA-12.1: failure algebra

Persist and canonicalize failed adaptations, regressions, invariant violations and repeated failed reasoning so equivalent failures are recognized before another attempt.

### SAA-12.2: OIEC-Bench admission gate

Connect benchmark tracks such as factual grounding, semantic representation, false-progress detection, repeated-error rate and agent task completion to canonical promotion policy.

### SAA-12.3: longitudinal knowledge integrity

Measure whether canonical knowledge remains coherent as the store grows:

- contradiction rate;
- semantic drift;
- false canonical admission;
- repeated corrected-error rate;
- supersedence health;
- retrieval precision;
- qualified reuse rate.

### SAA-12.4: bounded improvement scheduling

Choose which confirmed knowledge gaps are worth experimenting on next using expected information gain, cost, risk and evidence value, without allowing the scheduler to certify its own priorities as truth.

### SAA-13: higher-order reasoning ecology

Use the canonical mathematical, semantic and reasoning stores plus failed-algorithm knowledge to reason over populations of strategies, domain transfers and composition families while preserving the same evidence boundaries.
