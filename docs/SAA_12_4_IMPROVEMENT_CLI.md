# SAA-12.4 Improvement Scheduling CLI

SAA-12.4 gives OIEC-STM-Agent a deterministic way to decide **which evidence-grounded investigation is worth doing next**.

The CLI entry point is:

```bash
oiec-stm-agent improvement <command>
```

The same command family is also available through the legacy `ourd-agent` executable because both names use the same CLI entry point.

> Improvement scheduling grants **no mutation authority**. It ranks and records investigations only. Any actual change still requires the normal OIEC/EGCF authority, evidence, approval, execution and qualification gates.

## Mental model

```text
Grounded problem signal
        ↓
Improvement opportunity
        ↓
Evidence value + impact + uncertainty reduction
        ↓
Cost + risk
        ↓
Deterministic priority
        ↓
Bounded scheduling policy
        ↓
Selected investigation(s)
```

A schedule answers:

> Given the opportunities that are currently known, which investigations fit inside the explicit cost, risk, count and priority limits?

It does **not** answer:

> Which files should the agent modify?

## Basis points

SAA-12.4 uses integer basis points for deterministic bounded scores.

```text
0      = 0%
1000   = 10%
5000   = 50%
9000   = 90%
10000  = 100%
```

Cost uses the same integer scale per opportunity, but should be read as a relative scheduling cost unit rather than monetary currency.

## 1. Register an opportunity

An opportunity must have grounded `EvidenceArtifact` references already registered in the EGCF store.

```bash
oiec-stm-agent improvement add \
  --repo . \
  --id parser-precedence \
  --kind FAILURE_PATTERN \
  --source-signature aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --objective "Investigate repeated parser precedence failure" \
  --evidence-value-bp 9000 \
  --impact-bp 8500 \
  --uncertainty-reduction-bp 8000 \
  --cost-bp 2500 \
  --risk-bp 1500 \
  --evidence 'evidence-artifact:sha256:<digest>'
```

Supported opportunity kinds are:

```text
FAILURE_PATTERN
BENCHMARK_GAP
INTEGRITY_SIGNAL
RETRIEVAL_GAP
EXPERIMENT_TRADEOFF
SEMANTIC_CONTRADICTION
```

### Meaning of the scores

| Field | Beginner meaning |
| --- | --- |
| `--evidence-value-bp` | How valuable would new evidence from this investigation be? |
| `--impact-bp` | If resolved, how much could this improve the system? |
| `--uncertainty-reduction-bp` | How much uncertainty could the investigation remove? |
| `--cost-bp` | How expensive is the investigation relative to other work? |
| `--risk-bp` | How risky is the investigation itself? |

The scheduler calculates priority deterministically from these quantities. High value, high impact and useful uncertainty reduction increase priority; cost and risk reduce it.

### Register from JSON

For automation or reproducible experiments:

```json
{
  "opportunity_id": "parser-precedence",
  "kind": "FAILURE_PATTERN",
  "source_signature": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "objective": "Investigate repeated parser precedence failure",
  "evidence_value_bp": 9000,
  "expected_impact_bp": 8500,
  "uncertainty_reduction_bp": 8000,
  "cost_bp": 2500,
  "risk_bp": 1500,
  "evidence_ids": ["evidence-artifact:sha256:<digest>"],
  "blocked_reasons": []
}
```

Then:

```bash
oiec-stm-agent improvement add --repo . --input-file opportunity.json
```

## 2. List opportunities

```bash
oiec-stm-agent improvement list --repo .
```

Only one kind:

```bash
oiec-stm-agent improvement list --repo . --kind FAILURE_PATTERN
```

Only opportunities without hard blockers:

```bash
oiec-stm-agent improvement list --repo . --eligible-only
```

Machine-readable output:

```bash
oiec-stm-agent improvement list --repo . --json
```

## 3. Preview a schedule

```bash
oiec-stm-agent improvement schedule \
  --repo . \
  --max-selected 4 \
  --cost-budget-bp 20000 \
  --max-risk-bp 6000 \
  --min-priority-bp 1000 \
  --why
```

Without `--record`, this is a preview. It calculates exactly what would be selected but does not persist a schedule artifact.

The output explains selections and deferrals such as:

```text
SELECT #1: parser-precedence ...
DEFER: external-risk because RISK_CEILING_EXCEEDED.
DEFER: low-value because PRIORITY_BELOW_THRESHOLD.
DEFER: expensive-test because COST_BUDGET_EXHAUSTED.
```

Possible deferral reasons include:

```text
RISK_CEILING_EXCEEDED
PRIORITY_BELOW_THRESHOLD
SELECTION_COUNT_BUDGET_EXHAUSTED
COST_BUDGET_EXHAUSTED
BLOCKED:<reason>
```

## 4. Record the schedule

After inspecting the preview:

```bash
oiec-stm-agent improvement schedule \
  --repo . \
  --max-selected 4 \
  --cost-budget-bp 20000 \
  --max-risk-bp 6000 \
  --min-priority-bp 1000 \
  --record \
  --why
```

`--record` persists the immutable SAA-12.4 schedule in the knowledge-governance store.

Recording the exact same schedule again is idempotent: the CLI reuses the existing schedule reference rather than manufacturing a duplicate scheduling event.

## 5. Restrict scheduling to selected opportunity kinds

```bash
oiec-stm-agent improvement schedule \
  --repo . \
  --kind FAILURE_PATTERN \
  --kind INTEGRITY_SIGNAL \
  --max-selected 2 \
  --why
```

## 6. JSON scheduling for automation

```bash
oiec-stm-agent improvement schedule \
  --repo . \
  --max-selected 3 \
  --cost-budget-bp 12000 \
  --max-risk-bp 4000 \
  --min-priority-bp 1500 \
  --record \
  --why \
  --json
```

The JSON result contains:

- selected investigations;
- deferred opportunities and exact reasons;
- total allocated cost;
- deterministic schedule signature;
- persisted schedule reference when `--record` is used;
- `authority_effect = INVESTIGATION_PRIORITY_ONLY_NO_MUTATION_AUTHORITY`.

That last field is intentionally explicit so downstream automation cannot reinterpret a scheduling result as execution permission.

## 7. Inspect schedule history

```bash
oiec-stm-agent improvement history --repo .
```

or:

```bash
oiec-stm-agent improvement history --repo . --json
```

## Example workflow

```text
Known failure / benchmark gap / integrity signal
                ↓
       grounded EvidenceArtifact
                ↓
  oiec-stm-agent improvement add
                ↓
  oiec-stm-agent improvement list
                ↓
 oiec-stm-agent improvement schedule --why
                ↓
       human/system inspection
                ↓
 oiec-stm-agent improvement schedule --record
                ↓
      investigation priority only
                ↓
 normal OIEC authority/evidence workflow
                ↓
       controlled investigation
```

## Safety invariant

The most important rule is:

```text
scheduled investigation != authorized mutation
```

SAA-12.4 decides where evidence-gathering attention should go next. EON, EGCF, authority manifests, evidence gates and approval records still decide whether a concrete action may execute.
