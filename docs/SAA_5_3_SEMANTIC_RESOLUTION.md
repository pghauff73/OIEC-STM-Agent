# SAA-5.3 / SAA-5.4 Semantic Representative Resolution

SAA-5.3 adds semantic representativeness as a co-equal requirement with the mathematical representative-input work in SAA-4.1 through SAA-5.2. SAA-5.4 propagates unresolved semantic representation issues into the surrounding OIEC governance systems.

## Governing invariant

A canonical input must be both mathematically representative and semantically resolved.

\[
RepresentativeInput = Independent \land Minimal \land Decoupled \land Admissible \land SemanticallyResolved.
\]

Therefore a mathematically decoupled coordinate is not sufficient for canonical Algorithm Store admission when its meaning remains unresolved.

## Coupling implies semantic misrepresentation

When SAA-4.1 finds exact unresolved coupling, the mathematical status remains:

`NON_REPRESENTATIVE_COUPLED`

and SAA-5.3 additionally creates one or more semantic issues with status:

`SEMANTIC_MISREPRESENTATION`.

This means the declared meaning of the affected input is not considered an adequate description of its observed relationship to the outputs. The variable name itself is not evidence of meaning.

Each issue records the source coordinate, declared meaning if any, observed output footprint, source representation signature, and mandatory follow-up questions such as:

- What independent quantity does this input actually represent?
- Why does it affect these outputs?
- Which outputs should change if only this meaning changes?
- Which outputs should remain invariant?
- What observation would falsify the proposed meaning?
- Is this coordinate a mixture of latent independent inputs?

Redundant inputs are also marked semantic misrepresentations because a declared independent meaning cannot be maintained when the coordinate is an exact linear combination of other inputs.

## Mathematical versus final canonical admission

`RepresentationAssessment.canonical_admission_eligible` from SAA-4.1 is treated by the semantic layer as mathematical eligibility only. `SemanticRepresentationAssessment` exposes both:

- `mathematical_admission_eligible`
- `canonical_admission_eligible`

The second remains false until every required semantic issue has a `SEMANTICALLY_RESOLVED` resolution.

The final helper `canonical_semantic_admission()` requires both mathematical eligibility and a resolved semantic record for every issue.

## Representative coordinates reopen the semantic question

SAA-5 may find a transformation

\[
v = Q u.
\]

Even if the source inputs have names and descriptions, a non-selector representative coordinate is a new semantic object. For example,

\[
v_0 = u_0 + u_1
\]

must not silently inherit the meaning of either source coordinate.

`assess_representative_candidate_semantics()` therefore creates one semantic issue per representative input. A source meaning may only be inherited when the representative coordinate is exactly one unchanged selector coordinate. Otherwise the status is `UNRESOLVED_SEMANTICS`.

This keeps algebraic decoupling separate from semantic resolution.

## Candidate meanings remain hypotheses

`make_semantic_candidate()` creates a `SemanticCandidateMeaning` with:

- meaning proposition;
- expected output positions;
- excluded output positions;
- assumptions;
- falsifiers;
- `epistemic_status = MODEL_PROPOSED_SEMANTICS`.

A model cannot self-certify the candidate as the true meaning.

## Evidence and falsification gate

`evaluate_semantic_candidate()` compares the candidate's predicted output footprint with the exact observed output footprint. A mismatch becomes:

`SEMANTICALLY_CONTRADICTED`.

A matching candidate without grounded evidence remains:

`CANDIDATE_REPRESENTATIVE_SEMANTICS`.

Grounded evidence without complete falsifier survival or independent review remains:

`EVIDENCE_SUPPORTED_SEMANTICS`.

Only a candidate with:

1. exact output-footprint fit;
2. grounded evidence identifiers;
3. every declared falsifier explicitly tested and survived; and
4. independent review

can become:

`SEMANTICALLY_RESOLVED`.

This status is the semantic prerequisite for canonical admission.

## SAA-5.4 propagation

Every unresolved semantic issue generates propagation directives for the surrounding governance systems.

### EON

Action: `SURFACE_UNRESOLVED_SEMANTIC_REPRESENTATION`

The issue must remain visible rather than disappearing behind a transformed variable name.

### OURD

Action: `CREATE_SEMANTIC_RESOLUTION_OBJECTIVE`

Meaning resolution becomes explicit work.

### IURM

Action: `BLOCK_AS_INDEPENDENT_DIMENSION`

A semantically unresolved or misrepresented input must not be treated as an independent one-dimension-at-a-time experiment variable.

### CFEL

Action: `REGISTER_SEMANTIC_COLLISION_ON_CONTRADICTORY_EFFECT`

Observed effects that conflict with the proposed meaning become collision evidence.

### BD/DL

Action: `DETERMINE_SEMANTIC_DOMAIN_AND_BOUNDS`

Once meaning is proposed, its natural domain and bounds must be established before representative re-normalization.

### Hypothesis State

Action: `RECORD_CANDIDATE_MEANINGS_AS_UNVERIFIED`

Candidate meanings remain propositions, not facts.

### Algorithm Store

Action: `BLOCK_CANONICAL_ADMISSION`

An unresolved semantic issue prevents the representation from defining canonical algorithm identity.

## Status ladder

SAA semantic representation uses the following statuses:

- `SEMANTIC_MISREPRESENTATION`
- `UNRESOLVED_SEMANTICS`
- `DECLARED_SEMANTICS`
- `CANDIDATE_REPRESENTATIVE_SEMANTICS`
- `EVIDENCE_SUPPORTED_SEMANTICS`
- `SEMANTICALLY_RESOLVED`
- `SEMANTICALLY_CONTRADICTED`

`DECLARED_SEMANTICS` means only that a description was supplied. It is not a truth claim.

## Non-claims

This milestone does not perform language-model ontology induction, automatically prove domain terminology, derive semantic bounds, mutate live EON/OURD/IURM state, or create final canonical Algorithm Store records. SAA-5.4 emits deterministic propagation directives so those integrations can consume the issue without silently resolving it.

The next canonical-form milestone should combine mathematically representative coordinates, semantically resolved meanings, BD-backed representative bounds, and 0-1 re-normalization before canonical Algorithm Store admission.
