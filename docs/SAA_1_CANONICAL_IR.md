# SAA-1 Canonical Structural IR

SAA-1 is the first implementation slice of the Searchable Algebra of Algorithms. It establishes a deterministic structural representation before numerical normalization, dynamic identification, Taylor expansion, coupling analysis, equivalence search, fit scoring, or Algorithm Store indexing are attempted.

## Scope

SAA-1 answers one deliberately narrow question:

> Do two declared algorithms have the same structural algorithm after source names, display metadata, and other non-semantic representation choices are removed?

It does **not** claim that structurally different algorithms are dynamically inequivalent, nor that structurally identical declarations are globally mathematically equivalent outside the semantics represented in this IR.

## Canonical vocabulary

The IR maps operators onto a fixed primitive vocabulary. Initial primitives include arithmetic, predicates, invocation/control operations, and reasoning operations such as `OBSERVE`, `GENERATE`, `PREDICT`, `VERIFY`, `FALSIFY`, `PRUNE`, `BACKTRACK`, `SYNTHESIZE`, `BRANCH`, `ITERATE`, and `TERMINATE`.

Aliases such as `+` and `SUM` normalize to `ADD`. Unknown primitives fail closed rather than entering identity under arbitrary names.

## Interface identity

Inputs, parameters, states, and outputs use explicit positional roles:

```text
input 0  -> u0
input 1  -> u1
parameter 0 -> p0
state 0 -> x0
output 0 -> y0
```

Human names are metadata. Renaming `temperature` to `x` therefore does not change structural identity. Port positions, data types, shapes, state update bindings, and output bindings remain identity-bearing.

## Node identity

Source node IDs are not canonical identity. A source graph may use `sum_inputs`, `node_947`, or another local name and still collapse to the same canonical structure.

Node identity contains:

- canonical primitive;
- operand structure;
- identity-bearing attributes;
- result arity;
- control dependencies;
- external input/output/state/entry/termination relationships.

Display-only attributes such as names, descriptions, comments, and source locations are excluded from identity.

## Commutativity

Operands of declared commutative primitives are sorted canonically. Thus:

```text
ADD(u0, u1)
```

and

```text
ADD(u1, u0)
```

have the same structural identity.

Ordered primitives remain ordered. Therefore:

```text
SUBTRACT(u0, u1)
```

and

```text
SUBTRACT(u1, u0)
```

remain distinct.

Associative flattening is intentionally not part of SAA-1. It can be added later only with qualification evidence showing that the transformation is semantics-preserving for the relevant primitive/domain.

## Branch and termination semantics

Control edges are typed. `true`, `false`, `loop`, `backtrack`, `terminate`, `exception`, and ordinary `next` relationships remain part of structural identity.

Termination nodes must explicitly use the `TERMINATE` primitive. Identity-bearing termination attributes remain in the canonical payload. Consequently a convergence stop and a budget-exhaustion stop cannot silently collapse into the same reasoning algorithm.

## Exact canonicalization and bounded symmetry

SAA-1 first performs deterministic graph-color refinement using operator structure, data dependencies, control dependencies, and external bindings.

When remaining symmetry is small, it enumerates permutations only inside indistinguishable refinement classes and chooses the lexicographically minimal graph serialization. Such a result is labelled:

```text
EXACT_STRUCTURAL
```

The permutation search is bounded. The default maximum is 10,000 permutations.

If exact labeling would exceed this budget, SAA-1 does **not** claim exact structural equivalence. It emits an invariant refinement representation labelled:

```text
REFINED_FINGERPRINT
```

with a warning describing why the exact claim was downgraded.

This is intentionally conservative because a false-equivalence result is more dangerous to the Algorithm Store than a false-novel result.

## Declarative input

`structure_from_mapping()` and `canonicalize_mapping()` provide a strict declarative interface. Operands are represented without source variable names:

```python
{
    "name": "sum",
    "inputs": [
        {"position": 0, "name": "temperature"},
        {"position": 1, "name": "pressure"},
    ],
    "outputs": [
        {"position": 0, "source": {"node": "combine"}},
    ],
    "nodes": [
        {
            "id": "combine",
            "primitive": "ADD",
            "operands": [{"input": 0}, {"input": 1}],
        }
    ],
}
```

Canonicalization removes the display name and source node ID from identity while preserving the ordered interface and operation semantics.

## Output

`CanonicalAlgorithmIR` contains:

```text
schema_version
canonicalizer_version
structural_hash
canonical_payload
canonicalization_strength
exact_permutations_considered
source_node_map
warnings
```

`source_node_map` is diagnostic provenance and is not included in `structural_hash`.

## SAA-1 invariants

The qualification tests enforce at least these properties:

```text
variable renaming preserves identity
node renaming preserves identity
commutative operand reversal preserves identity
noncommutative operand reversal changes identity
branch direction changes identity
termination semantics change identity
state names do not change identity
large unresolved symmetry downgrades the equivalence strength
unknown fields and unknown primitives fail closed
```

## Deferred work

SAA-1 intentionally does not implement:

- 0–1 variable normalization;
- dimension/time normalization;
- state-space extraction;
- minimal realizations;
- s-domain or z-domain transfer forms;
- MIMO coupling/decoupling;
- Taylor jets;
- hybrid dynamic equivalence beyond structural control topology;
- Algorithm Store canonical records or SQLite indexes;
- fit scoring, deltas, adaptation, lineage, or qualification integration.

Those belong to later SAA milestones. Keeping them outside SAA-1 makes the structural equivalence claim independently testable and falsifiable.
