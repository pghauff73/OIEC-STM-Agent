# SAA-6 Canonical Representative Algorithm Form

SAA-6 is the admission layer that turns a qualified SAA-5 representative-input candidate into a canonical representative algorithm form.

The governing invariant is:

\[
\boxed{
CanonicalRepresentative
=
Independent
\land Minimal
\land Decoupled
\land Admissible
\land SemanticallyResolved
\land ExactlyBounded
}
\]

A source representation is not eligible merely because its transfer matrix is known. A representative form must first pass SAA-4.1, SAA-5, SAA-5.1, SAA-5.2, and SAA-5.3.

## 1. Required upstream evidence

SAA-6 requires:

- the SAA-1 `CanonicalAlgorithmIR`;
- the exact SAA-2 source `NormalizationContract`;
- the SAA-4 `CanonicalMIMOCoupling`;
- a SAA-5 `RepresentativeInputSearch` whose best candidate is exact, minimal, independent, decoupled, and admissible;
- one SAA-5.3 semantic issue per representative input;
- one candidate semantic meaning per issue;
- one `SEMANTICALLY_RESOLVED` resolution per issue.

It fails closed if any of these are missing.

## 2. Representative coordinate relation

For source normalized inputs

\[
u\in[0,1]^m,
\]

SAA-5 produces a representative coordinate map

\[
v=Qu.
\]

The corresponding exact representative transfer matrix satisfies

\[
y=G_v(q)v.
\]

The source representation remains provenance. `Q` is not itself the canonical input coordinate because a row of `Q` can map the source unit box outside `[0,1]`.

## 3. Exact representative bounds

For representative coordinate

\[
v_i=\sum_j Q_{ij}u_j,
\]

where every source coordinate satisfies `0 <= u_j <= 1`, the exact image interval of the source unit box is

\[
v_{i,\min}=\sum_j\min(0,Q_{ij}),
\]

\[
v_{i,\max}=\sum_j\max(0,Q_{ij}).
\]

The reachable width is

\[
w_i=v_{i,\max}-v_{i,\min}.
\]

SAA-6 records this using the boundary policy:

`EXACT_LINEAR_IMAGE_OF_NORMALIZED_SOURCE_BOX`.

A nonzero representative input with zero reachable width fails closed.

## 4. Re-normalization to [0,1]

The canonical coordinate is

\[
r_i=
\frac{v_i-v_{i,\min}}{w_i},
\qquad
r_i\in[0,1].
\]

The transform is exactly reversible on the bounded representative interval:

\[
v_i=v_{i,\min}+w_i r_i.
\]

Because SAA-3 and SAA-4 transfer functions represent deviation dynamics, the offset disappears:

\[
\delta v_i=w_i\delta r_i.
\]

Therefore every representative transfer column is scaled by its exact width:

\[
G_r(q)[:,i]=w_i G_v(q)[:,i].
\]

This is the first SAA stage where a newly discovered representative coordinate is again a canonical `[0,1]` coordinate.

## 5. Semantic admission

SAA-6 does not trust source labels or model-proposed descriptions.

For every representative input, it requires:

- a `SemanticRepresentationIssue` describing that representative coordinate;
- a `SemanticCandidateMeaning`;
- a matching `SemanticResolution`;
- semantic output-footprint fit of 10000 basis points;
- grounded evidence;
- survival of declared falsifiers;
- independent semantic review.

Only `SEMANTICALLY_RESOLVED` inputs may enter the canonical form.

Thus:

\[
\boxed{
MathematicalRepresentative
\not\Rightarrow
CanonicalRepresentative
}
\]

and:

\[
\boxed{
CanonicalRepresentative
=
MathematicalRepresentative
\land SemanticRepresentative
}
\]

## 6. Canonical input order

A SAA-5 representative candidate has one-to-one input/output pairing after exact decoupling.

SAA-6 orders representative inputs by their unique paired output index. This removes superficial input-port ordering from representative behavior identity while retaining the ordered output interface.

The current SAA-6 claim is therefore ordered with respect to outputs.

