# SAA-4 MIMO Coupling and Static Decoupling

SAA-4 extends the Searchable Algebra of Algorithms from SAA-3 SISO linear dynamics to bounded multi-input/multi-output transfer matrices. It introduces canonical normalized MIMO identities, port-permutation equivalence, input/output coupling analysis, Relative Gain Array pairing, and an exact steady-state static decoupling transform.

SAA-4 deliberately does not claim full dynamic MIMO canonicalization under arbitrary polynomial input/output transformations. Smith-McMillan reduction, dynamic decouplers, MIMO state-space minimal realization, and nonlinear coupling remain later milestones.

## 1. Canonical normalized transfer matrix

For `p` outputs and `m` inputs, SAA-4 represents

\[
\hat{Y}(q)=G(q)\hat{U}(q)
\]

with

\[
G(q)=
\begin{bmatrix}
G_{11}(q) & \cdots & G_{1m}(q)\\
\vdots & \ddots & \vdots\\
G_{p1}(q) & \cdots & G_{pm}(q)
\end{bmatrix}.
\]

Every channel is canonicalized through SAA-3 after selecting the corresponding SAA-2 input and output normalization bindings. Thus channel dynamics use the same 0–1 normalized coordinate philosophy as the SISO layer.

The transform variable is:

- `SIGMA = s*T_c` for continuous dynamics;
- `Z` plus the normalized sample interval `T_s/T_c` for discrete dynamics.

SAA-4 v1 supports at most six inputs and six outputs.

## 2. Ordered MIMO identity

The primary MIMO identity preserves input/output order.

The `ordered_signature` hashes:

- MIMO version;
- continuous/discrete domain;
- canonical transform variable;
- input and output counts;
- normalized discrete sample interval where relevant;
- exact/approximate dynamic strength;
- every reduced normalized SAA-3 transfer channel in matrix position.

Exact ordered signature equality therefore means equality of the reduced normalized rational transfer matrix with the same ordered interface.

For approximate channels the hash is still deterministic, but equality is not promoted to a proof of exact dynamic equivalence.

## 3. Port-permutation identity

Different implementations may use different port ordering while implementing the same matrix transformation.

SAA-4 can therefore search over independent output and input permutations:

\[
G'(q)=P_y G(q) P_u.
\]

For a bounded search, SAA-4 chooses the lexicographically minimal canonical matrix payload and records:

- `permutation_invariant_signature`;
- `canonical_output_permutation`;
- `canonical_input_permutation`;
- `permutation_strength = EXACT_PORT_PERMUTATION`.

The maximum default search is 4096 row/column permutation combinations.

If

\[
p!m! > B_{perm},
\]

SAA-4 does not claim permutation-invariant equivalence. It returns:

`ORDERED_ONLY_PERMUTATION_BUDGET_EXCEEDED`

and leaves `permutation_invariant_signature` unset.

This is deliberately conservative. A search budget failure must never be interpreted as proof of non-equivalence or as permission to use a heuristic hash as exact identity.

## 4. Exact permutation decoupling

A square transfer matrix is permutation-decoupled when a one-to-one input/output pairing exists such that every off-pairing transfer channel is identically zero.

For a permutation `pi`, SAA-4 checks:

\[
G_{ij}(q)=0 \quad \forall j\neq \pi(i).
\]

When this is true it records:

- `permutation_decoupled = true`;
- `exact_diagonal_input_permutation = pi`.

This is purely a port reassignment. It does not alter the underlying dynamic equations.

## 5. Steady-state gain matrix

SAA-4 extracts a normalized steady-state gain matrix `K`.

For continuous dynamics:

\[
K = G(0)
\]

in the dimensionless `SIGMA` domain.

For discrete dynamics:

\[
K = G(1).
\]

If a channel has a pole at the steady-state evaluation point, that gain is marked unavailable rather than approximated.

Because SAA-2 has already normalized every channel, gain magnitudes are comparable across input/output dimensions without arbitrary physical units dominating the result.

## 6. Relative Gain Array

For a square nonsingular steady-state matrix, SAA-4 computes the Relative Gain Array:

\[
\Lambda = K \circ (K^{-1})^T,
\]

where `circ` denotes elementwise multiplication.

The RGA is useful because it exposes how input/output pairings change when other control loops are closed. It is also invariant to independent diagonal input and output scaling, making it well suited to normalized algorithm comparison.

SAA-4 uses exact `Fraction` arithmetic whenever the underlying channels are exact.

If `K` is singular or contains an unavailable steady-state entry, no RGA is asserted.

## 7. Preferred RGA pairing

For square systems with a valid RGA, SAA-4 searches all input permutations and selects the pairing maximizing

\[
\sum_i |\Lambda_{i,\pi(i)}|.
\]

It records:

- `preferred_rga_pairing`;
- `rga_off_pairing_mass`.

The off-pairing mass is

\[
C_{RGA}=
\frac{
\sum_{j\neq\pi(i)}|\Lambda_{ij}|
}{
\sum_{i,j}|\Lambda_{ij}|
}.
\]

A perfectly paired diagonal RGA has

