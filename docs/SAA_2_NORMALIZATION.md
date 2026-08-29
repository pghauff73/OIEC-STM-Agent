# SAA-2 Bounded 0–1 Normalization

SAA-2 adds the numerical coordinate-normalization layer to the Searchable Algebra of Algorithms. It builds on the SAA-1 structural IR and deliberately makes no state-space, transfer-function, MIMO, Taylor-series, or global dynamic-equivalence claims.

## Objective

For every bounded scalar numerical coordinate, SAA-2 defines the reversible affine transform

\[
\hat{x}=\frac{x-x_{\min}}{x_{\max}-x_{\min}},
\qquad 0\leq \hat{x}\leq1.
\]

The inverse is

\[
x=x_{\min}+\hat{x}(x_{\max}-x_{\min}).
\]

The same form is used for inputs, parameters, states, and outputs. SAA-2 never silently clips values outside a declared bound.

## Why bounds are explicit

Canonical normalization must not invent an operating range. Every coordinate therefore requires a bound contract with a declared provenance class:

- `EXACT_BOUND`
- `DOMAIN_BOUND`
- `ENGINEERING_BOUND`
- `OBSERVED_BOUND`
- `APPROXIMATE_BOUND`

`EXACT_BOUND` and `DOMAIN_BOUND` are treated as exact-strength normalization. Engineering, observed, and approximate bounds downgrade the normalization to approximate strength.

A non-finite, zero-width, or inverted interval fails closed.

## Audit identity versus canonical identity

SAA-2 intentionally maintains two hashes.

`contract_hash` is the audit identity. It includes the actual minima, maxima, units, provenance, and characteristic time. Two different source coordinate systems therefore have different audit hashes.

`canonical_signature` describes the normalized coordinate system. It includes port role, position, source data type, shape, target interval `[0,1]`, affine-transform semantics, and exact/approximate strength. It deliberately excludes source offset, scale, unit, and provenance text.

Consequently two exact affine coordinate systems such as metres and millimetres can have different audit identities but the same canonical normalization identity.

Changing from an exact bound to an observed/approximate bound changes the canonical normalization strength and therefore the canonical signature.

## Scalar-only SAA-2 v1

This milestone supports scalar numeric coordinates only. Supported SAA-1 data-type markers are:

- `scalar`
- `number`
- `float`
- `real`
- `int`
- `integer`

Vector/tensor ports fail closed because SAA-2 v1 does not yet have a per-component bound contract. That avoids silently applying one scalar range to heterogeneous dimensions.

## No nonlinear squashing

SAA-2 does not normalize an unbounded variable using sigmoid, tanh, logistic, or another nonlinear squashing function. Such a transform changes derivatives and dynamics and would therefore contaminate later SAA dynamic-equivalence analysis.

An unbounded variable must first receive a justified bounded operating domain from the surrounding system, for example Boundary Determination, before it can enter the exact SAA-2 pipeline.

## Dimensionless time

Where a characteristic time `T_c` is supplied, SAA-2 defines

\[
\tau=\frac{t}{T_c}.
\]

The inverse is `t = tau * T_c`. Characteristic time must be finite and positive. The exact numeric value and unit are retained in the audit hash but removed from canonical scale identity.

SAA-2 does not yet construct `s`-domain or `z`-domain representations. That is deferred to later dynamic canonicalization milestones.

## Combined normalized algorithm signature

SAA-1 and SAA-2 can be combined using `normalized_algorithm_signature(structural_ir, contract)`.

The signature binds:

- SAA-1 canonicalizer version, structural hash, and structural strength;
- SAA-2 normalizer version, canonical normalization signature, and normalization strength.

Thus source renaming and exact affine rescaling can preserve a normalized structural identity, while a real structural change still changes the combined signature.

## Fail-closed invariants

SAA-2 enforces the following invariants:

1. Every declared scalar input, parameter, state, and output has exactly one normalization binding.
2. Unknown or missing positions are rejected.
3. Bounds are finite and have positive width.
4. Normalized inverse inputs are restricted to `[0,1]`.
5. Source values outside declared bounds are rejected rather than clipped.
6. Vector-shaped coordinates are rejected in SAA-2 v1.
7. Approximate bounds are never promoted to exact normalization.
8. Canonical signature and audit identity are separate.
9. Normalizer version participates in both identities.

## Non-claims

SAA-2 does not establish that two algorithms are dynamically equivalent. Matching normalized structural signatures establishes only that the SAA-1 structures match and their numerical interfaces have compatible canonical 0–1 coordinate contracts at the recorded strength.

State-space reduction, transfer forms, input/output coupling, MIMO invariant forms, and nonlinear Taylor jets remain later SAA milestones.
