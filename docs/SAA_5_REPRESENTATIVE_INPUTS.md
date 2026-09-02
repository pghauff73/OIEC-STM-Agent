# SAA-4.1 and SAA-5 Representative Input Discovery

SAA-4.1 changes the interpretation of MIMO coupling in the Searchable Algebra of Algorithms. Coupling is no longer treated as a final descriptive property suitable for canonical Algorithm Store admission. It is treated as evidence that the declared input coordinates may be non-representative.

The governing invariant is:

\[
\boxed{\text{unresolved input coupling} \Rightarrow \text{non-representative source form}}
\]

SAA-5 then searches for a bounded, exact, behavior-preserving representative input basis. SAA-5.1 removes exact redundant input dimensions. SAA-5.2 checks transform invertibility and admissibility.

## 1. Source representation versus representative form

For the normalized transfer matrix

\[
Y(q)=G_s(q)U_s(q),
\]

`G_s` is the source representation. SAA-4's ordered and port-permutation signatures remain useful provenance identities, but a coupled source form is not eligible to define the canonical algorithm identity.

`assess_mimo_representation()` returns one of the following principal states:

- `REPRESENTATIVE_EXACT`
- `NON_REPRESENTATIVE_COUPLED`
- `NON_REPRESENTATIVE_REDUNDANT_INPUTS`
- `REPRESENTATION_UNRESOLVED_APPROXIMATE`
- `REPRESENTATION_UNRESOLVED_RANK_BUDGET`

Only `REPRESENTATIVE_EXACT` has `canonical_admission_eligible = true` at this stage.

A crossed diagonal matrix can still be representative because a pure one-to-one port pairing is not considered intrinsic coupling. SAA distinguishes trivial relabelling from mixed dimensions.

## 2. Exact structural coupling measure

SAA-5 measures exact coupling from the zero/nonzero support of the reduced rational transfer matrix.

For a candidate pairing between representative inputs and distinct outputs, every nonzero channel outside the pairing is counted as residual coupling. The best bounded one-to-one pairing is chosen and reported as `coupling_bp` on a 0–10000 basis-point scale.

A value of zero means every active representative input has exactly one distinct output channel under the selected pairing.

This measure is algebraic and exact for exact SAA-3/SAA-4 channels. It is deliberately separate from SAA-4's floating diagnostic frequency samples.

## 3. SAA-5.1: exact constant-input behavioral rank

Declared inputs may contain redundant dimensions even when no two columns are literal duplicates.

SAA-5.1 finds exact constant linear dependencies among complete rational transfer columns. For example, if

\[
G_3(q)=G_1(q)+G_2(q),
\]

then the third declared input is not an independent algorithmic dimension.

SAA constructs a finite exact coefficient-vector representation of every rational transfer column by clearing row denominators. Exact Fraction Gaussian elimination then gives pivot input columns and the constant behavioral rank

\[
r=\operatorname{rank}_{\mathbb{Q}} G(q)
\]

with respect to constant input-coordinate combinations.

The source behavior is factored as

\[
G_s(q)=G_b(q)P,
\]

where:

- `G_b` contains the independent pivot input columns;
- `P` is `source_to_basis_projection`;
- `r` is `effective_input_rank`.

This is stronger than duplicate/proportional-column removal because arbitrary exact constant column dependencies are detected.

The search is bounded by `MAX_RANK_VECTOR_TERMS`. Exceeding that limit produces an unresolved representation status rather than a heuristic rank claim.

### Scope of minimality

SAA-5.1 proves minimality only under exact constant linear input combinations. It does not yet prove minimality under rational dynamic, nonlinear, or hybrid coordinate transformations.

## 4. SAA-5: representative basis search

After redundancy removal, SAA seeks an invertible constant basis transform `T` on the reduced input space:

\[
G_r(q)=G_b(q)T.
\]

The corresponding representative coordinate is

\[
v=T^{-1}Pu_s.
\]

Thus

\[
G_r(q)v
=G_b(q)TT^{-1}Pu_s
=G_s(q)u_s.
\]

Every accepted candidate is checked by exact rational reconstruction. Sampled agreement is not sufficient.

### Search order

SAA-5 first evaluates the identity basis after SAA-5.1 redundancy reduction. If coupling remains, it searches bounded exact constant linear transforms generated from fixed algebraic probe points.

For an effective input rank `r`, SAA chooses `r` output rows and evaluates the corresponding exact rational submatrix at fixed canonical algebraic values of `q`. When the matrix is finite and nonsingular, its inverse gives a candidate input basis direction.

Continuous default probes:

- `0`
- `1`
- `-1`
- `2`
- `-2`

Discrete default probes:

- `1`
- `-1`
- `0`
- `2`
- `-2`

