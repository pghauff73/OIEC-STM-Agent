# Bounded Hypothesis State and Control-Only Progress

OIEC-STM distinguishes a hypothesis from a verified fact. A hypothesis is a first-class epistemic object used to organize competing explanations, predictions, falsifiers, and grounded evidence links, but its proposition remains explicitly unverified.

## Hypothesis state

The production agent maintains a bounded `HypothesisSet`. Its maximum size is taken from the active OIEC `DimensionBudget.max_active_hypotheses`, falling back to the kernel cap of 16.

Each `Hypothesis` records:

- a content-addressed `hypothesis_id`;
- the proposition;
- a model-proposed prior score in basis points;
- assumptions;
- predictions;
- falsifiers;
- grounded evidence links;
- deterministic support/conflict/balance bookkeeping;
- a linked-evidence status;
- `verification_status = UNVERIFIED_PROPOSITION`.

The model prior is not a probability certified by OIEC. It is model-belief metadata.

## Content-addressed identity

Hypothesis identity is derived from the normalized proposition, assumptions, predictions, and falsifiers. The model-proposed prior is deliberately excluded from identity, so changing confidence from 40% to 70% cannot manufacture a new hypothesis.

Re-proposing the same semantic hypothesis therefore does not create a new hypothesis merely because the model supplies different whitespace, confidence, a different call ID, or a different runtime UUID. The first recorded prior remains model-belief metadata for that hypothesis identity.

The pool is append-only from the model's perspective and bounded. Exceeding the configured active-hypothesis cap fails closed.

## Grounded evidence links

`link_hypothesis_evidence` requires an existing `EvidenceArtifact`. A link records one of:

- `supports`;
- `conflicts`;
- `falsifies`.

The evidence artifact itself is system-grounded. The semantic relation between that evidence and the hypothesis is still explicitly labelled:

```text
MODEL_PROPOSED_RELATION_TO_VERIFIED_EVIDENCE
```

Thus:

```text
verified evidence exists
!=
model's interpretation of that evidence is verified
```

The hypothesis proposition always remains:

```text
UNVERIFIED_PROPOSITION
```

unless a future external/formal verifier establishes stronger status.

One content/provenance evidence fingerprint can be linked only once to a given hypothesis. The model cannot reuse the same observation first as `supports`, then as `conflicts`, then as `falsifies` to manufacture three state transitions.

## Deterministic evidence bookkeeping

For a hypothesis, OIEC derives bounded support and conflict scores from linked evidence quality. A sufficiently strong explicit `falsifies` link moves the bookkeeping status to `FALSIFIED_BY_LINKED_EVIDENCE`; otherwise the support/conflict balance can produce `SUPPORTED_BY_LINKED_EVIDENCE`, `WEAKENED_BY_LINKED_EVIDENCE`, or `UNRESOLVED`.

These names describe the state of **model-proposed interpretations of grounded evidence**, not truth certification.

## Hypothesis bookkeeping in progress certificates

The production `VerifiedProjection` separates:

```text
hypothesis_definition_atoms
hypothesis_evidence_atoms
```

Creating a new hypothesis definition is **control progress**, not epistemic evidence progress.

Adding a novel grounded evidence link contributes to the diagnostic field:

```text
ProgressCertificate.hypothesis_resolution_bp
```

but the link relation is model-proposed, so that field does **not by itself** reset the control-only streak or qualify as verified epistemic gain. It records structured hypothesis bookkeeping, not proof that the interpretation is correct.

Repeated evidence content is deduplicated by content/provenance identity, so a fresh evidence UUID does not manufacture another bookkeeping event.

## Bounded control-only allowance

Production reasoning sometimes needs a small number of transitions that structure the problem without gathering evidence, for example:

1. establish governance;
2. create competing hypotheses or select an action;
3. then test them.

OIEC therefore allows a bounded number of consecutive control-only transitions. The default is:

```text
max_control_only_progress = 2
```

A control-only transition is a verified change to governance/action/hypothesis structure or a model-proposed hypothesis-evidence interpretation **without new grounded evidence, a new collision observation, or meaningful boundary resolution**.

The persistent rule is:

```text
control-only #1 -> allowed
control-only #2 -> allowed
control-only #3 -> CONTROL_ONLY_BUDGET_EXHAUSTED
```

The streak is stored in `RuntimeState.control_only_progress_streak`, so restarting the agent or starting another chat turn does not reset the allowance.

Genuine system-grounded epistemic progress resets the streak to zero, including:

- novel content-addressed evidence;
- a new collision/counterexample observation;
- meaningful boundary uncertainty reduction.

If new evidence is gathered in a transition that also performs hypothesis bookkeeping, the evidence is what resets the streak. The model's relation label is not what earns the reset.

A terminal response also resets the streak because the autonomous sequence has ended.

## Production invariant

The combined rule is:

```text
Model belief != system verification
Hypothesis proposition != verified fact
Model-proposed evidence relation != verified inference
Control structure != epistemic progress
```

and continuation is permitted only when:

```text
ProgressCertificate.accepted
AND
not cycle_detected
AND
control_only_streak <= max_control_only_progress
```

This gives the model enough room to organize a problem while preventing indefinite governance, action, hypothesis, confidence, or evidence-interpretation churn from impersonating verified reasoning progress.
