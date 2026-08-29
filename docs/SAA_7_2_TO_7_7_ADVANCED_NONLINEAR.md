# SAA-7.2 through SAA-7.7: Advanced bounded nonlinear representation

## Purpose

SAA-7 introduced exact finite Taylor jets in the semantically qualified representative coordinates produced by SAA-6. SAA-7.1 added bounded search for exact triangular nonlinear shears when the local equation showed nonlinear coupling or semantic misrepresentation.

SAA-7.2 through SAA-7.7 extend that local nonlinear layer into an evidence-governed, region-aware, persistent and geometrically analysed reasoning system.

The governing invariant remains:

> A finite local nonlinear model is local evidence. It is never silently promoted to global nonlinear truth.

The complete path implemented by this milestone is:

```text
SAA-6 canonical representative form
        ↓
SAA-7 exact local Taylor jet
        ↓
SAA-7.1 initial nonlinear representation search
        ↓
SAA-7.2 governed nonlinear evidence acquisition
        ↓
SAA-7.3 multi-point semantic stability
        ↓
SAA-7.4 persistent local nonlinear knowledge
        ↓
SAA-7.5 broader exact polynomial representation search
        ↓
SAA-7.6 differential-geometric analysis
        ↓
SAA-7.7 observability / controllability gates
```

## Non-negotiable epistemic boundaries

The nonlinear stack follows six hard rules.

1. Exact and estimated evidence are different epistemic objects.
2. One expansion point cannot establish regional semantic stability.
3. Local nonlinear knowledge is stored separately from global SAA-6 canonical identity.
4. An invertible coordinate transformation does not prove that a finite Taylor jet is globally valid.
5. A singular Jacobian at one operating point does not by itself prove a redundant semantic dimension.
6. A static input-output equation cannot certify controllability.

These rules are deliberately conservative because false equivalence or false semantic certainty can contaminate every later reasoning path that reuses a canonical algorithm.

---

# SAA-7.2 Governed nonlinear evidence acquisition

## Objective

SAA-7 previously accepted a supplied exact Taylor jet. SAA-7.2 adds controlled ways of obtaining that jet and records how the coefficients were acquired.

The new evidence object is `GovernedJetEvidence`.

It records:

- parent SAA-6 representative behavior signature;
- evidence kind;
- source snapshot hash;
- producer;
- acquisition method;
- whether acquisition is independent;
- exact versus estimated status;
- expansion point;
- validity radius;
- Taylor order;
- the canonical exact jet when exact admission is allowed;
- bounded derivative estimates when the evidence is approximate;
- evidence signature and warnings.

## Exact symbolic polynomial acquisition

For an exact polynomial source

\[
y_k(r)=\sum_\beta c_{k,\beta}r^\beta,
\]

and exact operating point \(c\), SAA-7.2 substitutes

\[
r=c+z
\]

and expands every monomial using exact binomial arithmetic.

For one coordinate,

\[
(c_i+z_i)^{\beta_i}
=
\sum_{\alpha_i=0}^{\beta_i}
{\beta_i\choose\alpha_i}
c_i^{\beta_i-\alpha_i}z_i^{\alpha_i}.
\]

The multivariate product is truncated only at the declared Taylor order. No floating-point coefficient participates in exact identity.

This acquisition mode produces:

`EXACT_SYMBOLIC_POLYNOMIAL`.

The source polynomial itself is content-hashed, so two identical symbolic sources produce the same source snapshot identity.

## Exact derivative table acquisition

An independently supplied derivative table may also generate an exact jet.

For multi-index \(\alpha\), the Taylor coefficient is

\[
a_{k,\alpha}
=
\frac{D^\alpha y_k(c)}{\alpha!},
\]

with

\[
\alpha!=\prod_i \alpha_i!.
\]

This mode produces:

`EXACT_DERIVATIVE_TABLE`.

Exact numeric values alone are not sufficient for canonical local admission. Producer, method and independence are checked. Reported/model-claimed values do not self-qualify.

## Estimated derivative evidence

Measurements, numerical differentiation and interval estimates are represented separately as bounded derivative evidence:

\[
D^\alpha y_k(c)\in[L,U].
\]

