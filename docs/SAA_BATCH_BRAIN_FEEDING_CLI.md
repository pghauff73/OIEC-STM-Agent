# SAA Batch Brain Feeding CLI

`oiec-stm-agent brain` is the batch-ingestion front door for the SAA mathematical brain.
It is intentionally not a canonical-algorithm import command.

The governing rule is:

```text
raw feed -> evidence / semantic / failure routing -> candidate staging -> normal SAA qualification
```

Batch feeding can register grounded evidence, admit already-resolved evidence-grounded semantic concepts, and register grounded failures. Mathematical algorithms, reasoning procedures, experiments, datasets, claims, invariants, and source documents enter the **staging ring** and still require their normal qualification path.

```text
canonical_algorithm_admissions = 0
```

for every brain-feed batch.

## Commands

```bash
oiec-stm-agent brain feed SOURCE --repo .
oiec-stm-agent brain validate SOURCE
oiec-stm-agent brain status --repo .
oiec-stm-agent brain quarantine --repo .
oiec-stm-agent brain example
```

`ourd-agent brain ...` is the same interface because `ourd-agent` and `oiec-stm-agent` share the installed dispatcher.

## First batch

Generate a complete example:

```bash
oiec-stm-agent brain example --output brain-feed.json
```

Validate it without changing SAA state:

```bash
oiec-stm-agent brain validate brain-feed.json
```

Feed it:

```bash
oiec-stm-agent brain feed brain-feed.json --repo . --verbose
```

Typical output is conceptually:

```text
SAA brain-feed batch: thermal-lab-001
  status: BRAIN_FEED_BATCH_ACCEPTED
  items: 4
  admitted/routed: 3
  staged for qualification: 1
  quarantined: 0
  duplicates: 0
  canonical algorithm admissions: 0
```

The example contains a calibrated measurement, a semantic meaning grounded by that measurement, an algorithm candidate, and a failure observation. The first, second, and fourth can route to qualified supporting stores. The algorithm remains staged.

## Manifest format

```json
{
  "schema_version": 1,
  "batch_id": "thermal-lab-001",
  "source_label": "Thermal laboratory run",
  "items": [
    {
      "id": "temperature-run-1",
      "kind": "MEASUREMENT",
      "payload": {}
    },
    {
      "id": "temperature-meaning",
      "kind": "SEMANTIC_CONCEPT",
      "evidence_from": ["temperature-run-1"],
      "payload": {}
    },
    {
      "id": "controller-candidate",
      "kind": "ALGORITHM_CANDIDATE",
      "depends_on": ["temperature-meaning"],
      "evidence_from": ["temperature-run-1"],
      "payload": {}
    }
  ]
}
```

`depends_on` describes general within-batch dependencies. `evidence_from` means “use any grounded `EvidenceArtifact` produced by these batch items as evidence for this item.” This removes the need to know content-addressed evidence IDs before the batch runs.

## Supported feed kinds

| Kind | Batch-feed behaviour |
| --- | --- |
| `MEASUREMENT` | Register as `EvidenceArtifact` only when grounding metadata is sufficient |
| `EVIDENCE` | Same evidence route as measurement |
| `SEMANTIC_CONCEPT` | Admit only if explicitly `SEMANTICALLY_RESOLVED` and grounded evidence is available |
| `FAILURE` | Register into SAA-12.1 Failure Algebra only with grounded evidence |
| `ALGORITHM_CANDIDATE` | Stage for normal SAA mathematical/semantic/evidence qualification |
| `REASONING_CANDIDATE` | Stage for SAA-8 reasoning qualification |
| `EXPERIMENT_CANDIDATE` | Stage for controlled experiment qualification |
| `DATASET` | Stage as a source artifact/reference |
| `CLAIM` | Stage for evidence and falsifier development |
| `INVARIANT_CANDIDATE` | Stage for invariant qualification |
| `SOURCE_DOCUMENT` | Stage as provenance/source material |

## Grounded measurement example

```json
{
  "id": "coolant-temp-run-01",
  "kind": "MEASUREMENT",
  "payload": {
    "subject_id": "thermal-control",
    "producer": "deterministic-calibrated-sensor",
    "method": "calibrated-temperature-measurement",
    "target": "coolant temperature",
    "oracle": "calibrated thermocouple",
    "independence_group": "thermal-run-01",
    "environment": {
      "engine_speed_rpm": 2500
    },
    "content": {
      "value": "83.2",
      "unit": "degC",
      "uncertainty": "+/-0.3 degC"
    },
    "success": true,
    "simulated": false
  }
}
```

The producer must identify deterministic or human grounding, the method cannot be `reported`, simulated measurements do not become real-execution evidence, and the evidence must be successful.

Under-grounded measurements are not discarded. They receive a staging status such as:

```text
STAGED_EVIDENCE_METADATA_REQUIRED
```

## Semantic concept example