## 7. Three signatures

SAA-6 deliberately emits three nested identities.

### 7.1 Mathematical representative signature

`mathematical_representative_signature`

binds:

- continuous/discrete domain;
- canonical transform variable;
- normalized sample interval where relevant;
- representative input count;
- output count;
- `[0,1]` target input domain;
- canonical input order;
- exactly re-normalized representative transfer matrix.

It excludes source coordinate names and source transformation provenance.

### 7.2 Semantic representative signature

`semantic_representative_signature`

binds each canonical representative input to:

- normalized semantic meaning text;
- paired output;
- expected output footprint;
- explicitly excluded outputs.

Issue IDs, evidence IDs, and review IDs are audit provenance rather than semantic identity.

### 7.3 Representative behavior signature

\[
ID_{behavior}
=
Hash(
ID_{math},
ID_{semantic}
).
\]

This is the strongest SAA-6 representation-independent behavior identity.

## 8. Conservative structural binding

SAA-6 also emits `canonical_algorithm_signature`.

For safety, v1 binds the representative behavior signature to the current SAA-1 source structural hash:

\[
ID_{algorithm}
=
Hash(
ID_{behavior},
ID_{source-structure}
).
\]

The policy is recorded as:

`CONSERVATIVE_SOURCE_STRUCTURE_BINDING`.

This can produce false novelty when two implementations have equivalent representative behavior but structurally different source expressions. That is intentional in v1 because:

\[
Cost(FalseEquivalent) > Cost(FalseNovel).
\]

A future representative structural rewrite can relax this conservatism after qualification.

## 9. Source representation remains provenance

The SAA-6 audit record retains:

- source MIMO signature;
- source normalization contract and canonical signature;
- source structural hash;
- SAA-5 search audit hash;
- representative candidate signature;
- source-to-representative projection;
- representative boundary signatures;
- semantic issue signatures;
- semantic candidate signatures;
- semantic resolution signatures.

These do not replace the representative behavior identity.

## 10. Store eligibility

A successful result has:

`canonical_admission_eligible = true`

and:

`store_status = ELIGIBLE_CANONICAL_REPRESENTATIVE_FORM`.

This means the object is eligible to become a canonical Algorithm Store record. SAA-6 does not yet persist or index it in the Algorithm Store. Persistent canonical-store integration remains a later milestone.

## 11. Zero effective input form

If SAA-5 proves that every declared input has zero behavioral effect, the representative input dimension is exactly zero.

SAA-6 accepts this degenerate quotient with:

- zero representative inputs;
- empty semantic issue set;
- empty representative input columns;
- a deterministic canonical representative signature.

The declared source inputs remain provenance only.

## 12. Non-claims

SAA-6 v1 does not claim:

- dynamic/rational input-coordinate transformations beyond the SAA-5 constant transform family;
- nonlinear representative coordinates;
- semantic synonym/ontology canonicalization beyond whitespace normalization and case folding;
- output-coordinate canonicalization;
- representative structural rewriting;
- persistent Algorithm Store indexing;
- automatic qualification of source documentation as semantic truth.

These remain later milestones.

## 13. Resulting pipeline

The implemented pipeline is now:

```text
SAA-1 structural IR
    ↓
SAA-2 exact source normalization
    ↓
SAA-3 linear dynamics
    ↓
SAA-4 MIMO coupling
    ↓
SAA-4.1 representation gate
    ↓
SAA-5.1 behavioral minimality
    ↓
SAA-5 representative basis search
    ↓
SAA-5.2 admissibility
    ↓
SAA-5.3 semantic resolution
    ↓
SAA-5.4 semantic propagation
    ↓
SAA-6 exact representative boundary determination
    ↓
SAA-6 [0,1] re-normalization
    ↓
Canonical Representative Algorithm Form
```

The central SAA-6 rule is:

\[
\boxed{
The canonical algorithm is identified from the smallest admissible decoupled input basis whose meanings are resolved and whose coordinates have been re-bounded into a common canonical domain.
}
\]