\[
C_{RGA}=0.
\]

This is a coupling diagnostic, not an automatic proof that a chosen controller or reasoning algorithm is globally superior.

## 8. Exact static decoupling

If the full MIMO dynamics are exact and the normalized steady-state gain matrix is invertible, SAA-4 constructs the static decoupler

\[
D=K^{-1}.
\]

It then forms

\[
G_d(q)=G(q)D.
\]

By construction:

- continuous: `G_d(0) = I`;
- discrete: `G_d(1) = I`.

The transformed channels are represented as exact reduced rational functions.

This transform exists in normalized deviation coordinates. It is not a physical actuator command map and is not automatically valid over the full original 0–1 box.

## 9. Residual dynamic coupling

Static decoupling removes steady-state cross coupling but generally does not diagonalize the full frequency-dependent transfer matrix.

SAA-4 therefore samples the decoupled matrix away from steady state and reports the off-diagonal energy ratio

\[
C(q)=
\frac{
\sum_{i\neq j}|G_{d,ij}(q)|^2
}{
\sum_{i,j}|G_{d,ij}(q)|^2
}.
\]

For continuous systems the v1 diagnostic points are dimensionless frequencies:

- `0.1`;
- `1.0`;
- `10.0`.

For discrete systems they are digital angles:

- `pi/4`;
- `pi/2`;
- `3*pi/4`.

These floating-point samples are diagnostics only. They are not included as exact canonical-equivalence evidence.

## 10. Why SAA-4 does not use approximate pole-zero or matrix cancellation

SAA-3 already distinguishes exact rational data from approximate floating-point evidence. SAA-4 preserves this boundary.

An apparently small off-diagonal transfer, near-singular steady-state matrix, or nearly cancelling pole/zero pair must not be converted into an exact decoupling claim merely because a numerical tolerance makes it convenient.

Therefore:

- exact static decoupling is produced only for exact MIMO channel dynamics;
- approximate systems may still receive RGA diagnostics derived from their recorded coefficients;
- approximate systems do not receive an exact static-decoupler record.

## 11. Signature hierarchy

SAA-4 exposes two MIMO identities.

### Ordered

`mimo_algorithm_signature(..., ignore_port_order=False)` binds:

\[
SAA1 + SAA2 + G_{ordered}(q).
\]

Its scope is:

`STRUCTURE_PLUS_NORMALIZED_ORDERED_MIMO_DYNAMICS`.

### Up to port permutation

When the bounded permutation search succeeds:

`mimo_algorithm_signature(..., ignore_port_order=True)` binds:

\[
SAA1 + SAA2 + \operatorname{CanonPerm}(G(q)).
\]

Its scope is:

`STRUCTURE_PLUS_NORMALIZED_MIMO_DYNAMICS_UP_TO_PORT_PERMUTATION`.

If the bounded permutation search was not completed, requesting this signature fails closed.

## 12. What SAA-4 establishes

For exact coefficients and exact SAA-2 normalization, equality of ordered SAA-4 transfer signatures establishes equality of the normalized reduced rational MIMO input-output matrix in the recorded domain.

Equality of permutation-invariant signatures additionally establishes equality up to independent input/output port permutations within the exact bounded canonical search.

SAA-4 also provides exact steady-state coupling and decoupling information where its mathematical prerequisites hold.

## 13. What SAA-4 does not establish

SAA-4 v1 does not establish:

- Smith-McMillan equivalence under arbitrary unimodular polynomial transforms;
- full dynamic decoupling;
- singular-vector or frequency-dependent unitary decoupling;
- canonical MIMO state-space minimal realization;
- equivalence under arbitrary linear mixtures of ports;
- nonlinear coupling equivalence;
- Taylor-jet equivalence;
- delay equivalence;
- hybrid mode equivalence;
- physical feasibility of the static decoupler over an actuator operating envelope;
- automatic Algorithm Store persistence or selection authority.

Those remain later SAA milestones.

## 14. Fail-closed invariants

SAA-4 v1 enforces:

1. non-empty rectangular transfer matrices;
2. maximum 6x6 dimensions;
3. one common continuous/discrete domain;
4. normalization input/output counts equal matrix dimensions;
5. continuous scalar SAA-2 input/output coordinates;
6. a declared SAA-2 characteristic time;
7. one common normalized discrete sample interval;
8. no permutation-invariant claim when the canonical permutation budget is exceeded;
9. no RGA when the steady-state matrix is singular or undefined;
10. no exact static decoupler for approximate channel dynamics.

## 15. Role in the Searchable Algebra

The algebra now has the sequence:

\[
A
\xrightarrow{SAA1}
C_{structure}
\xrightarrow{SAA2}
C_{coordinates}
\xrightarrow{SAA3}
C_{SISO\ dynamics}
\xrightarrow{SAA4}
C_{MIMO\ coupling}.
\]

This lets the Algorithm Store distinguish algorithms that merely have similar code from algorithms that have the same normalized linear input-output dynamics, while also exposing whether their inputs and outputs are intrinsically coupled, trivially permutable, or statically decouplable.
