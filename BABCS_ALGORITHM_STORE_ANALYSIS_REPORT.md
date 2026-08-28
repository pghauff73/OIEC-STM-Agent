# BAB-CS Algorithm Store and Analysis Report

## Executive conclusion

The current BAB-CS bounded integrator has been captured without modifying its
worktree and stored as an exact content-addressed tar artifact in the OURD EGCF
store. A separate `PROPOSED` `reference` algorithm definition describes the
implementation for search, comparison, explanation, and experiment analysis.
It is deliberately not a direct executor and is not qualified for release or
production use by this import.

## Store receipt

- Algorithm ID: `reference.babcs.bounded-integrator@1`
- Algorithm definition object: `algorithm-definition:sha256:a601e0df9528a44cb205ff9cae3025ea6a316a03afe58ac5c9bd0506d2ff3cf7`
- Source bundle artifact: `artifact:sha256:d2b5e6be142370f20c0dd350ea24a5c2698cde6819e662ae81935d9a741be440`
- Analysis evidence object: `egcf-evidence:sha256:e0ba3bf9c25e4e5653058e56c057593d45de5431ed29552b649bcc7f456a480d`
- Bundle SHA-256: `b85f1faa728fc39292f45dacabeb0a86d23e644f70004df362acad0400748e8a`
- Manifest SHA-256: `38917e71db6b3944e0994d8fcf51f25c298c4e0fc8588441f5eb4298d41ab936`
- Bundle size: `409600` bytes
- Captured files: `18`

## Source provenance

- Repository: `../BAB-CS`
- Upstream package version: `1.1.0`
- Git HEAD: `0b8ef0b4e9caaea46859dd01c1f2f5e599db2ee2`
- Dirty worktree captured: `true`
- Dirty paths in BAB-CS worktree: `374`
- Dirty captured-source paths: `3`
- Dirty paths outside the source bundle: `371`
- License retained from source: `MPL-2.0`

The bundle digest, not Git HEAD alone, identifies the imported implementation
because the BAB-CS worktree contains current uncommitted changes.

### Dirty captured-source paths present during capture

- `README.md`
- `src/babcs/bounded.py`
- `src/babcs/io.py`

## Algorithm structure

- Python modules: `14`
- Public API symbols: `30`
- Classes: `62`
- Functions and methods: `219`
- Dataclasses: `8`
- Candidate methods: `ab2`, `backward_euler`, `bdf2`, `explicit_euler`, `heun`, `rk23`, `trapezoidal`

BAB-CS supervises candidate transient integration rather than trusting one
explicit step blindly. Its active path projects the candidate into the circuit
constraints, compares it with implicit authority, applies bounded correction,
checks residual/error/energy/amplification evidence, and periodically rebuilds
authority through independent replay.

### Control layers

- candidate integrator prediction
- algebraic projection
- implicit reference authority
- contractive correction
- residual, error, energy, and amplification gates
- periodic independent replay anchor
- event-safe history reset
- stiffness and failure fallback to implicit authority

## OIEC-STMv1.1 analysis

- **Boundary Determination:** Circuit topology, rollout mode, event boundaries, source snapshot, and configured safety caps define where a step is admissible.
- **Dimension Limiting:** Candidate method, step size, reference interval, anchor refinement, linear backend, and bounded retry count constrain active numerical complexity.
- **IURM:** Candidate/reference and dual-resolution comparisons isolate controlled numerical variations.
- **EON:** A simulation configuration and exact circuit case determine one reproducible integration action.
- **CFEL:** Step rejection, residual failures, anchor discrepancy, stiffness, and uncertainty metrics revise the next step or transfer authority.

The strongest architectural match is the separation between candidate freedom
and authoritative acceptance. BAB-CS may compute several candidate dimensions,
but configured bounds, implicit references, event surfaces, and fail-closed
fallback determine which state becomes authoritative. This is analogous to
OIEC's distinction between semantic possibility, bounded experimentation, and
governed action.

## Strengths

- separates provisional candidate state from independently refreshed implicit authority
- uses categorical fail-closed gates for residual, contraction, stiffness, event, and minimum-step failures
- records per-step evidence and supports deterministic dense execution by default
- keeps rollout modes explicit and provides no unanchored candidate-only production mode

## Focused validation

- Command: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_babcs tests.test_bound_model tests.test_integrator_boundaries`
- Result: `PASS`
- Tests observed: `36`
- Duration: `0.492653` seconds

This focused result covers the main bounded integrator, bound model, and
integrator-boundary tests. It does not replace the BAB-CS repository's full
test discovery, long-horizon tier, runtime benchmark workflow, external
ngspice comparison, packaging checks, or human release decision.

## Limitations and unresolved evidence

- the repository states that BAB-CS is not a production sparse SPICE replacement
- trajectory accuracy is not claimed indefinitely for unstable, chaotic, discontinuous, or neutrally oscillating circuits
- the captured worktree is dirty, so the content bundle rather than Git HEAD is the authoritative implementation snapshot
- focused unit tests do not establish complete release qualification, external equivalence, or certification

## Governance conclusion

The correct current state is **stored and analyzable, but not executable by
reference and not qualified by this repository**. Any future execution adapter
must be a separate implementation with explicit capabilities, exact source and
environment binding, independent qualification evidence, bounded resource
budgets, and EON authorization. The imported MPL-2.0 source bundle also remains
legally distinct from this repository's MIT-licensed original code.
