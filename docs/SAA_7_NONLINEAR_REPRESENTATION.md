# SAA-7 and SAA-7.1: Local Nonlinear Representative Reasoning

## Purpose

SAA-7 extends the Searchable Algebra of Algorithms beyond exact linear representative dynamics into bounded nonlinear local structure. It does not weaken the SAA-6 representativeness rule. It applies nonlinear analysis only after SAA-6 has produced independent, minimal, decoupled, admissible, semantically resolved and exactly bounded representative inputs.

The governing principle remains:

> Coupling detected implies that the current input representation is non-representative.

For nonlinear systems the principle becomes:

> A nonlinear interaction that causes one representative input to affect multiple semantic output roles, or that requires several representative inputs inside one unresolved interaction term, is evidence that the current local coordinate meaning may be incomplete.

SAA-7 therefore separates two questions:

1. What exact local nonlinear equation is present around a qualified operating point?
2. Can a better nonlinear coordinate representation make that equation more independent and semantically clear?

## SAA-7 exact Taylor-jet representation

A local map is represented in normalized SAA-6 representative coordinates `r` around an exact expansion point `c`:

\[
y_k(r) = \sum_{|\alpha|\le p} a_{k,\alpha}(r-c)^\alpha + O(\|r-c\|^{p+1}).
\]

The stored coefficient `a[k,alpha]` is the exact Taylor polynomial coefficient. SAA-7 does not infer a global function from this finite jet.

### Hard limits

The first implementation is intentionally bounded:

- maximum input dimension: 8;
- maximum output dimension: 8;
- maximum Taylor order: 4;
- maximum nonzero terms: 512;
- exact rational coefficients only;
- exact expansion point only;
- exact local validity box only.

Floats are rejected for exact canonicalization. Approximate nonlinear fitting belongs in a later evidence layer and cannot silently enter exact identity.

### Exact local domain

Every jet is attached to an exact normalized expansion point and positive local radius vector:

\[
|r_i-c_i|\le \rho_i,
\]

with the entire certified box required to remain inside the SAA-6 normalized domain `[0,1]^n`.

The validity radius participates in the scoped signature. Consequently two jets may have identical coefficients but different certified domains.

### Identity separation

SAA-7 emits separate identities:

- `coefficient_signature`: parent representative meaning, expansion point, order and exact Taylor coefficients;
- `scope_signature`: coefficient identity plus certified local validity box;
- `local_behavior_signature`: coefficient identity, scope and nonlinear coupling assessment.

This prevents domain evidence from being confused with algebraic coefficient identity.

### Local equivalence only

Finite Taylor-jet matching never establishes global nonlinear equivalence.

The strongest first-version comparison status is:

`EXACT_LOCAL_JET_MATCH_ON_INTERSECTION`

and always carries:

`global_equivalence_eligible = False`.

This is a deliberate false-equivalence safeguard.

## Nonlinear semantic coupling

SAA-7 inspects each nonzero Taylor monomial.

A term is a nonlinear representational warning when either:

1. more than one representative input appears in the term; or
2. an input contributes to an output other than its SAA-6 paired output.

Examples:

\[
y_0=r_0+r_1^2
\]

is non-representative when `r1` is semantically paired with `y1`.

Likewise:

\[
y_0=r_0+r_0r_1
\]

contains an unresolved cross-coordinate interaction.

By contrast:

\[
y_0=r_0+r_0^2
\]

is not automatically a semantic defect. It can represent nonlinear self-behaviour of a correctly identified independent coordinate.

Statuses are:

- `NONLINEAR_REPRESENTATIVE`;
- `NONLINEAR_SEMANTIC_MISREPRESENTATION`.

## SAA-7.1 nonlinear representative-coordinate search

SAA-7.1 searches for a better local input basis only after SAA-7 detects nonlinear representational defects.

The first search family is deliberately narrow and exactly invertible: triangular polynomial shears.

For deviations `z=r-c`, one candidate has the form

\[
w_t = z_t + q(z_{\neg t}),
\]

where `q` does not contain the target coordinate `z_t`.

The inverse is exact:

\[
z_t = w_t-q(w_{\neg t}).
\]

This avoids pretending that a numerically fitted nonlinear transform is invertible.

### Example

Given

\[
y_0=z_0+z_1^2,\qquad y_1=z_1,
\]

SAA-7.1 can derive

\[
w_0=z_0+z_1^2,\qquad w_1=z_1,
\]

and the local equation becomes

\[
y_0=w_0,\qquad y_1=w_1.
\]

The mathematical coupling disappears.

That does **not** mean `w0` may inherit the old semantic label attached to `z0`.

## Conservative domain transformation

Coordinate transforms can reduce the region for which a local representation is certified.

For a shear

\[
w_t=z_t+c z^\alpha,
\]

SAA-7.1 bounds the maximum nonlinear excursion over the current certified local box and reduces the target radius before accepting the transformed jet.

If the transform consumes the available radius, the candidate is rejected.

Thus a better-looking representation cannot acquire a larger validity domain merely by coordinate manipulation.

## Search bounds

The initial search engine is bounded to:

- 128 evaluated candidates;
- depth 2;
- Taylor degree at most 4;
- exact rational transform coefficients with bounded bit complexity;
- transformations generated from observed problematic Taylor terms and a nonzero paired linear response.

Search failure means only:

`NONLINEAR_REPRESENTATION_UNRESOLVED`

or

`NONLINEAR_SEARCH_BUDGET_EXHAUSTED`.

It does not prove that no nonlinear representative coordinate system exists.

## Semantic re-resolution after a nonlinear transform

A transformed coordinate is a new semantic object.

For every changed coordinate SAA-7.1 creates `NonlinearSemanticRepresentationIssue` with questions including:

- What independent domain quantity does this new coordinate represent?
- Does the previous meaning survive the nonlinear change?
- Which mechanism explains the nonlinear combination?
- Which outputs should change when only this coordinate changes?
- What evidence would falsify the proposed meaning?
- Does the meaning remain stable across more than one expansion point?

These issues are compatible with the existing SAA semantic candidate and resolution machinery.

A nonlinear coordinate cannot become locally canonical until its candidate meaning has:

- complete output-footprint fit;
- grounded evidence;
- survived declared falsifiers;
- independent review;
- `SEMANTICALLY_RESOLVED` status.

The issues also propagate through the existing OIEC governance consumers. IURM and Algorithm Store remain blocking consumers.

## Canonical local nonlinear form

After mathematical decoupling and semantic re-resolution, SAA-7.1 emits `CanonicalNonlinearRepresentativeForm`.

It carries:

- the SAA-6 parent representative identity;
- source jet identity;
- transformed exact Taylor jet;
- exact transform lineage;
- resolved new input meanings;
- semantic signature;
- local representative behavior signature;
- audit hash.

Its qualification status is:

`ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM`

but it explicitly carries:

`global_equivalence_eligible = False`.

The existing persistent Canonical Algorithm Store is therefore not automatically populated by SAA-7.1 in this milestone.

## What SAA-7 and SAA-7.1 do not claim

They do not yet prove:

- global nonlinear equivalence;
- analytic convergence of a Taylor series outside the supplied local evidence box;
- correctness of approximate derivative estimates;
- nonlinear observability or controllability equivalence;
- arbitrary polynomial-diffeomorphism equivalence;
- differential-geometric equivalence;
- Koopman equivalence;
- semantic stability across operating regimes;
- hybrid-mode nonlinear equivalence;
- automatic persistent nonlinear canonical-store admission.

## Updated SAA pipeline

```text
SAA-1   Structural IR
SAA-2   Exact normalization
SAA-3   Linear dynamics
SAA-4   MIMO coupling
SAA-4.1 Representation gate
SAA-5.1 Input minimality
SAA-5   Representative basis discovery
SAA-5.2 Transform admissibility
SAA-5.3 Semantic resolution
SAA-5.4 Governance propagation
SAA-6   Canonical representative algorithm form
SAA-6.1 Persistent canonical store
SAA-6.2 Canonical indexes
SAA-6.3 Uniqueness/equivalence lookup
SAA-6.4 Algorithm relation graph
SAA-7   Exact bounded local Taylor jets
SAA-7.1 Nonlinear representative-coordinate search
```

## Further milestones

The recommended progression after SAA-7.1 is:

### SAA-7.2 Nonlinear evidence acquisition

Create governed finite-difference, automatic-differentiation and symbolic derivative adapters. Separate exact symbolic derivatives from measured/estimated derivatives, attach uncertainty and provenance, and prohibit approximate derivatives from entering exact jet identity.

### SAA-7.3 Multi-point semantic stability

Repeat local jets at several qualified expansion points. Determine whether a proposed representative meaning survives movement across the operating domain. A meaning that exists only at one point remains local.

### SAA-7.4 Nonlinear Canonical Store

Persist qualified local nonlinear forms separately from global canonical algorithms. Index by parent algorithm, expansion point, Taylor order, local scope, nonlinear coefficient signature and semantic signature. Never merge local forms into a global identity without stronger evidence.

### SAA-7.5 Broader exact coordinate transforms

Extend the search family from triangular shears to bounded triangular polynomial automorphisms and formally inverted near-identity jets. Preserve exact inverse proofs and domain contraction.

### SAA-7.6 Differential-geometric representation tests

Add Jacobian-rank, local-diffeomorphism and distribution/integrability checks. These can tell OIEC when an apparently useful coordinate change is locally impossible or when a lower-dimensional manifold is indicated.

### SAA-7.7 Observability and controllability semantics

For nonlinear state systems, test whether proposed semantic coordinates remain observable and controllable rather than merely algebraically decoupled.

### SAA-8 Reasoning algorithms as canonical objects

Represent explicit reasoning paths as bounded operator graphs with conditions, invariants, evidence requirements and termination. Apply the same uniqueness, representativeness and semantic-resolution rules to reasoning procedures themselves.

### SAA-8.1 Reasoning-topology equivalence

Compare alternative reasoning graphs under qualified operator/topology transformations. Distinguish identical reasoning algorithms, specializations, generalizations and genuinely novel compositions.

### SAA-9 Semantic ontology and concept identity

Build evidence-grounded concept equivalence and synonym resolution so algorithms can be retrieved by what their variables mean, not merely by literal labels. Semantic similarity remains retrieval guidance; evidence is required for equivalence.

### SAA-10 Qualified problem-fit engine

Given a problem, derive representative requirements and rank known canonical algorithms by semantic compatibility, mathematical fit, evidence strength, invariants, risk, performance and resource cost.

### SAA-11 Delta and adaptation engine

When the best known algorithm is insufficient, isolate the exact capability delta and vary one qualified dimension at a time under IURM. Candidate improvements cannot self-certify.

### SAA-12 Closed retrieve-fit-improve-qualify loop

Complete the governed intelligence-growth cycle:

```text
Problem
  -> representative meaning
  -> retrieve canonical algorithms
  -> evaluate qualified fit
  -> isolate deficiency
  -> generate bounded adaptation
  -> test/falsify
  -> independently qualify
  -> canonicalize if genuinely new
  -> expand Algorithm Store
```

## Core epistemic invariant

The nonlinear roadmap keeps one rule above all others:

> Better mathematical fit is not automatically better meaning, and better local representation is not automatically global truth.

SAA grows only when mathematics, semantics, evidence and scope agree.
