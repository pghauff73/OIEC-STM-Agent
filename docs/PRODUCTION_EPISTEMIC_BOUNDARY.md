# Production Epistemic Boundary and Loop Control

Production agents need an explicit boundary between **what the model believes** and **what the system has verified**. OIEC-STM now enforces this boundary in the production CLI and GUI agent loop.

## Two planes

### Model-belief plane

The following are proposals, not facts:

- model prose;
- confidence statements;
- hypotheses and assumptions;
- plans;
- claimed causal explanations;
- tool proposals;
- claims that a task is complete.

Each model response is traced as `model_belief` with:

```text
epistemic_status = UNVERIFIED_MODEL_BELIEF
```

The audit record contains a hash of the text and a semantic signature of proposed tool calls. Runtime-generated UUIDs and evidence IDs do not affect the semantic call signature.

### System-verified plane

The production controller derives a `VerifiedProjection` exclusively from deterministic runtime state:

- workspace snapshot;
- deduplicated `EvidenceArtifact` content/provenance;
- deduplicated collision observations;
- established governance/control state;
- current EON action and evidence-gate state;
- transaction lifecycle state;
- Boundary Determination and Dimension Limiting signatures.

Model prose cannot directly populate this projection.

This distinction means:

```text
model says "test passed"             -> belief
run_command returns code 0 + evidence -> verified observation
model says "the file changed"        -> belief
workspace snapshot actually changes   -> verified state
model says "I made progress"          -> belief
ProgressCertificate accepted           -> verified progress decision
```

## Content-addressed evidence novelty

Progress does not count raw evidence IDs. Evidence is reduced to stable atoms based on content and provenance.

Therefore:

```text
read README.md -> evidence:e1
read README.md -> evidence:e2
```

with identical bytes, source snapshot and observation semantics contributes one verified evidence atom, not two.

A fresh UUID cannot manufacture epistemic progress.

## Mandatory Progress Certificates

Every production model transition receives a system-generated `ProgressCertificate`.

For a nonterminal step, continuation requires at least one accepted progress condition:

- novel verified evidence;
- governed state advancement;
- boundary uncertainty reduction;
- another progress mode already defined by OIEC's deterministic certificate rules.

The production model cannot submit or approve its own certificate.

A final model response also receives a terminal certificate, but the final prose is explicitly traced as:

```text
epistemic_status = MODEL_OUTPUT_UNVERIFIED
```

This means the runtime certifies that the bounded process terminated, not that every sentence in the generated answer is true.

## Cycle detection

The controller detects several loop classes.

### No verified progress

If a nonterminal tool step leaves the verified projection unchanged and adds no novel content-addressed evidence:

```text
NO_VERIFIED_PROGRESS -> CYCLE_STOP
```

### Verified-state cycle

If the system returns to a previous verified-state signature:

```text
S0 -> S1 -> S2 -> S0
```

the loop is stopped.

### Semantic periodic cycle

Tool-call identities are normalized to remove volatile IDs. Repeated control-only patterns such as:

```text
A -> B -> A -> B
```

without new positive verified evidence are classified as:

```text
SEMANTIC_PERIODIC_CYCLE -> CYCLE_STOP
```

This prevents a model from evading loop detection by changing call IDs, evidence UUIDs or superficial wording.

## Stop behavior

A blocked loop creates:

1. the rejected/accepted `ProgressCertificate` in runtime state;
2. a `progress_certificate` audit event;
3. a CFEL collision with `disposition=CYCLE_STOP`;
4. a `cycle_stop` audit event;
5. a typed `StateError` that terminates the autonomous turn.

The recommended correction is not "try again". It is:

```text
obtain genuinely new evidence
OR change the bounded hypothesis/experiment
OR request human input
OR terminate epistemically
```

## Production entry points

The compatibility core remains available as:

```python
from ourd import OURDAgent
```

Production entry points use:

```python
from ourd import ProductionOURDAgent
```

The `oiec-stm-agent` CLI and GUI `CoreGateway` instantiate `ProductionOURDAgent` automatically.

This separation preserves compatibility for low-level tests and integrations while making the product-facing agent stricter.

## Turn-scoped tool authority

Each ICPI turn may carry a signed `TurnExecutionPolicy` bound to the route,
source snapshot, context envelope, target paths, requested outputs, allowed
tool groups, and mutation classification. The policy can only narrow the
existing human authority. Tool availability is recalculated from current
runtime state and every dispatch rechecks the same preconditions.

Super reasoning is not a universal tool. It is hidden until the turn permits
certified reasoning, governance is established, authority is current, and no
pending action owns the boundary. An injected or stale call returns a signed,
structured `ToolFailureEnvelope`. The first new recoverable precondition
failure records one deterministic collision and permits a corrected transition;
an identical retry reuses the collision identity and does not count as
progress.

Summarization is a distinct read-only intent. Corpus manifests bind exact paths,
file hashes, line counts, and the source snapshot. Per-document coverage tracks
merged read ranges and evidence IDs. A summary artifact is accepted only after
complete coverage of the exact file, and whole-corpus completion is exact set
equality between manifested and current summaries. Model-written summary prose
is labelled as source-bound interpretation, not certified truth.

Formal writing follows the same separation. Source extraction, anchors,
locators, bibliographic records, citation uses, integrity reports, and writing
certificates are deterministic artifacts. Concepts, reasoning labels,
paraphrases, plans, and prose remain interpretations. A `WRITE` or `REVISE`
operation returns a candidate only; workspace mutation still requires exact
authority, a prepared transaction, EON action, evidence gate, human approval,
application, verification, finalization, and rollback evidence.

Terminal synthesis now separates verified tool outputs, verified policy
failures, model-proposed tool arguments, restored source excerpts, document
summary artifacts, and corpus coverage. Tool arguments never appear as verified
observations, and restored Markdown or other repository text is explicitly
treated as untrusted data rather than instructions.

## Core invariant

The governing production invariant is:

```text
Model belief != system verification
```

and autonomous continuation is:

```text
continue
IFF
system_generated_progress_certificate.accepted
AND
not cycle_detected
```

That turns progress from a narrative claim into a deterministic runtime decision.