This mode produces:

`BOUNDED_ESTIMATED_DERIVATIVES`.

It intentionally has:

```text
exact = False
canonical_local_eligible = False
jet = None
```

The evidence remains valuable for comparison, falsification and future approximate reasoning, but it cannot contaminate exact nonlinear canonical identity.

## Current evidence boundary

Implemented exact acquisition:

- exact symbolic polynomials;
- exact derivative tables.

Implemented approximate acquisition boundary:

- bounded derivative estimates retained without exact canonical promotion.

Not yet claimed:

- automatic differentiation provenance from arbitrary runtime code;
- validated interval automatic differentiation;
- certified finite-difference truncation/error bounds;
- probabilistic coefficient posteriors;
- noisy experimental-system identification.

---

# SAA-7.3 Multi-point semantic stability

## Objective

A coordinate can appear meaningful at one expansion point and cease to be representative elsewhere.

SAA-7.3 therefore evaluates local nonlinear forms as a set of operating-region observations.

Each `NonlinearRegionalObservation` contains:

- qualified local nonlinear form;
- expansion point and local validity box;
- resolved meanings;
- transform-family signature;
- optional evidence signature.

## Connected operating region

For local boxes \(B_i\) and \(B_j\), SAA constructs an adjacency edge when their exact axis-aligned boxes overlap in every coordinate.

The observation graph must be connected before OIEC may make a regional semantic claim.

This prevents two distant local successes from being silently treated as evidence about the unexplored region between them.

## Semantic stability conditions

Regional semantic admission requires:

\[
ConnectedRegion
\land
MeaningStable
\land
RepresentationFamilyStable.
\]

The statuses are:

- `LOCALLY_STABLE_SEMANTICS`
- `MULTI_REGION_SEMANTICS_UNRESOLVED`
- `SEMANTIC_TRANSITION_DETECTED`
- `REPRESENTATION_REGIME_CHANGE`
- `REGIONALLY_STABLE_SEMANTICS`

### Semantic transition

If the resolved meaning of coordinate \(v_i\) differs between qualified local points, OIEC records a semantic transition rather than averaging the meanings.

### Representation regime change

Even if the same label is retained, a different required nonlinear transform family indicates that the coordinate representation changes across the operating region.

This yields:

`REPRESENTATION_REGIME_CHANGE`.

That is important because identical wording can hide a mathematically different concept.

## Regional eligibility

Only:

`REGIONALLY_STABLE_SEMANTICS`

sets:

```text
regional_semantic_eligible = True
```

Even then, the claim is restricted to the connected union of qualified local boxes.

---

# SAA-7.4 Persistent local nonlinear Canonical Store

## Objective

Local nonlinear knowledge must persist, but it must not be confused with the stronger global identity represented by the SAA-6 Canonical Algorithm Store.

SAA-7.4 therefore creates a separate store rooted under:

```text
.ourd-agent/egcf/nonlinear-canonical/
```

The public API is `NonlinearCanonicalStore`.

## Three immutable object classes

The store persists:

1. exact governed nonlinear evidence;
2. qualified local nonlinear representative forms;
3. qualified regional semantic-stability assessments.

The SQLite database is a disposable projection over these immutable objects.

## Local identity

A local nonlinear canonical form is keyed by:

\[
ID_{local}=LocalRepresentativeBehaviorSignature.
\]

The identity binds:

- SAA-6 parent representative behavior;
- transformed jet coefficient identity;
- transformed jet scope identity;
- resolved local semantic identity.

Two identical local nonlinear forms do not create two pieces of knowledge. The second admission adds provenance.

## Store admission gate

Before a local form is persisted, SAA-7.4 rechecks:

- `local_canonical_eligible = True`;
- `global_equivalence_eligible = False`;
- local store status is correct;
- local behavior signature recomputes exactly;
- evidence is a `GovernedJetEvidence` object;
- evidence is exact;
- evidence is locally canonical-eligible;
- evidence contains a canonical jet;
- evidence belongs to the same SAA-6 parent;
- evidence grounds the source jet actually used by the local representation;
- evidence kind is an exact supported acquisition method.

Estimated evidence cannot pass this gate.

