# EGCFv1 Requirements Matrix

**Assessment date:** 2026-08-21  
**Release state:** implementation candidate pending exact-snapshot validation and human approval

This matrix maps the normative requirements in `EGCFV1_IMPLEMENTATION_PLAN.md`
to implementation and deterministic evidence. A passing test is technical
evidence, not release approval.

## Architecture And Identity

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| Typed, canonical command objects | `ourd/egcf/models.py`, `ourd/egcf/ids.py`, `ourd/egcf/schemas.py` | `tests/test_egcf_core.py`, `tests/test_schemas.py` | Implemented |
| Every command input field has an explicit type and exact definition binding | `ourd/egcf/catalog.py`, `CommandInvocation.command_definition_id` | `tests/test_egcf_completion.py` | Implemented |
| Schemas and command references are reproducibly generated | `tools/generate_egcf_reference.py`, `commands/v1/contracts.json` | generator check in `tests/test_egcf_completion.py` and `tools/validate_egcf.py` | Implemented |
| Immutable content-addressed records | `ourd/egcf/store.py` | projection rebuild and tamper tests in `tests/test_egcf_core.py` | Implemented |
| Rebuildable query projection | `ourd/egcf/store.py` SQLite projection over immutable objects/events | `test_object_and_artifact_projection_rebuilds_with_events` | Implemented |
| Separate EGCF event chain bound to OURD history | `ourd/egcf/store.py` | event projection and tamper checks | Implemented |
| Universal modifiers in shared code | `ourd/egcf/context.py`, `ourd/egcf/cli.py` | `tests/test_egcf_core.py`, `tests/test_egcf_cli.py` | Implemented |
| Stable graph identity for executable semantics | `ourd/egcf/compiler.py` | compiler and property tests | Implemented |
| Every lifecycle stage is reported as completed, not required, or blocked | `ourd/egcf/lifecycle.py`, engine projections | `tests/test_egcf_completion.py` | Implemented |

## Capability And Authority

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| C0-C5 capability classes | `ourd/egcf/capabilities.py`, `ourd/authority.py` | compiler/security tests | Implemented |
| Composition can only preserve or narrow authority | `CommandContext.inherit`, `CapabilityResolver`, compiler checks | scope-narrowing property and anti-broadening tests | Implemented |
| Models, agents, MCP, skills, and adapters cannot transfer authority | adapter contracts and `OURDAgent.invoke_semantic_command` | vertical and security tests | Implemented |
| C3 mutation uses only EON and transactions | `ourd/egcf/adapters/eon.py`, `ourd/agent.py`, `ourd/transactions.py` | exact approval, apply, restart rollback test | Implemented |
| C4 and C5 fail closed | compiler and adapter registry | `test_c4_and_c5_are_fail_closed` | Implemented |
| Approval binds the exact plan, graph, source, authority, expiry, and use count | `ourd/egcf/approval.py`, `ourd/egcf/engine.py` | stale approval, replay, and use-limit tests | Implemented |

## Algorithms And Commands

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| Every executable command resolves through an exact algorithm | `ourd/egcf/registry.py`, `algorithms/v1/catalog.json` | catalog parity, substitution, and vertical tests | Implemented |
| Algorithm digest binds implementation source | `AlgorithmRegistry.bootstrap` | post-compile substitution refusal | Implemented |
| Qualification is contextual, expiring, and evidence-bound | `ourd/egcf/registry.py`, `ourd/egcf/ieps.py` | reported-test and evidence-gate tests | Implemented |
| Selection receipts contain the score components actually used | `SelectionEngine.select` | completion and vertical tests | Implemented |
| Model-reported tests cannot self-qualify | producer/category restrictions | `test_reported_tests_cannot_self_qualify_algorithm` | Implemented |
| Namespace catalog is versioned and data-driven | `commands/v1/catalog.json`, `ourd/egcf/catalog.py` | catalog/schema parity tests | Implemented |
| First ten high-value commands have an end-to-end path | semantic handlers, workflows, simulation, assurance | `test_ten_priority_commands_execute_end_to_end` | Implemented |

