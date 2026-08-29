# SAA-3 Canonical Linear Dynamics

SAA-3 is the first dynamic-equivalence layer in the Searchable Algebra of Algorithms. It builds on SAA-1 structural canonicalization and SAA-2 bounded coordinate normalization, then derives a canonical SISO linear input-output transfer representation.

Its target is not merely “these algorithms look structurally alike.” Its target is the stronger, bounded statement:

> these exact normalized SISO linear models have the same rational input-output dynamics.

SAA-3 deliberately does not extend that claim to nonlinear systems, MIMO systems, arbitrary source-code graphs, delays, hybrid dynamics, or approximate pole-zero cancellation.

## 1. Linear deviation model

SAA-3 treats linear dynamics as deviation dynamics around the operating reference implicit in the SAA-2 bounds. For a continuous system,

\[
\delta y(s)=G(s)\,\delta u(s),
\qquad
G(s)=\frac{N(s)}{D(s)}.
\]

For a discrete system,

\[
\delta y(z)=G(z)\,\delta u(z),
\qquad
G(z)=\frac{N(z)}{D(z)}.
\]

Affine offsets from SAA-2 therefore do not enter the transfer gain. Only the coordinate widths enter the perturbation scaling.

## 2. Interface normalization

If the source input and output ranges have widths

\[
\Delta u=u_{\max}-u_{\min},
\qquad
\Delta y=y_{\max}-y_{\min},
\]

then

\[
\delta \hat u=\frac{\delta u}{\Delta u},
\qquad
\delta \hat y=\frac{\delta y}{\Delta y}.
\]

The normalized transfer therefore becomes

\[
\hat G=\frac{\Delta u}{\Delta y}G.
\]

This removes exact affine input/output scale differences while retaining the SAA-2 audit identity of the original coordinates.

SAA-3 v1 requires exactly one continuous-scalar input and exactly one continuous-scalar output. MIMO canonicalization is deferred.

## 3. Continuous-time normalization

SAA-2 supplies a characteristic time `T_c`. SAA-3 defines the dimensionless Laplace variable

\[
\sigma=sT_c,
\qquad
s=\frac{\sigma}{T_c}.
\]

Every continuous polynomial is rewritten by substitution:

\[
P(s)\rightarrow P\left(\frac{\sigma}{T_c}\right).
\]

For example,

\[
G_1(s)=\frac{1}{s+1},\quad T_c=1
\]

and

\[
G_2(s)=\frac{1000}{s+1000},\quad T_c=0.001
\]

both reduce to

\[
\hat G(\sigma)=\frac{1}{\sigma+1}
\]

when their interface scaling is otherwise identical.

A characteristic time is mandatory for SAA-3. The layer will not silently treat source time as canonical time.

## 4. Discrete-time normalization

For discrete systems, `z` is already dimensionless. SAA-3 therefore keeps the rational `z` polynomial and canonicalizes the sampling interval relative to SAA-2 characteristic time:

\[
\Delta\tau=\frac{T_s}{T_c}.
\]

`T_s` is mandatory for a discrete SAA-3 model. Two `G(z)` forms with different dimensionless sampling intervals do not share a canonical signature.

## 5. Coefficient evidence strength

SAA-3 separates exact coefficient declarations from approximate floating-point observations.

The following source values are treated as exact declarations:

- integers;
- `fractions.Fraction` values;
- finite `decimal.Decimal` values;
- exact numeric strings such as `"1/3"`, `"0.125"`, or `"-2"`.

Python `float` values are treated as approximate evidence even when the displayed decimal is simple. They are converted deterministically for hashing, but they do not receive exact pole-zero cancellation.

SAA-2 normalization strength also participates. An observed or approximate bound downgrades the resulting SAA-3 dynamic strength.

The two primary strengths are:

- `EXACT_LINEAR_DYNAMICS`
- `APPROXIMATE_LINEAR_DYNAMICS`

Exact and approximate models do not share the same canonical signature merely because their displayed coefficients happen to match.

## 6. Exact rational canonicalization

SAA-3 accepts numerator and denominator coefficients in descending power order.

For exact models it performs the following deterministic reduction:

1. remove leading zero coefficients;
2. reject a zero denominator;
3. apply SAA-2 interface scaling;
4. apply continuous-time or discrete-time normalization;
5. compute the exact polynomial GCD of numerator and denominator over rational coefficients;
6. divide out the exact common factor;
7. scale numerator and denominator so the denominator is monic;
8. serialize every rational coefficient as an integer numerator/denominator pair;
9. hash the canonical payload.