## Dedicated indexes

The local projection indexes:

- parent representative behavior;
- local representative behavior;
- local semantic signature;
- source jet signature;
- coefficient signature;
- scope signature;
- exact center;
- validity radius;
- Taylor order;
- evidence provenance;
- regional semantic assessments.

## Rebuildability

Deleting the nonlinear SQLite projection does not delete knowledge.

`rebuild_projection()` reconstructs indexes from immutable local/evidence/regional objects and reconstructs local-evidence links from source-jet identity.

## Generations

Local knowledge and regional semantic knowledge use their own generation counters. They do not increment the global SAA-6 store simply because a new local operating-point model was observed.

This preserves the distinction:

\[
GlobalCanonicalKnowledge
\neq
LocalNonlinearKnowledge.
\]

---

# SAA-7.5 Broader exact nonlinear representation search

## Objective

SAA-7.1 searched single target-independent monomial shears:

\[
w_t=z_t+c z^\alpha.
\]

SAA-7.5 expands the exact search family to multi-term polynomial shears:

\[
w_t=z_t+q(z_{\neg t})
\]

where

\[
q(z_{\neg t})=\sum_\alpha c_\alpha z^\alpha
\]

and no monomial depends on target coordinate \(z_t\).

## Exact inverse

Because \(q\) does not depend on its target coordinate,

\[
z_t=w_t-q(w_{\neg t}).
\]

The inverse is exact by construction.

## Polynomial automorphisms

Multiple exact shears may be composed:

\[
\Phi=S_m\circ\cdots\circ S_2\circ S_1.
\]

The exact inverse is the reverse composition:

\[
\Phi^{-1}=S_1^{-1}\circ S_2^{-1}\circ\cdots\circ S_m^{-1}.
\]

The current bounds are:

- at most 32 terms per polynomial shear;
- at most 4 composed transforms;
- at most 128 evaluated candidates;
- exact coefficient complexity bounded to 48 bits;
- retained Taylor order remains bounded by SAA-7.

## Grouped correction search

If an output contains

\[
y_0=z_0+z_1^2+z_1^3,
\]

SAA-7.5 can generate one grouped transform

\[
w_0=z_0+z_1^2+z_1^3
\]

rather than requiring separate search depth for each nonlinear term.

## Domain contraction

For

\[
w_t=z_t+\sum_\alpha c_\alpha z^\alpha,
\]

SAA bounds nonlinear excursion conservatively by

\[
E=\sum_\alpha |c_\alpha|\prod_i\rho_i^{\alpha_i}.
\]

The certified target radius becomes

\[
\rho'_t=\rho_t-E.
\]