## Workflow, Execution, And Recovery

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| Workflow DAG compilation and static checking | `ourd/egcf/compiler.py` | cycle, reference, conflict, budget, retry tests | Implemented |
| Conditional nodes and persisted checkpoints | `ourd/egcf/engine.py` | checkpoint pause/resume test | Implemented |
| Global action, retry, and wall-clock budgets | compiler and engine | budget/refusal security tests | Implemented |
| Simulation is distinct from execution | `ourd/egcf/simulation.py`, simulation adapter | evidence and vertical tests | Implemented |
| Replay recompiles and cannot reuse C3 approval | `EGCFEngine.replay` | replay graph and approval-use tests | Implemented |
| Rollback is restart-safe and authority-bound | EON adapter and `TransactionManager` recovery path | restart-safe rollback test | Implemented |
| Workflow templates are versioned | `workflows/v1/parser-regression.json` | vertical workflow tests | Implemented |

## Evidence, Memory, And Assurance

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| Evidence is classified by producer, category, simulation, freshness, and independence | `ourd/egcf/evidence.py` | evidence-gating tests | Implemented |
| Duplicate evidence cannot inflate confidence | content hash and independence-group checks | duplicate-confidence test | Implemented |
| Conflicts and known unknowns remain visible | confidence, decision, invariant, assurance records | evidence and assurance tests | Implemented |
| Invariants and decisions are append-only supersedable | `invariants.py`, `decisions.py`, `SupersedenceRecord` | conflict/supersedence tests | Implemented |
| Assurance narratives cannot create approval | `ourd/egcf/assurance.py`, immutable approval lookup | assurance-gap test | Implemented |
| CFEL records failures without blind retry | existing `ourd/cfel.py` plus EGCF failure records | existing CFEL suite and EGCF retry tests | Implemented |

## Adapters And Domain Packs

| Requirement | Implementation | Deterministic evidence | State |
| --- | --- | --- | --- |
| Codex, MCP, skill, shell, model, agent, simulation, engine-control, and EON adapters declare schemas, effects, idempotency, boundaries, and rollback | `ourd/egcf/adapters/` | adapter inventory and completion tests | Implemented |
| External textual output is untrusted data | adapter result envelopes | vertical adapter test | Implemented |
| Subagent grants are narrowed and consensus is not authority | `adapters/agent.py` | vertical adapter test | Implemented |
| Domain packs cannot grant authority | `ourd/egcf/domains.py` | domain-pack completion test | Implemented |
| Grammar, physics, geometry, vision, robotics, and CAD reference packs | `ourd/egcf/domains.py` | strict contract and deterministic sample tests | Implemented |

## Validation And Promotion

| Requirement | Implementation | Evidence | State |
| --- | --- | --- | --- |
| Deterministic validation report for one exact snapshot | `tools/validate_egcf.py` | generated report under `.ourd-agent/egcf/validation/` | Ready to run |
| Package/wheel validation | validator builds and inspects the wheel and entry point | validation bundle | Ready to run |
| Live Qwen evaluation with exact tag/digest | `tools/evaluate_egcf_qwen.py` | model report under `.ourd-agent/egcf/model-evaluations/` | Ready to run |
| Source remains unchanged during validation/evaluation | before/after workspace hash and source manifest | both report types | Enforced |
| Human approval names exact candidate and validation hashes | external human decision | no implementation can self-satisfy this | Pending |
| Certification records limitations and excluded scope | release governance | cannot occur before exact approval | Pending |

## Release Boundary

The implementation can reach `DETERMINISTICALLY_VALIDATED` and
`LIVE_MODEL_EVALUATED` automatically. It cannot promote itself to
`HUMAN_APPROVED` or `CERTIFIED`. Any source edit after validation creates a new
candidate and invalidates the prior validation binding.