Thus

\[
\frac{s^2+3s+2}{s^2+4s+3}
=\frac{(s+1)(s+2)}{(s+1)(s+3)}
\]

reduces exactly to

\[
\frac{s+2}{s+3}.
\]

This is a real input-output equivalence operation rather than a structural similarity heuristic.

## 7. Approximate models do not cancel near poles and zeros

For approximate models SAA-3 performs deterministic denominator normalization but does **not** cancel common-looking factors.

This is intentional. A pole at `-1.000001` and a zero at `-1.0` can produce important transient behavior even though a tolerance-based simplifier might erase both.

Approximate SAA-3 therefore records the warning and uses the policy:

`MONIC_ONLY_NO_APPROXIMATE_FACTOR_CANCELLATION`

A later evidence-driven approximation layer may introduce error-bounded model reduction, but it must do so with an explicit approximation certificate rather than hidden tolerances.

## 8. State-space entry path

SAA-3 also accepts bounded SISO state-space declarations.

Continuous form:

\[
\dot x=Ax+Bu,
\qquad
y=Cx+Du.
\]

Discrete form:

\[
x_{k+1}=Ax_k+Bu_k,
\qquad
y_k=Cx_k+Du_k.
\]

The transfer function is

\[
G(q)=C(qI-A)^{-1}B+D,
\]

where `q` is `s` before continuous normalization or `z` for discrete time.

The implementation uses the Faddeev-LeVerrier recurrence to construct the characteristic polynomial and the polynomial adjugate coefficients without introducing a NumPy/SciPy dependency. The resulting transfer is then sent through the same canonical rational reducer as an explicitly supplied transfer function.

Consequences:

- exact state-coordinate similarity scaling does not change the dynamic signature;
- an exactly unobservable or uncontrollable mode can disappear through exact transfer pole-zero cancellation;
- an explicit transfer form and an equivalent exact state-space form can share one SAA-3 signature.

SAA-3 calls this a **minimal rational input-output form**. It does not claim to construct a unique minimal state-space realization or canonical internal-state basis.

## 9. Canonical dynamic record

`CanonicalLinearDynamics` records:

- SAA-3 schema and dynamics version;
- continuous/discrete domain;
- canonical variable `SIGMA` or `Z`;
- reduced numerator and denominator;
- input-output dynamic order;
- relative degree;
- proper/improper status;
- dimensionless sample interval for discrete systems;
- exact/approximate dynamic strength;
- SAA-2 normalization signature used to construct the model;
- audit hash;
- canonical dynamic signature;
- reductions and warnings.

`audit_hash` retains source representation and the SAA-2 audit contract binding. `canonical_signature` contains only the normalized dynamic identity and evidence strength required for equivalence comparison.

## 10. Combined SAA-1 + SAA-2 + SAA-3 identity

`dynamic_algorithm_signature(structural_ir, normalization, dynamics)` binds all three layers:

```text
SAA-1 structural identity
        +
SAA-2 normalized coordinate identity
        +
SAA-3 normalized linear dynamic identity
        =
STRUCTURE_PLUS_NORMALIZED_LINEAR_IO_DYNAMICS
```

The function fails closed if the dynamic IR was built against a different SAA-2 normalization signature.

This produces the first SAA identity that carries an explicit dynamic-equivalence component.

## 11. Bounds on the implementation

To keep canonicalization finite and deterministic, SAA-3 v1 limits:

- state-space order to `12`;
- polynomial degree to `64`;
- interfaces to SISO continuous scalar coordinates.

The bounds can be revised in a later version with performance evidence.

## 12. Non-claims and deferred milestones

SAA-3 does not yet provide:

- MIMO transfer-matrix canonicalization;
- controllability/observability canonical state bases;
- balanced or modal realization;
- tolerance-based model reduction;
- nonlinear Taylor jets;
- Volterra or describing-function forms;
- transport delays;
- hybrid/event dynamics;
- automatic extraction of a linear model from an arbitrary SAA-1 graph;
- continuous-to-discrete or discrete-to-continuous conversion;
- persistent Algorithm Store indexing by dynamic signature.

Those belong to later SAA milestones.

The SAA-3 claim is deliberately narrower and stronger: for exact bounded normalized SISO linear models, equality of the canonical dynamic signature means equality of the reduced rational input-output dynamics in the recorded continuous or discrete normalized time domain.