If \(\rho'_t\le0\), the transform is rejected.

No coordinate transformation is allowed to manufacture an evidence domain larger than the evidence supports.

## Semantic consequence

Any changed polynomial coordinate is assigned unresolved nonlinear semantics. Mathematical decoupling alone does not justify inheriting the old meaning.

Fresh candidate meaning, evidence, falsifier survival and independent review are required before a polynomial representative form becomes locally canonical.

---

# SAA-7.6 Differential-geometric representation analysis

## Objective

Algebraic decoupling is not the entire representation problem. A nonlinear mapping may have singular points, invariant directions or lower-dimensional behavior that only becomes visible through derivatives.

SAA-7.6 provides exact differential-geometric analysis of the retained finite jet polynomial.

## Exact Jacobian

At a qualified point \(r\), SAA evaluates

\[
J_{ki}(r)=\frac{\partial y_k}{\partial r_i}.
\]

All arithmetic remains rational when the jet and point are rational.

SAA computes exact row-reduced rank and the right nullspace.

The local tangent nullspace is

\[
\mathcal N_r=\ker J(r).
\]

The local output-manifold dimension is recorded as

\[
d_r=rank(J(r)).
\]

## Local diffeomorphism

For square maps, a local diffeomorphism candidate exists when

\[
rank(J)=n.
\]

This is still a local retained-jet statement.

## Exact Hessian

SAA evaluates

\[
H^{(k)}_{ij}(r)=\frac{\partial^2 y_k}{\partial r_i\partial r_j}
\]

and explicitly counts cross-coordinate curvature terms.

This distinguishes nonlinear self-curvature from cross-coordinate interaction.

## Constant invariant distribution across the jet

A more powerful test does not evaluate the Jacobian at only one point.

For a constant direction \(d\), SAA asks whether

\[
D_d y_k(z)=0
\]

as an exact polynomial for every output in the retained jet.

The derivative polynomial coefficients form a matrix whose columns correspond to input coordinates. Its exact nullspace yields constant directions that annihilate the complete retained derivative polynomial, not merely one Jacobian sample.

These directions form a constant distribution. Constant vector fields commute, so the detected distribution is integrable.

This supports a stronger local-model redundancy signal than a single-point rank loss.

## Conservative singularity handling

If the Jacobian loses rank at one point but there is no invariant direction across the retained derivative polynomial, SAA reports:

`LOCAL_SINGULAR_REPRESENTATION`.

It does not collapse the dimension.

If a constant invariant direction exists across the retained jet, SAA reports:

`INVARIANT_REDUNDANT_DIRECTION_DETECTED`.

The distinction protects against mistaking a nonlinear singularity for a meaningless variable.

## Current geometry boundary

Implemented:

- exact Jacobian;
- exact Hessian;
- exact rank;
- exact tangent nullspace;
- local manifold dimension;
- local diffeomorphism test;
- constant invariant distribution;
- integrability of detected constant distribution.

Not yet claimed:

- general nonconstant Frobenius distributions;
- global manifold topology;
- certified atlas construction;
- global diffeomorphism;
- differential invariants under arbitrary coordinate maps.

---

# SAA-7.7 Observability and controllability semantics

## Objective

A mathematically independent coordinate is not necessarily useful if it cannot be observed or controlled.

SAA-7.7 introduces a bounded local gate for these questions.

## Representative-input observability

For the nonlinear static output map, OIEC first asks whether representative input perturbations are locally distinguishable from outputs.

The current exact gate requires:

\[
rank(J)=n_{input}
\]

with no invariant unobservable input direction in the retained jet.

If this fails, SAA reports:

`REPRESENTATIVE_INPUT_NOT_LOCALLY_OBSERVABLE`.

## Static equations do not prove controllability

If only a static map is supplied, SAA may establish local input observability, but controllability remains unresolved.

The status is:

`OBSERVABLE_CONTROLLABILITY_REQUIRES_DYNAMIC_MODEL`.

This prevents OIEC from deriving a dynamic control claim from an algebraic input-output relationship.

## Exact local dynamic linearization

A dynamic gate may be supplied as exact matrices

\[
\delta\dot x=A\delta x+B\delta u,
\]

\[
\delta y=C\delta x.
\]

Every state receives an explicit semantic meaning.

The state dimension is currently capped at 12.

## Controllability rank

SAA constructs

\[
\mathcal C=[B\;AB\;A^2B\;\cdots\;A^{n-1}B]
\]

and evaluates its exact rational rank.

## Observability rank

SAA constructs

\[
\mathcal O=
\begin{bmatrix}
C\\
CA\\
CA^2\\
\vdots\\
CA^{n-1}
\end{bmatrix}
\]

and evaluates its exact rational rank.

The local dynamic state is accepted as controllable/observable only when both ranks equal the state dimension.

Statuses include:

- `DYNAMIC_UNOBSERVABLE_AND_UNCONTROLLABLE`
- `DYNAMIC_UNOBSERVABLE`
- `DYNAMIC_UNCONTROLLABLE`
- `LOCALLY_OBSERVABLE_AND_CONTROLLABLE`

## Current control-theory boundary

This milestone uses exact local Kalman rank conditions on a supplied local dynamic linearization.

It does not yet claim:

- nonlinear accessibility via Lie brackets;
- nonlinear observability rank conditions via Lie derivatives;
- global controllability;
- global observability;
- stabilization;
- reachable-set equality;
- robust controllability under uncertainty.

---

# Public API

The advanced nonlinear stack is available through:

```python
from ourd.egcf.nonlinear import ...
```

Core modules remain independently importable under `ourd.egcf.algebra`.

---

# Qualification requirements

Dedicated CI runs SAA-7 and SAA-7.2 through SAA-7.7 on:

- Python 3.10;
- Python 3.12;
- Python 3.13.

The advanced qualification suite covers:

- exact polynomial acquisition;
- exact derivative multi-factorial conversion;
- rejection of self-reported exact evidence;
- separation of estimated evidence from exact identity;
- connected regional semantic stability;
- disconnected region rejection;
- representation regime changes;
- local store duplicate suppression;
- approximate evidence rejection from exact local store;
- SQLite projection rebuild;
- grouped polynomial shears;
- semantic re-resolution after polynomial transforms;
- full-rank local geometry;
- invariant direction detection;
- exact cross curvature;
- refusal to infer controllability from static maps;
- exact local controllability/observability qualification;
- blocking of uncontrollable dynamic state.

The ordinary repository CI remains required so nonlinear work cannot regress core OIEC, packaging, Tk GUI or OpenGL behavior.

---

# Further roadmap after SAA-7.7

The next steps should preserve the same representational discipline rather than broadening mathematical claims faster than evidence can support them.

## SAA-7.8 Nonlinear Lie-derivative and Lie-bracket rank conditions

Add bounded exact polynomial state dynamics and implement:

- nonlinear observability codistribution generated by gradients of repeated Lie derivatives;
- accessibility distribution generated by control vector fields and bounded Lie brackets;
- exact rank at qualified operating points;
- semantic meaning attached to state and control directions;
- explicit distinction between local weak observability/accessibility and global properties.

This extends SAA-7.7 beyond linearized Kalman ranks without pretending local Lie-rank tests are global control proofs.

## SAA-7.9 Validated regional nonlinear envelopes

Move from overlapping pointwise Taylor boxes toward certified regional models using bounded remainder evidence.

Candidate methods:

- interval Taylor models;
- rational interval arithmetic;
- validated automatic differentiation;
- Bernstein polynomial bounds;
- sum-of-squares certificates for polynomial inequalities where practical.

Goal:

\[
LocalJets + CertifiedRemainders
\rightarrow
ValidatedRegionalBehavior.
\]

Only this kind of evidence should be allowed to strengthen a local nonlinear relation toward a genuinely regional mathematical claim.

## SAA-7.10 Global nonlinear equivalence research layer

Investigate stronger equivalence tools while keeping them outside canonical admission until their assumptions are proved.

Candidates:

- polynomial automorphism normal forms;
- differential invariants;
- feedback equivalence;
- conjugacy and semiconjugacy;
- bisimulation-like continuous-system relations;
- differential-algebraic invariants.

Global equivalence should remain an explicit theorem/evidence object, never an inference from matching local jets.

## SAA-7.11 Koopman and Carleman discovery aids

Add Koopman/Carleman representations only as search and approximation layers initially.

They may help discover latent coordinates or operator structure, but finite lifted approximations must not receive exact canonical-equivalence status.

## SAA-8 Canonical reasoning algorithms

Represent explicit reasoning procedures as bounded algorithms:

\[
R=(V,E,C,I,T)
\]

with:

- reasoning operators;
- dependency graph;
- conditions;
- invariants;
- termination rules;
- evidence requirements;
- semantic contracts.

Examples include falsification-first search, causal decomposition, differential diagnosis, backward proof search and evidence-first synthesis.

## SAA-8.1 Reasoning-topology equivalence

Canonicalize explicit reasoning graphs and classify:

- exact equivalent reasoning algorithms;
- generalizations;
- specializations;
- compositions;
- near variants;
- genuinely new reasoning structure.

Private chain-of-thought is not the storage target. Only explicit auditable reasoning artifacts enter this layer.

## SAA-8.2 Reasoning semantic representativeness

Apply the same representation principle to reasoning-state variables.

If a reasoning dimension mixes multiple meanings, mark it non-representative and seek a better reasoning-state coordinate system before claiming algorithm novelty.

## SAA-9 Evidence-grounded semantic ontology

Build canonical concept identities over qualified mathematical behavior and evidence.

Semantic similarity is retrieval evidence, not equivalence.

Potential relations:

- `SAME_MEANING_AS`
- `SPECIALIZES_MEANING`
- `GENERALIZES_MEANING`
- `UNIT_TRANSFORM_OF`
- `DOMAIN_RESTRICTION_OF`
- `CAUSES`
- `MEASURES`
- `CONTROLS`
- `OBSERVES`

Each strong semantic edge must carry evidence and falsifiers.

## SAA-9.1 Units, dimensions and physical-domain semantics

Integrate dimensional analysis and unit-aware semantic contracts so equations that are algebraically similar but physically incompatible cannot collapse into the same canonical meaning.

## SAA-9.2 Semantic contradiction and revision

When new evidence contradicts a stored meaning:

- do not mutate history silently;
- create a contradiction event;
- isolate dependent reasoning paths;
- requalify affected canonical relations;
- supersede only with explicit evidence lineage.

## SAA-10 Qualified problem-to-algorithm fit

Given a new problem, derive representative requirements and search the Canonical Algorithm Store by:

- meaning;
- mathematical behavior;
- bounds;
- evidence strength;
- risk;
- computational cost;
- performance;
- observability/controllability requirements;
- domain validity.

The system should distinguish known from suitable.

## SAA-10.1 Retrieve-first reasoning

Make the default control path:

```text
Problem
→ Representative requirements
→ Retrieve known canonical algorithms
→ Evaluate fit
→ Reuse / adapt / reject
→ Search only for missing algorithmic structure
```

This is the practical mechanism that prevents repeated reinvention.

## SAA-11 Controlled algorithm adaptation

When the best known algorithm is insufficient, define

\[
\Delta=Requirements-BestQualifiedFit.
\]

Use IURM to vary one representative dimension at a time and compare the adapted algorithm against its parent.

No adaptation self-certifies improvement.

## SAA-11.1 Algorithm qualification and evolutionary lineage

Persist:

- parent algorithm;
- changed dimension;
- predicted improvement;
- falsifier;
- benchmark evidence;
- failure evidence;
- resulting qualification status.

This creates an auditable evolutionary tree rather than opaque model drift.

## SAA-12 Closed intelligence-improvement loop

The target loop is:

```text
Problem
→ Meaning
→ Representative form
→ Retrieve
→ Fit
→ Identify gap
→ Generate bounded candidate
→ Falsify
→ Qualify
→ Canonicalize
→ Store
→ Reuse
```

The intelligence substrate grows only when new qualified structure is discovered.

## SAA-12.1 Failure-memory algebra

Canonicalize important failed algorithms and failed reasoning paths separately from successful canonical knowledge.

A future proposal can then be recognized as structurally equivalent to a known failed approach before expensive repetition.

## SAA-12.2 OIEC-Bench integration

Make OIEC-Bench a release gate for intelligence claims.

Track longitudinally:

- factual precision;
- unsupported-claim rate;
- meaning-path integrity;
- semantic misrepresentation detection;
- representative-coordinate recovery;
- false progress certification;
- repeated error rate;
- grounded error reduction;
- false canonical admission rate;
- known-algorithm reuse;
- cost per verified task.

The flagship longitudinal question remains:

> Does OIEC become measurably less wrong, less ambiguous and more efficient as qualified work accumulates?

## Production integration

After the algebraic milestones are individually qualified, integrate them into the runtime decision path in stages:

1. read-only retrieval and diagnostics;
2. advisory representation search;
3. governed semantic-resolution objectives;
4. canonical-store-backed algorithm selection;
5. bounded adaptation proposals;
6. qualification-gated reuse;
7. benchmark-controlled closed improvement.

Runtime integration should lag mathematical capability. The system should first prove that a representation layer is deterministic, bounded and rebuildable before allowing it to steer autonomous actions.

---

# Final invariant

The advanced nonlinear program is governed by:

\[
\boxed{
BetterIntelligence
=
BetterEvidence
+BetterMeaning
+BetterRepresentation
+QualifiedReusableStructure
}
\]

not by merely accumulating more equations or more model output.

A nonlinear equation becomes valuable canonical knowledge only when OIEC can state what it means, where that meaning holds, how the equation was evidenced, whether the representation is independent, and which observations would invalidate the claim.
