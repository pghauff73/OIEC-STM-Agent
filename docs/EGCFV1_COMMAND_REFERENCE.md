# EGCFv1 Command Reference

EGCF commands are semantic engineering operations. They compile to typed,
content-addressed workflow plans; they are not aliases for arbitrary shell
commands.

## Invocation

```bash
egcf <namespace> <verb> --repo /path/to/workspace --input '{...}'
egcf run <objective words> --repo /path/to/workspace --input '{...}'
```

Read-only authority is the default. C3 operations require an external authority
manifest and an exact immutable approval record.

## Universal Modifiers

Every command uses the same parser and `CommandContext` contract:

```text
--dry-run --why --scope --evidence --approval --risk --rollback
--budget --timeout --trace --json --graph --record --replay
--strict --simulate
```

Modifiers inherit monotonically. A child operation may narrow scope, budget, or
timeout and may strengthen evidence, approval, risk, rollback, trace, and
strictness. It cannot broaden its parent grant.

## Capability Classes

| Class | Meaning | EGCFv1 status |
| --- | --- | --- |
| C0 | Observe only | Enabled |
| C1 | Analyse and create internal proposal records | Enabled |
| C2 | Simulate in disposable or synthetic environments | Enabled |
| C3 | Local workspace mutation through EON | Enabled with exact authority and approval |
| C4 | External mutation | Fail closed |
| C5 | Critical or destructive mutation | Fail closed |

Effective authority is the intersection of capability ceiling, scoped grants,
required evidence, approval policy, budget, expiry, and use count.

## Core Namespaces

| Namespace | Verbs |
| --- | --- |
| `capability` | `list`, `describe`, `graph`, `check`, `request`, `grant`, `revoke`, `audit`, `explain` |
| `hrt` | `interpret`, `assumptions`, `ambiguity`, `clarify`, `claims`, `provenance`, `summary`, `explain` |
| `ourd` | `model`, `objects`, `relations`, `boundaries`, `dependencies`, `impact`, `trace`, `scope`, `exclusions`, `graph` |
| `iurm` | `dimensions`, `baseline`, `vary`, `screen`, `interactions`, `sensitivity`, `mvd`, `optimise` |
| `ieps` | `generate`, `coverage`, `oracle`, `counterexamples`, `uniqueness`, `mutation`, `shrink`, `qualify`, `gate` |
| `eon` | `draft`, `validate`, `compile`, `simulate`, `authorise`, `execute`, `rollback`, `compare` |
| `algorithm` | `register`, `search`, `compare`, `qualify`, `benchmark`, `compose`, `evolve`, `retire`, `explain`, `select` |
| `evidence` | `collect`, `classify`, `compare`, `graph`, `export`, `confidence`, `conflicts`, `history` |
| `invariant` | `discover`, `register`, `validate`, `compare`, `conflicts`, `supersede` |
| `decision` | `create`, `query`, `history`, `supersede`, `explain`, `conflicts` |
| `debug` | `reproduce`, `minimise`, `bisect`, `hypotheses`, `trace`, `compare`, `rootcause`, `verify` |
| `experiment` | `design`, `ofat`, `factorial`, `covering`, `benchmark`, `analyse`, `repeat`, `compare` |
| `verify` | `unit`, `integration`, `property`, `fuzz`, `mutation`, `differential`, `metamorphic`, `regression`, `performance`, `security` |
| `simulate` | `worktree`, `migration`, `dependency`, `api`, `hardware`, `filesystem`, `network`, `chaos`, `rollback` |
| `performance` | `profile`, `benchmark`, `hotspots`, `regression`, `memory`, `gpu`, `io` |
| `security` | `threat-model`, `taint`, `sast`, `secrets`, `permissions`, `provenance`, `sbom`, `audit` |
| `repo` | `graph`, `symbols`, `ownership`, `history`, `evolution`, `metrics`, `hotspots`, `timeline` |
| `workflow` | `create`, `compile`, `execute`, `pause`, `resume`, `replay`, `branch`, `merge`, `monitor` |
| `agent` | `spawn`, `specialise`, `debate`, `review`, `critic`, `merge`, `consensus`, `terminate` |
| `cfel` | `observe`, `classify`, `compare`, `diagnose`, `recover`, `learn`, `stability`, `regression` |
| `assurance` | `generate` |

The checked-in authority for the complete namespace list is
`commands/v1/catalog.json`.

## Domain Namespaces

EGCFv1 includes a versioned domain-pack SDK and deterministic `grammar@1`,
`physics@1`, `geometry@1`, `vision@1`, `robotics@1`, and `cad@1` packs. Every
pack declares input/output contracts, datasets, units or tolerances where
applicable, invariants, evidence policy, and a no-authority-transfer boundary.
Unavailable or unqualified implementations fail closed rather than falling
through to shell execution.

The per-command generated contract table is checked in at
`docs/EGCFV1_GENERATED_REFERENCE.md`; its machine-readable companion is
`commands/v1/contracts.json`.

## Examples

Compile a read-only command and inspect all projections:

```bash
egcf capability list --repo . \
  --dry-run --why --json --graph --trace --record
```

Compile the parser-regression composite objective:

```bash
egcf run fix parser regression --repo . \
  --input '{"target":"src/parser.py","symptom":"precedence changed"}' \
  --dry-run --why --graph --strict
```

Rebuild the disposable SQLite projection from canonical records:

```bash
egcf --repo . --rebuild-projection
```

Capture the current source snapshot:

```bash
egcf --repo . --snapshot
```

## Record Families

The immutable object store contains intents, command definitions and
invocations, capability specs and grants, algorithm definitions and
qualifications, selection decisions, claims, evidence requirements and
artifacts, confidence assessments, invariants, decisions, workflows, compiled
graphs, execution plans, approvals, executions, rollbacks, failures, assurance
cases, artifacts, and supersedence records.

## Trust Rules

- Command definitions contain data, not callbacks or executor references.
- Algorithm implementation digests bind exact implementation source.
- Model, MCP, skill, Codex, and agent text is untrusted proposal output.
- Simulation evidence is labeled and cannot satisfy real-execution gates.
- Agent consensus is not approval.
- Assurance cases report approval facts from immutable approval records; prose
  cannot create authority.
- Replay of a C3 plan creates a fresh candidate and requires fresh approval.