```json
{
  "id": "coolant-temperature-meaning",
  "kind": "SEMANTIC_CONCEPT",
  "evidence_from": ["coolant-temp-run-01"],
  "payload": {
    "name": "coolant temperature",
    "meaning": "thermodynamic temperature of engine coolant at the declared sensor location",
    "domain": "automotive thermal control",
    "quantity_kind": "temperature",
    "physical_dimension": [0, 0, 0, 0, 1, 0, 0],
    "canonical_unit": "degC",
    "semantic_status": "SEMANTICALLY_RESOLVED"
  }
}
```

The seven physical-dimension entries are, in order:

```text
length, mass, time, electric current,
thermodynamic temperature, amount of substance, luminous intensity
```

A concept marked unresolved stays staged. Merely giving a concept a plausible English name cannot make it canonical.

## Algorithm candidate example

```json
{
  "id": "thermal-threshold-candidate",
  "kind": "ALGORITHM_CANDIDATE",
  "depends_on": ["coolant-temperature-meaning"],
  "evidence_from": ["coolant-temp-run-01"],
  "payload": {
    "name": "thermal threshold detector",
    "inputs": ["coolant temperature"],
    "outputs": ["overheat flag"],
    "procedure": "compare representative coolant temperature with a qualified threshold",
    "meanings": {
      "input": "coolant temperature",
      "output": "overheat state"
    }
  }
}
```

Expected disposition:

```text
STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED
```

The raw candidate is retained immutably, but no SAA canonical algorithm is created. Subsequent tooling must perform representation analysis, semantic resolution, evidence qualification, uniqueness lookup, benchmarking, and the applicable canonical admission gates.

## Failure example

```json
{
  "id": "sensor-drift-failure",
  "kind": "FAILURE",
  "evidence_from": ["coolant-temp-run-01"],
  "payload": {
    "source_kind": "thermal experiment",
    "component": "coolant temperature sensor",
    "failure_class": "EVIDENCE_FAILURE",
    "mechanism": "calibration drift contradicted the expected measurement tolerance",
    "semantic_roles": ["temperature observation"],
    "violated_invariants": ["measurement remains within calibration tolerance"]
  }
}
```

A grounded failure is routed to the SAA-12.1 failure algebra. Refeeding an equivalent known failure contributes provenance rather than inventing a new failure family.

## Feed a directory

A directory can contain manifests, single JSON feed items, or JSON arrays of feed items.

```bash
oiec-stm-agent brain feed ./brain-feed --repo .
```

Recursive traversal is explicit:

```bash
oiec-stm-agent brain feed ./brain-feed --repo . --recursive
```

The hard default batch bound is 4096 items. A lower operational bound can be imposed with:

```bash
oiec-stm-agent brain feed ./brain-feed --repo . --max-items 500
```

## Strict mode

Normal feed mode preserves partial progress. Valid items can route while malformed candidate objects are quarantined.

```bash
oiec-stm-agent brain feed brain-feed.json --repo .
```

Strict mode still records the batch and its quarantine evidence, but returns a non-zero exit code when any item is quarantined:

```bash
oiec-stm-agent brain feed brain-feed.json --repo . --strict
```

This is useful in CI pipelines.

## Validation only

```bash
oiec-stm-agent brain validate brain-feed.json
```

Validation checks the manifest shape, hard item bound, duplicate human IDs, missing batch references, and dependency cycles. It does not create `.ourd-agent/egcf/brain-feed` state.

## Inspect the brain-feed ledger

```bash
oiec-stm-agent brain status --repo .
```

Include item dispositions:

```bash
oiec-stm-agent brain status --repo . --items
```

Filter an exact disposition status:

```bash
oiec-stm-agent brain status --repo . \
  --status STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED \
  --items
```

Machine-readable output is available with `--json`.

## Inspect quarantine

```bash
oiec-stm-agent brain quarantine --repo .
```

Quarantine means the object could not safely enter a normal route. Examples include malformed algorithm representations, invalid physical-dimension vectors, missing batch references, and cyclic dependencies.

Quarantine is deliberately different from staging:

```text
STAGED     = structurally acceptable, but more qualification is required
QUARANTINE = the current feed object cannot safely proceed in its present form
```

## Deduplication

Every raw item has both an item signature and a content signature.

- Refeeding the exact same item produces `DUPLICATE_EXACT_ITEM`.
- Equivalent content under another human item ID produces `DUPLICATE_CONTENT`.
- Existing target references are reused in the batch receipt.

This prevents repeated batch imports from manufacturing extra mathematical knowledge.

## Persistent layout

The raw/staging ledger lives under:

```text
.ourd-agent/egcf/brain-feed/
  items/sha256/
  dispositions/sha256/
  batches/sha256/
```

SQLite is a rebuildable projection over those immutable objects.

## Brain-feeding model

```text
JSON / datasets / measurements / papers / algorithms
                      |
                      v
                BATCH FEEDER
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       EVIDENCE    SEMANTICS    FAILURES
          |           |           |
          +-----------+-----------+
                      |
                      v
                CANDIDATE RING
                      |
                      v
             NORMAL SAA QUALIFICATION
                      |
                      v
              CANONICAL ALGORITHM STORE
```

The last arrow is intentionally outside the batch feeder.
