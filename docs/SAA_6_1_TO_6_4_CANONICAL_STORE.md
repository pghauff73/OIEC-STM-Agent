# SAA-6.1 through SAA-6.4: Canonical Algorithm Store

## Purpose

SAA-6 produces a canonical representative algorithm form whose mathematics are exact in the supported scope, whose representative inputs are minimal and decoupled, and whose meanings have passed the semantic-resolution gate. SAA-6.1 through SAA-6.4 make those forms persistent, unique, searchable and relational.

The governing invariant is:

```text
Canonical knowledge = unique representative behavior + resolved meaning + grounded qualification
```

A source equation, implementation, variable naming scheme or coordinate system is not canonical knowledge merely because it was observed. Source representations are retained as immutable provenance. Canonical nodes are admitted only after SAA-6 qualification.

## Canonical identity

The canonical node key is the SAA-6 `representative_behavior_signature`:

```text
canonical-algorithm:sha256:<representative_behavior_signature>
```

The representative behavior signature already binds:

- exact re-normalized representative dynamics;
- representative input order;
- resolved input meanings;
- expected and excluded output footprints.

It deliberately does not bind source-coordinate provenance. Therefore two differently written source algorithms that reduce to the same qualified representative mathematics and semantics resolve to one canonical node.

The stronger SAA-6 `canonical_algorithm_signature`, which conservatively includes the source SAA-1 structural hash, is retained in source provenance and indexed as an anchor. It is not used to create duplicate canonical knowledge.

## SAA-6.1: persistent canonical forms

`CanonicalAlgorithmStore` writes three immutable content-addressed object families below:

```text
.ourd-agent/egcf/canonical-algorithms/
    objects/sha256/
    sources/sha256/
    relations/sha256/
```

### Canonical algorithm objects

Canonical objects contain only the representative knowledge needed for reuse:

- representative version;
- continuous/discrete domain;
- normalized sample interval;
- representative input count;
- canonical input meanings;
- input/output semantic footprints;
- exact normalized rational channels;
- mathematical representative signature;
- semantic representative signature;
- representative behavior signature.

Source-specific transforms, source variable positions, source structural hashes and evidence histories are intentionally excluded from the canonical node payload.

### Source provenance objects

Every admitted source representation receives an immutable `algorithm-source` record containing:

- canonical target ID;
- source SAA-1 structural hash;
- source MIMO signature;
- source normalization signature;
- representative candidate signature;
- representative-search audit hash;
- SAA-6 form audit hash;
- semantic qualification proof signature;
- complete source SAA-6 form.

An equivalent second source therefore expands provenance, not canonical knowledge.

## Canonical semantic admission

The store does not trust `canonical_admission_eligible` as an unchecked boolean. Admission re-verifies the SAA-6 signatures and the semantic proof bundle.

For every representative input the store requires:

1. one representative semantic issue;
2. the exact semantic candidate referenced by SAA-6;
3. a `SEMANTICALLY_RESOLVED` resolution;
4. complete semantic output-footprint fit;
5. independent review;
6. every declared falsifier to have `SURVIVED`;
7. non-empty grounded evidence;
8. every evidence ID to resolve to a successful, non-simulated `EvidenceArtifact`;
9. evidence producer to be deterministic or human grounded;
10. evidence method not to be reported-only;
11. evidence category `semantic-grounding`;
12. evidence to reference the actual semantic issue or candidate.

This makes the canonical store a second epistemic boundary. A fabricated or stale SAA-6 object cannot obtain canonical admission merely by setting status fields.

The zero-effective-input quotient is the one vacuous semantic case because it has no representative input meanings to resolve.

## SAA-6.2: canonical indexes

The existing EGCF projection database receives dedicated rebuildable tables:

```text
canonical_algorithms
canonical_algorithm_sources
canonical_algorithm_relations
canonical_store_metadata
```

Canonical algorithms are indexed by:

- representative behavior signature, unique;
- mathematical representative signature;
- semantic representative signature;
- conservative source-bound algorithm signature;
- domain;
- input/output dimensions;
- store generation.

Source provenance is indexed by:

- canonical ID;
- source-bound algorithm signature;
- source structural hash.

Relations are indexed by:

- relation type;
- source reference;
- target reference.

The projection remains disposable. Immutable canonical/source/relation objects are authoritative. If the SQLite projection is removed or rebuilt, `CanonicalAlgorithmStore` reconstructs its indexes from those objects.

## Store generations

A new unique canonical node increments the canonical store generation:

```text
G0 -> G1 -> G2 -> ...
```

An equivalent source representation does not increment the generation because no new canonical knowledge was created.

This gives a simple auditable measure of qualified knowledge growth rather than file or conversation growth.

