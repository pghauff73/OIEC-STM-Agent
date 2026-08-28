from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from ..authority import finalize_authority, load_authority, read_only_authority, validate_authority
from ..models import AuthorityManifest
from ..workspace import Workspace
from .adapters.eon import EONAdapter
from .adapters.control import EngineControlAdapter
from .adapters.semantic import SemanticAdapter
from .adapters.simulation import SimulationAdapter
from .approval import ApprovalManager
from .capabilities import CAPABILITY_ORDER, CapabilityResolver
from .compiler import WorkflowCompiler
from .context import CommandContext
from .errors import ApprovalError, CompilationError, EGCFError
from .handlers import SemanticHandlers
from .ids import parse_typed_id, sha256_json, utc_now
from .lifecycle import Lifecycle
from .models import (
    ApprovalRecord,
    CommandInvocation,
    CompiledWorkflow,
    ExecutionPlan,
    ExecutionRecord,
    FailureRecord,
    IntentRecord,
    RollbackRecord,
    SelectionDecision,
    WorkflowDefinition,
    WorkflowNode,
)
from .registry import AlgorithmRegistry, CommandRegistry
from .schemas import validate_json_value
from .store import EGCFStore


class EGCFEngine:
    def __init__(
        self,
        root: Path,
        *,
        authority_path: Path | None = None,
        authority_manifest: AuthorityManifest | None = None,
        actor: str = "user",
        recovery_transaction_id: str = "",
    ):
        self.workspace = Workspace(root)
        if authority_path is not None and authority_manifest is not None:
            raise EGCFError("provide authority_path or authority_manifest, not both")
        self.authority_path = authority_path
        self.actor = actor
        self.recovery_transaction_id = recovery_transaction_id
        if authority_manifest is not None:
            self.authority = AuthorityManifest(**asdict(authority_manifest))
            validate_authority(self.authority, self.workspace)
            finalize_authority(self.authority)
        elif authority_path is not None:
            self.authority = load_authority(
                authority_path,
                self.workspace,
                allow_snapshot_mismatch=bool(recovery_transaction_id),
            )
        else:
            self.authority = read_only_authority(self.workspace)
        self.store = EGCFStore(self.workspace.root)
        self.commands = CommandRegistry(self.store)
        self.capabilities = CapabilityResolver(self.store)
        self.algorithms = AlgorithmRegistry(self.store, self.commands)
        self.compiler = WorkflowCompiler(
            self.store,
            self.workspace,
            self.commands,
            self.algorithms,
            self.capabilities,
        )
        self.grant = self.capabilities.grant_from_authority(self.authority)
        self.grant_id = self.store.register(self.grant)
        self.handlers = SemanticHandlers(
            store=self.store,
            workspace=self.workspace,
            commands=self.commands,
            algorithms=self.algorithms,
            capabilities=self.capabilities,
            compiler=self.compiler,
        )
        self.approvals = ApprovalManager(self.store, self.workspace)
        self.eon = EONAdapter(
            self.workspace.root,
            authority_path,
            recovery_transaction_id=recovery_transaction_id,
        )
        self.simulation = SimulationAdapter(self.workspace.root)
        self.control = EngineControlAdapter(
            authorize=self.authorize,
            execute_plan=self.execute_plan,
        )

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "EGCFEngine":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _intent(self, command_id: str, inputs: Dict[str, Any]) -> str:
        raw_request = f"{command_id} {inputs}"
        record = IntentRecord(
            raw_request=raw_request,
            raw_request_hash=sha256_json(raw_request),
            actor=self.actor,
            objective=command_id,
            assumptions=list(inputs.get("assumptions", [])),
            ambiguities=list(inputs.get("ambiguities", [])),
            provenance={"interface": "egcf"},
            created_at=utc_now(),
        )
        return self.store.register(record)

    def compile_command(
        self,
        command_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        modifiers: Optional[Dict[str, Any]] = None,
    ) -> tuple[CompiledWorkflow, CommandContext, Lifecycle]:
        definition = self.commands.resolve(command_id)
        context = CommandContext.from_mapping(modifiers)
        intent_id = self._intent(definition.command_id, inputs or {})
        invocation = CommandInvocation(
            command_id=definition.command_id,
            inputs=dict(inputs or {}),
            modifiers=context.to_dict(),
            scope=list(context.scope),
            command_definition_id=definition.object_id,
            intent_id=intent_id,
            actor=self.actor,
            created_at=utc_now(),
        )
        lifecycle = Lifecycle()
        lifecycle.compress(["INTERPRETED", "MODELLED", "RESOLVED", "QUALIFIED"])
        compiled = self.compiler.compile_invocation(
            invocation,
            context=context,
            grant=self.grant,
        )
        lifecycle.transition("COMPILED")
        return compiled, context, lifecycle

    def create_execution_plan(
        self,
        compiled: CompiledWorkflow,
        *,
        prepare_mutations: bool,
    ) -> ExecutionPlan:
        rollback_graph = copy.deepcopy(compiled.rollback_graph)
        eon_action_ids: list[str] = []
        evidence_ids = list(compiled.command_context.get("evidence", []))
        for node in compiled.nodes:
            selection = self.store.get(node["selection_id"])
            if not isinstance(selection, SelectionDecision):
                raise EGCFError("compiled node references an invalid selection decision")
            evidence_ids.extend([selection.object_id, *selection.evidence_ids])
        if prepare_mutations:
            for node in compiled.nodes:
                algorithm = self.algorithms.resolve(node["algorithm_id"])
                if algorithm.implementation_kind != "eon":
                    continue
                prepared = self.eon.prepare(node)
                rollback_graph.setdefault(node["node_id"], {})["prepared"] = prepared
                if prepared.get("action_id"):
                    eon_action_ids.append(prepared["action_id"])
        plan = ExecutionPlan(
            compiled_workflow_id=compiled.object_id,
            graph_hash=compiled.graph_hash,
            source_snapshot_hash=compiled.source_snapshot_hash,
            node_order=list(compiled.execution_order),
            eon_action_ids=eon_action_ids,
            algorithm_digests=[node["algorithm_digest"] for node in compiled.nodes],
            capability_grant_id=self.grant_id,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            budget=dict(compiled.budget),
            rollback_graph=rollback_graph,
            approval_policy=compiled.approval_policy,
            expires_at="",
            created_at=utc_now(),
        )
        self.store.register(plan, event_type="egcf_execution_plan_created")
        return plan

    def invoke(
        self,
        command_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        modifiers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resolved = self.commands.resolve(command_id)
        compiled, context, lifecycle = self.compile_command(
            resolved.command_id, inputs, modifiers
        )
        if CAPABILITY_ORDER[compiled.capability_level] >= CAPABILITY_ORDER["C4"]:
            lifecycle.transition("REFUSED")
            raise CompilationError("C4 and C5 executors are fail-closed until explicitly qualified")
        plan = self.create_execution_plan(
            compiled,
            prepare_mutations=not context.dry_run and compiled.capability_level == "C3",
        )
        projections = self._projections(compiled, plan, context, lifecycle)
        if context.dry_run:
            lifecycle.transition("COMPLETED")
            projections["lifecycle"] = list(lifecycle.history)
            projections["lifecycle_stages"] = lifecycle.projection()
            return projections
        if compiled.capability_level == "C2" and not (
            context.simulate or resolved.namespace == "simulate"
        ):
            lifecycle.transition("REFUSED")
            raise EGCFError("C2 commands require --simulate or a simulate namespace command")
        if compiled.approval_policy in {"human", "quorum"}:
            lifecycle.transition("AWAITING_APPROVAL")
            projections.update(
                {
                    "status": "AWAITING_APPROVAL",
                    "approval_required": compiled.approval_policy,
                    "lifecycle": list(lifecycle.history),
                    "lifecycle_stages": lifecycle.projection(),
                }
            )
            return projections
        lifecycle.transition("AUTHORIZED")
        result = self.execute_plan(plan.object_id)
        if compiled.nodes[0]["algorithm_id"].startswith("builtin.eon.authorise") or compiled.nodes[0]["algorithm_id"].startswith("builtin.workflow.execute"):
            control_output = result["outputs"][-1]
            return {
                **projections,
                **control_output,
                "control_execution_plan_id": plan.object_id,
                "control_execution_ids": result["execution_ids"],
            }
        return {**projections, **result}

    def _projections(
        self,
        compiled: CompiledWorkflow,
        plan: ExecutionPlan,
        context: CommandContext,
        lifecycle: Lifecycle,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": True,
            "status": "COMPILED",
            "compiled_workflow_id": compiled.object_id,
            "execution_plan_id": plan.object_id,
            "graph_hash": compiled.graph_hash,
            "source_snapshot_hash": compiled.source_snapshot_hash,
            "lifecycle": list(lifecycle.history),
            "lifecycle_stages": lifecycle.projection(),
        }
        if context.why:
            result["why"] = {
                "capability_level": compiled.capability_level,
                "capability_requirements": compiled.capability_requirements,
                "risk": compiled.risk,
                "approval_policy": compiled.approval_policy,
                "evidence_requirements": compiled.evidence_requirements,
                "unresolved": compiled.unresolved,
                "selections": [node["selection_id"] for node in compiled.nodes],
            }
        if context.graph:
            result["graph"] = {"nodes": compiled.nodes, "edges": compiled.edges}
        if context.trace:
            result["trace"] = {
                "lifecycle": list(lifecycle.history),
                "lifecycle_stages": lifecycle.projection(),
                "event_head": self.store.events.head,
                "plan": plan.to_dict(),
            }
        if context.record:
            result["record"] = {
                "compiled_workflow_id": compiled.object_id,
                "execution_plan_id": plan.object_id,
                "minimum_recording_always_enabled": True,
            }
        return result

    def authorize(
        self,
        plan_id: str,
        *,
        approver: str,
        authority: str,
        constraints: Optional[Dict[str, Any]] = None,
        expires_at: str = "",
        use_limit: int = 1,
    ) -> str:
        return self.approvals.authorize(
            plan_id,
            approver=approver,
            authority=authority,
            constraints=constraints,
            expires_at=expires_at,
            human=True,
            use_limit=use_limit,
        )

    @staticmethod
    def _resolve_value(
        value: Any,
        outputs: Dict[str, Any],
        known_sources: set[str] | None = None,
    ) -> Any:
        if isinstance(value, dict) and "$from" in value:
            source = str(value["$from"])
            if known_sources is not None and source not in known_sources:
                return copy.deepcopy(value)
            if source not in outputs:
                if "default" in value:
                    return copy.deepcopy(value["default"])
                raise EGCFError(f"referenced node has no output: {source}")
            resolved = outputs[source]
            for segment in value.get("path", []):
                try:
                    resolved = resolved[segment]
                except (KeyError, IndexError, TypeError) as exc:
                    if "default" in value:
                        return copy.deepcopy(value["default"])
                    raise EGCFError(
                        f"cannot resolve output reference {source} path {value.get('path', [])}"
                    ) from exc
            return copy.deepcopy(resolved)
        if isinstance(value, dict):
            return {
                key: EGCFEngine._resolve_value(item, outputs, known_sources)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [EGCFEngine._resolve_value(item, outputs, known_sources) for item in value]
        return copy.deepcopy(value)

    @classmethod
    def _condition_met(cls, condition: Dict[str, Any], outputs: Dict[str, Any]) -> bool:
        if not condition:
            return True
        allowed = {"value", "equals", "not_equals", "in", "truthy"}
        unknown = sorted(set(condition) - allowed)
        if unknown:
            raise EGCFError(f"condition has unknown fields: {unknown}")
        observed = cls._resolve_value(condition.get("value"), outputs, set(outputs))
        checks = []
        if "equals" in condition:
            checks.append(observed == condition["equals"])
        if "not_equals" in condition:
            checks.append(observed != condition["not_equals"])
        if "in" in condition:
            checks.append(observed in condition["in"])
        if "truthy" in condition:
            checks.append(bool(observed) is bool(condition["truthy"]))
        if not checks:
            raise EGCFError("condition requires equals, not_equals, in, or truthy")
        return all(checks)

    def execute_plan(
        self,
        plan_id: str,
        approval_id: str = "",
        *,
        pause_at_checkpoint: bool = False,
        resume: bool = False,
    ) -> Dict[str, Any]:
        plan = self.store.get(plan_id)
        if not isinstance(plan, ExecutionPlan):
            raise EGCFError(f"not an execution plan: {plan_id}")
        compiled = self.store.get(plan.compiled_workflow_id)
        if not isinstance(compiled, CompiledWorkflow):
            raise EGCFError("execution plan references an invalid compiled workflow")
        if plan.graph_hash != compiled.graph_hash:
            raise EGCFError("compiled graph hash changed after plan creation")
        if plan.source_snapshot_hash != self.workspace.snapshot_hash():
            raise EGCFError("execution plan source snapshot is stale")
        approval: ApprovalRecord | None = None
        if plan.approval_policy in {"human", "quorum"}:
            if not approval_id:
                raise ApprovalError("execution plan requires an approval record")
            approval = self.approvals.validate(plan, approval_id)
        context = CommandContext.from_mapping(compiled.command_context)
        lifecycle = Lifecycle("COMPILED")
        lifecycle.transition("AUTHORIZED")
        lifecycle.transition("EXECUTING")
        nodes = {node["node_id"]: node for node in compiled.nodes}
        executions: list[ExecutionRecord] = []
        completed: list[tuple[Dict[str, Any], Any, Dict[str, Any]]] = []
        node_outputs: Dict[str, Any] = {}
        completed_node_ids: set[str] = set()
        if resume:
            paused = self.store.find(
                "execution",
                lambda item: isinstance(item, ExecutionRecord)
                and item.plan_id == plan.object_id
                and item.status == "PAUSED",
            )
            if not paused:
                raise EGCFError("resume requires a persisted paused checkpoint")
            prior = self.store.find(
                "execution",
                lambda item: isinstance(item, ExecutionRecord)
                and item.plan_id == plan.object_id
                and item.node_id in nodes
                and item.status in {"COMPLETED", "SIMULATED", "SKIPPED"},
            )
            for record in prior:
                completed_node_ids.add(record.node_id)
                node_outputs[record.node_id] = record.output
        pause_requested = pause_at_checkpoint or (
            not resume
            and bool(
                self.store.find(
                    "execution",
                    lambda item: isinstance(item, ExecutionRecord)
                    and item.plan_id == plan.object_id
                    and item.status == "PAUSE_REQUESTED",
                )
            )
        )
        started_monotonic = time.monotonic()
        action_budget = plan.budget.get("actions")
        wall_budget = plan.budget.get("wall_seconds")
        semantic = SemanticAdapter(self.handlers, context, self.grant)
        try:
            for action_index, node_id in enumerate(plan.node_order, start=1):
                if node_id in completed_node_ids:
                    continue
                if action_budget is not None and action_index > int(action_budget):
                    raise EGCFError("execution action budget exceeded")
                if wall_budget is not None and time.monotonic() - started_monotonic > float(wall_budget):
                    raise EGCFError("execution wall-time budget exceeded")
                node = nodes[node_id]
                algorithm = self.algorithms.resolve(node["algorithm_id"])
                if algorithm.implementation_digest != node["algorithm_digest"]:
                    raise EGCFError("algorithm implementation digest drifted after compilation")
                if algorithm.status in {"RETIRED", "DEPRECATED", "PROPOSED"}:
                    raise EGCFError(f"algorithm is not executable: {algorithm.status}")
                if algorithm.implementation_kind == "eon":
                    adapter = self.eon
                elif algorithm.implementation_kind == "engine-control":
                    adapter = self.control
                elif algorithm.implementation_kind == "simulation":
                    adapter = self.simulation
                else:
                    adapter = semantic
                runtime_node = copy.deepcopy(node)
                runtime_node["inputs"] = self._resolve_value(
                    node["inputs"],
                    node_outputs,
                    set(nodes),
                )
                definition = self.commands.resolve(node["command_id"])
                validate_json_value(definition.input_schema, runtime_node["inputs"])
                if not self._condition_met(node.get("when", {}), node_outputs):
                    record = ExecutionRecord(
                        plan_id=plan.object_id,
                        node_id=node_id,
                        algorithm_id=node["algorithm_id"],
                        executor="egcf-engine",
                        inputs_hash=sha256_json(runtime_node["inputs"]),
                        output={"skipped": True, "condition": node.get("when", {})},
                        status="SKIPPED",
                        usage={"actions": 0},
                        evidence_ids=[],
                        started_at=utc_now(),
                        completed_at=utc_now(),
                        simulated=False,
                    )
                    self.store.register(record, event_type="egcf_node_skipped")
                    executions.append(record)
                    node_outputs[node_id] = record.output
                    continue
                preflight = adapter.preflight(runtime_node)
                if not preflight.get("ok"):
                    raise EGCFError(f"executor preflight failed: {preflight}")
                if algorithm.implementation_kind == "simulation":
                    output = adapter.execute(runtime_node, simulation_authorized=True)
                elif algorithm.implementation_kind == "eon":
                    output = adapter.execute(
                        runtime_node,
                        prepared=plan.rollback_graph.get(node_id, {}).get("prepared", {}),
                        approval=approval.to_dict() if approval else {},
                        approval_id=approval_id,
                    )
                elif algorithm.implementation_kind == "engine-control":
                    output = adapter.execute(runtime_node)
                else:
                    output = adapter.execute(
                        runtime_node,
                        approval=approval.to_dict() if approval else {},
                        approval_id=approval_id,
                    )
                validate_json_value(algorithm.output_schema, output, f"$output.{node_id}")
                if algorithm.implementation_kind == "builtin":
                    validate_json_value(
                        definition.output_schema,
                        output,
                        f"$command_output.{node_id}",
                    )
                verification = adapter.verify(runtime_node, output)
                if not verification.get("verified"):
                    if node["capability_level"] in {"C3", "C4", "C5"}:
                        adapter.rollback_or_compensate(runtime_node, output)
                    raise EGCFError(f"executor verification failed: {verification}")
                status = "SIMULATED" if output.get("simulated") else "COMPLETED"
                evidence_id = self.handlers.evidence.collect(
                    subject_id=plan.object_id,
                    content={"node_id": node_id, "output": output, "verification": verification},
                    category="test" if verification.get("verified") else "observation",
                    producer=f"deterministic-{adapter.name}-adapter",
                    method="executor verification",
                    source_snapshot_hash=plan.source_snapshot_hash,
                    target=node_id,
                    oracle=f"{adapter.name}.verify",
                    environment={"adapter_version": adapter.version},
                    command_id=node["command_id"],
                    algorithm_id=node["algorithm_id"],
                    success=True,
                    independence_group=f"executor:{adapter.name}:{node_id}",
                    simulated=output.get("simulated", False),
                )
                record = ExecutionRecord(
                    plan_id=plan.object_id,
                    node_id=node_id,
                    algorithm_id=node["algorithm_id"],
                    executor=adapter.name,
                    inputs_hash=sha256_json(runtime_node["inputs"]),
                    output=output,
                    status=status,
                    usage={"actions": 1},
                    evidence_ids=[evidence_id],
                    started_at=utc_now(),
                    completed_at=utc_now(),
                    simulated=output.get("simulated", False),
                )
                self.store.register(record, event_type="egcf_node_executed")
                executions.append(record)
                completed.append((runtime_node, adapter, output))
                node_outputs[node_id] = output
                if node.get("checkpoint") and pause_requested:
                    pause_record = ExecutionRecord(
                        plan_id=plan.object_id,
                        node_id=f"__checkpoint__:{node_id}",
                        algorithm_id="workflow.control@1",
                        executor="egcf-engine",
                        inputs_hash=sha256_json(node_id),
                        output={"checkpoint_node_id": node_id},
                        status="PAUSED",
                        usage={"actions": 0},
                        evidence_ids=list(record.evidence_ids),
                        started_at=utc_now(),
                        completed_at=utc_now(),
                    )
                    pause_id = self.store.register(
                        pause_record,
                        event_type="egcf_workflow_paused",
                    )
                    return {
                        "ok": True,
                        "status": "PAUSED",
                        "plan_id": plan.object_id,
                        "checkpoint_id": pause_id,
                        "checkpoint_node_id": node_id,
                        "execution_ids": [item.object_id for item in executions],
                        "lifecycle": lifecycle.history,
                        "lifecycle_stages": lifecycle.projection(),
                    }
        except Exception as exc:
            rollback_results = []
            for node, adapter, output in reversed(completed):
                if node["capability_level"] in {"C3", "C4", "C5"}:
                    try:
                        rollback_results.append(adapter.rollback_or_compensate(node, output))
                    except Exception as rollback_exc:
                        rollback_results.append({"status": "FAILED", "error": str(rollback_exc)})
            rollback_record = RollbackRecord(
                plan_id=plan.object_id,
                execution_ids=[record.object_id for record in executions],
                rollback_class="mixed" if len(rollback_results) > 1 else (
                    next(iter(plan.rollback_graph.values())).get("class", "none")
                    if plan.rollback_graph
                    else "none"
                ),
                pre_state={"source_snapshot_hash": plan.source_snapshot_hash},
                post_state={"source_snapshot_hash": self.workspace.snapshot_hash()},
                restored_state={"source_snapshot_hash": self.workspace.snapshot_hash()},
                failures=[
                    str(item.get("error", item))
                    for item in rollback_results
                    if item.get("status") == "FAILED"
                ],
                status=(
                    "ROLLED_BACK"
                    if rollback_results and all(item.get("status") != "FAILED" for item in rollback_results)
                    else "PARTIALLY_COMPENSATED" if rollback_results else "NOT_REQUIRED"
                ),
                created_at=utc_now(),
            )
            rollback_id = self.store.register(
                rollback_record,
                event_type="egcf_rollback_recorded",
            )
            failure = FailureRecord(
                subject_id=plan.object_id,
                expected="all authorized plan nodes execute and verify",
                observed=f"{type(exc).__name__}: {exc}",
                active_dimension="execution",
                frozen_dimensions=["plan hash", "authority", "algorithm digests"],
                evidence_ids=[identifier for record in executions for identifier in record.evidence_ids],
                retry_count=0,
                status="FAILED",
                created_at=utc_now(),
            )
            failure_id = self.store.register(failure, event_type="egcf_execution_failed")
            lifecycle.transition("FAILED")
            raise EGCFError(
                f"execution failed; failure_id={failure_id}; rollback_id={rollback_id}; rollback={rollback_results}: {exc}"
            ) from exc
        lifecycle.transition("VERIFYING")
        lifecycle.transition("COMPLETED")
        workflow_record = ExecutionRecord(
            plan_id=plan.object_id,
            node_id="__workflow__",
            algorithm_id="workflow.lifecycle@1",
            executor="egcf-engine",
            inputs_hash=sha256_json(plan.node_order),
            output={"node_execution_ids": [record.object_id for record in executions]},
            status="SIMULATED" if executions and all(record.simulated for record in executions) else "COMPLETED",
            usage={"actions": len(executions)},
            evidence_ids=[identifier for record in executions for identifier in record.evidence_ids],
            started_at=executions[0].started_at if executions else utc_now(),
            completed_at=utc_now(),
            simulated=bool(executions) and all(record.simulated for record in executions),
        )
        self.store.register(workflow_record, event_type="egcf_workflow_completed")
        return {
            "ok": True,
            "status": "COMPLETED",
            "plan_id": plan.object_id,
            "approval_id": approval_id,
            "execution_ids": [record.object_id for record in executions],
            "workflow_execution_id": workflow_record.object_id,
            "outputs": [record.output for record in executions],
            "lifecycle": lifecycle.history,
            "lifecycle_stages": lifecycle.projection(),
        }

    def replay(
        self,
        plan_id: str,
        modifiers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        historical = self.store.get(plan_id)
        if not isinstance(historical, ExecutionPlan):
            raise EGCFError(f"not an execution plan: {plan_id}")
        compiled = self.store.get(historical.compiled_workflow_id)
        if not isinstance(compiled, CompiledWorkflow):
            raise EGCFError("historical plan references an invalid compiled workflow")
        workflow = WorkflowDefinition(
            name=compiled.workflow_id.rsplit("@", 1)[0],
            version=int(compiled.workflow_id.rsplit("@", 1)[1]),
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id=node["node_id"],
                    command_id=node["command_id"],
                    inputs=dict(node["inputs"]),
                    depends_on=list(node["depends_on"]),
                    when=dict(node.get("when", {})),
                    retry_limit=int(node["retry_limit"]),
                    checkpoint=bool(node["checkpoint"]),
                )
                for node in compiled.nodes
            ],
            outputs={},
            description="Recompiled historical EGCF plan",
        )
        context = CommandContext.from_mapping({**compiled.command_context, **(modifiers or {}), "replay": plan_id})
        replayed = self.compiler.compile(workflow, context=context, grant=self.grant)
        plan = self.create_execution_plan(
            replayed,
            prepare_mutations=replayed.capability_level == "C3" and not context.dry_run,
        )
        return {
            "historical_plan_id": historical.object_id,
            "replayed_plan_id": plan.object_id,
            "historical_graph_hash": historical.graph_hash,
            "replayed_graph_hash": replayed.graph_hash,
            "same_graph": historical.graph_hash == replayed.graph_hash,
            "historical_snapshot": historical.source_snapshot_hash,
            "current_snapshot": self.workspace.snapshot_hash(),
            "same_snapshot": historical.source_snapshot_hash == self.workspace.snapshot_hash(),
            "reauthorization_required": replayed.capability_level in {"C3", "C4", "C5"},
        }

    def run_objective(
        self,
        objective: str,
        *,
        inputs: Optional[Dict[str, Any]] = None,
        modifiers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = " ".join(objective.lower().split())
        if "fix" in normalized and "parser" in normalized and "regression" in normalized:
            template_path = Path(__file__).resolve().parents[2] / "workflows" / "v1" / "parser-regression.json"
            payload = json.loads(template_path.read_text(encoding="utf-8"))
            workflow = WorkflowDefinition(
                name=payload["name"],
                version=payload["version"],
                parameters=payload.get("parameters", {}),
                nodes=[WorkflowNode(**node) for node in payload["nodes"]],
                outputs=payload.get("outputs", {}),
                description=payload.get("description", ""),
            )
            context = CommandContext.from_mapping(modifiers)
            compiled = self.compiler.compile(workflow, context=context, grant=self.grant)
            plan = self.create_execution_plan(compiled, prepare_mutations=False)
            return self._projections(compiled, plan, context, Lifecycle("COMPILED"))
        return self.invoke(
            "hrt.interpret",
            {"text": objective, **(inputs or {})},
            modifiers,
        )