These are algebraic search coordinates, not physical frequency-response claims.

Candidate transform columns are scale-normalized so arbitrary gain scaling does not create unnecessary search variants.

The search is bounded by `MAX_REPRESENTATIVE_TRANSFORMS`. Exhaustion returns `REPRESENTATIVE_SEARCH_BUDGET_EXHAUSTED`; it never establishes non-equivalence.

## 5. Representative-form acceptance

A candidate is returned as `REPRESENTATIVE_FORM_CANDIDATE` only when all of the following hold:

1. input dimensions are independent after SAA-5.1;
2. the candidate has the exact minimal constant input rank;
3. residual exact support coupling is zero;
4. the transform preserves complete rational input-output behavior;
5. SAA-5.2 marks the transform admissible.

If a transform improves coupling but does not eliminate it, it is retained as `IMPROVED_NON_REPRESENTATIVE_CANDIDATE` rather than promoted.

If no bounded constant transform removes coupling, the result is:

`REPRESENTATIVE_FORM_UNRESOLVED_CONSTANT_LINEAR_SEARCH`

This is the trigger for a future dynamic or nonlinear representation-search milestone.

## 6. SAA-5.2: invertibility and admissibility

SAA-5.2 distinguishes two invertibility cases.

### Full invertibility

When source and representative input dimensions are equal:

\[
v=Qu_s,
\qquad
u_s=Sv,
\]

and both mappings are square exact inverses.

Status:

`FULLY_INVERTIBLE`

### Behavioral quotient invertibility

When redundant source dimensions were removed, a globally invertible map to the original coordinate tuple cannot exist because the source contains a behavioral nullspace.

SAA therefore requires exact invertibility on the behavioral quotient:

\[
QS=I_r.
\]

`Q` is the source-to-representative projection and `S` is an exact representative-to-source section. Any source input vector maps to the same representative behavior, while `S` provides one canonical source realization for a representative coordinate.

Status:

`INVERTIBLE_ON_BEHAVIORAL_QUOTIENT`

This is not a relaxation of behavior preservation. It explicitly removes input distinctions that have no independent effect on the algorithm output.

## 7. Constant-transform admissibility

SAA-5 currently searches exact real constant transforms only. Such transforms are memoryless, causal, and dynamically stable by construction.

A transform is admissible only if:

- the required full or quotient invertibility test succeeds;
- all coefficients are finite exact rational values;
- the largest numerator/denominator bit length does not exceed `MAX_TRANSFORM_COEFFICIENT_BITS`.

Exceeding the coefficient budget yields `INADMISSIBLE_TRANSFORM` even when the matrix algebraically decouples the system.

This prevents an extreme exact transform from being silently promoted as an operationally representative interface.

## 8. Re-normalization boundary

A general representative coordinate

\[
v=Qu_s
\]

need not remain in the original `[0,1]` coordinate range. Consequently SAA-5 marks non-selector transforms with `requires_renormalization = true`.

SAA-5 discovers the representative directions. A later canonical representative-form milestone must derive and qualify appropriate bounded coordinates for those directions before they become final Algorithm Store identity.

Pure selection/permutation projections can preserve existing normalized coordinates and do not necessarily require re-normalization.

## 9. Approximate dynamics

Approximate SAA-3/SAA-4 channels do not enter the exact representative-basis search.

They return:

`REPRESENTATIVE_FORM_UNRESOLVED_APPROXIMATE`

This follows the SAA rule that a false representative equivalence is more costly than failing to identify an equivalence that may exist.

## 10. Algorithm Store consequence

After SAA-4.1, the store pipeline should interpret source signatures as follows:

```text
SAA-4 source MIMO form
    ↓
representation assessment
    ↓
REPRESENTATIVE_EXACT?
├─ yes → eligible for the next canonical-form stage
└─ no
    ↓
SAA-5 representative-input search
    ↓
representative candidate found?
├─ yes → re-normalize / canonical representative form
└─ no  → retain source as provenance, not canonical algorithm identity
```

The governing distinction is:

\[
\boxed{\text{source representation} \neq \text{canonical algorithm representation}}
\]

whenever unresolved coupling or redundant declared input dimensions remain.

## 11. Non-claims

SAA-4.1/SAA-5/SAA-5.1/SAA-5.2 do not yet claim:

- arbitrary rational/dynamic input decoupling;
- Smith-McMillan canonical equivalence;
- output-coordinate correction;
- nonlinear coordinate discovery;
- Taylor-jet representative refinement;
- global physical feasibility of a future actuator mapping;
- final canonical representative Algorithm Store identity.

They establish a bounded exact constant-input representation-discovery layer and explicitly identify when a stronger search is still required.