## SAA-6.3: exact uniqueness and equivalence lookup

Before admission the store searches existing canonical nodes.

Possible lookup outcomes are:

```text
UNIQUE_CANONICAL_CANDIDATE
REPRESENTATIVE_EQUIVALENT_ALREADY_STORED
MATHEMATICAL_MATCH_SEMANTIC_DIFFERENCE
SEMANTIC_MATCH_MATHEMATICAL_DIFFERENCE
MULTIPLE_CANONICAL_NEIGHBOR_MATCHES
```

### Exact representative equivalence

If `representative_behavior_signature` already exists:

```text
new source -> existing canonical node
```

No new canonical algorithm is written. The new source is retained as provenance and linked with `EQUIVALENT_TO`.

### Same mathematics, different meaning

Equal mathematical signatures with unequal semantic signatures are not equivalent algorithms.

They remain separate canonical nodes and are linked as `NEAR_VARIANT_OF` with basis:

```text
EXACT_MATHEMATICAL_SIGNATURE_MATCH_SEMANTIC_DIFFERENCE
```

This enforces:

```text
same equation + different meaning != same canonical algorithm
```

### Same meaning, different mathematics

Equal semantic signatures with different mathematical signatures also remain separate nodes. They are linked as near variants with basis:

```text
EXACT_SEMANTIC_SIGNATURE_MATCH_MATHEMATICAL_DIFFERENCE
```

This gives later fit/evolution systems a useful neighborhood without asserting false equivalence.

## SAA-6.4: algorithm relationship graph

The canonical store persists immutable relation objects. Supported relation vocabulary is:

```text
EQUIVALENT_TO
NEAR_VARIANT_OF
GENERALIZES
SPECIALIZES
DERIVED_FROM
COMPOSED_FROM
APPROXIMATES
BOUNDS
DECOUPLES
REQUIRES
LOWER_COST_THAN
STRONGER_EVIDENCE_THAN
```

### Derived relations

The following are generated by SAA itself:

- `DERIVED_FROM` from a canonical node to its first qualified source representation;
- `EQUIVALENT_TO` from an additional source representation to the already-known canonical node;
- `NEAR_VARIANT_OF` from exact mathematical or semantic index matches that are not fully equivalent.

Manual assertion of these relations is forbidden.

### Evidence-backed relations

Relations such as `GENERALIZES`, `SPECIALIZES` or `REQUIRES` may be registered between canonical nodes only with grounded `EvidenceArtifact` IDs and an explicit basis.

The store therefore distinguishes:

```text
exact relation derived from canonical identity
```

from:

```text
relationship claim supported by evidence
```

### Graph queries

The API provides:

- `relations(ref)` for all incident edges;
- `relations(ref, relation_type=...)` for typed edges;
- `neighbors(canonical_id)` for a local algorithm neighborhood.

This is the first persistent reasoning topology for SAA canonical algorithms.

## Public API

```python
from ourd.egcf import CanonicalAlgorithmStore, EGCFStore

with EGCFStore(workspace) as egcf:
    algorithms = CanonicalAlgorithmStore(egcf)

    lookup = algorithms.lookup(form)

    admission = algorithms.admit(
        form,
        semantic_issues=issues,
        semantic_candidates=candidates,
        semantic_resolutions=resolutions,
    )

    algorithms.list()
    algorithms.sources(admission.canonical_id)
    algorithms.neighbors(admission.canonical_id)
```

Evidence-backed graph relations can be added with:

```python
algorithms.add_relation(
    general_algorithm_id,
    specialized_algorithm_id,
    "GENERALIZES",
    basis="qualified domain inclusion",
    evidence_ids=(evidence_id,),
)
```

## Current claim scope

SAA-6.1 through SAA-6.4 establish persistence, exact representative uniqueness lookup and an evidence-bearing relation graph for SAA-6 v1 forms.

They do not yet establish:

- nonlinear or Taylor-jet canonical equivalence;
- dynamic/rational input-transform equivalence beyond SAA-6 v1;
- semantic ontology or synonym equivalence;
- automatic proof of `GENERALIZES` or `SPECIALIZES`;
- algorithm problem-fit ranking;
- adaptation/evolution search;
- automatic selection of canonical SAA algorithms by EGCF execution.

Those remain later milestones.

## Governing principle

The canonical store grows only when qualified knowledge grows:

```text
encountered equation
    -> representative form
    -> resolved meaning
    -> grounded qualification
    -> uniqueness lookup
    -> reuse existing OR admit new canonical node
```

The intended result is a reasoning substrate that becomes cleaner as it grows rather than accumulating duplicate equations, ambiguous meanings or unsupported relationships.
