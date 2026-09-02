# OURD Summarization and Governance Recovery Audit

**Audit date:** August 30, 2026  
**Plan:** `OURD_SUMMARIZATION_GOVERNANCE_RECOVERY_IMPLEMENTATION_PLAN.md`  
**Status:** Core recovery implementation and deterministic original-incident
control flow are complete; release certification still requires a frozen
qualification bundle and human approval.

## Incident Resolution

The original request:

```text
Summarise each /docs/ markdown file.
```

now compiles as a read-only `SUMMARIZE` intent. `/docs/` resolves to the bounded
workspace-relative `docs` path. The turn exposes repository and corpus read
tools, not governance, mutation, or super-reasoning tools. A deterministic
corpus manifest enumerates every authorized Markdown file, each file must reach
complete line coverage before its summary is accepted, and completion requires
exact set equality between manifested and summarized paths.

## Requirement Evidence

| ID | Implementation | Current evidence status |
| --- | --- | --- |
| SGR-001 | British and US summary language recognized | Interaction tests pass |
| SGR-002 | Summary requests summary/evidence/coverage, not a reasoning certificate | Intent assertions pass |
| SGR-003 | `/docs/`, folders, and Markdown include patterns resolve exactly | Context and manifest tests pass |
| SGR-004 | Signed turn policy is route/snapshot/context bound and can only narrow authority | Runtime enforcement implemented; broader property corpus remains desirable |
| SGR-005 | Summary tool surface is read/corpus only | Tool-name snapshot passes |
| SGR-006 | Super reasoning hidden before governance | Before/after governance test passes |
| SGR-007 | Dispatch rechecks tool and state preconditions | Injected unavailable-call test passes |
| SGR-008 | Failures use signed structured codes/classes/transitions | `GOVERNANCE_REQUIRED` envelope assertions pass |
| SGR-009 | First recoverable failure permits correction | First failure records one deterministic collision and governance transition succeeds |
| SGR-010 | Identical retry stops counting as progress | Collision identity and count remain stable |
| SGR-011 | Corpus manifest binds exact deterministic paths, hashes, and snapshot | Golden manifest ordering test passes |
| SGR-012 | Read ranges merge into exact coverage and uncovered ranges | Coverage completion tests pass |
| SGR-013 | Summary artifact binds file hash, snapshot, read evidence, prompt, and model | Artifact validation test passes |
| SGR-014 | Corpus completion is exact set equality | Complete report tests pass |
| SGR-015 | Context compaction preserves summary semantics and list-valued evidence IDs | Compaction regression test passes |
| SGR-016 | Terminal projection separates proposals, observations, and policy failures | Projection separation test passes |
| SGR-017 | Markdown evidence can be restored from active evidence after compaction | Markdown restoration test passes |
| SGR-018 | Chat activity is concise and aggregated | Activity projection tests pass |
| SGR-019 | Full evidence remains in append-only/core persistence and read-only detail projections | Existing replay/persistence suites remain authoritative |
| SGR-020 | `/scope` is read-only and explanatory | Session/interaction tests pass |
| SGR-021 | Mutation authority, transactions, EON, evidence gate, and rollback remain separate owners | Adjacent authority/action suites pass |
| SGR-022 | Original incident completes route-to-manifest-to-summary-to-report control flow | Frozen deterministic fixture passes |

## Epistemic Boundary

The runtime verifies source bytes, paths, hashes, line coverage, tool outputs,
policy failures, and artifact signatures. It does not certify that model summary
prose is complete, insightful, or true. Each summary is labelled
`MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE`, and the terminal report must state
material coverage or source limits.

Repository text is untrusted data. Model-proposed tool arguments are displayed
separately from verified tool outputs. A model cannot convert a summary request
into mutation authority or certified reasoning by naming a hidden tool.

## Release Boundary

Automated evidence does not certify a release. Remaining release gates are:

1. run full discovery, packaging, entry-point, replay, and headless GUI checks
   from one frozen snapshot;
2. record source, schema, fixture, report, wheel, and test-output hashes;
3. execute the oversized-corpus and broader adversarial matrix; and
4. obtain exact-hash human approval before certification or publication.
