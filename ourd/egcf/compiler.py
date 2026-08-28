from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any, Dict, Iterable, Optional

from ..workspace import Workspace
from .capabilities import CAPABILITY_ORDER, CapabilityResolver
from .context import APPROVAL_ORDER, RISK_ORDER, ROLLBACK_ORDER, CommandContext, narrow_scope
from .errors import CompilationError
from .ids import sha256_json, utc_now
from .models import (
    CapabilityGrant,
    CommandInvocation,
    CompiledWorkflow,
    DecisionRecord,
    InvariantRecord,
    WorkflowDefinition,
    WorkflowNode,
)
from .registry import (
    AlgorithmRegistry,
    CommandRegistry,
    SelectionEngine,
    runtime_qualification_context,
)
from .schemas import validate_json_value
from .store import EGCFStore


def _maximum(values: Iterable[str], order: Dict[str, int], default: str) -> str:
    items = list(values)
    if not items:
        return default
    invalid = [item for item in items if item not in order]
    if invalid:
        raise CompilationError(f"invalid ordered values: {invalid}")
    return max(items, key=order.__getitem__)


class WorkflowCompiler:
    def __init__(
        self,
        store: EGCFStore,
        workspace: Workspace,
        commands: CommandRegistry,
        algorithms: AlgorithmRegistry,
        capabilities: CapabilityResolver,
    ):
        self.store = store
        self.workspace = workspace
        self.commands = commands
        self.algorithms = algorithms
        self.capabilities = capabilities
        self.selector = SelectionEngine(store, algorithms)

    def _compile_node(
        self,
        node: WorkflowNode,
        context: CommandContext,
        grant: CapabilityGrant,
    ) -> Dict[str, Any]:
        definition = self.commands.resolve(node.command_id)
        validate_json_value(definition.input_schema, node.inputs)
        context_scope = (
            list(grant.scope)
            if context.scope in (["**"], ["*"], ["."])
            else narrow_scope(grant.scope, context.scope)
        )
        node_scope = node.inputs.get("scope", context_scope)
        effective_scope = narrow_scope(context_scope, node_scope)
        command_capabilities = list(definition.capability_query.get("facets", []))
        declared_level = str(definition.capability_query.get("level", "C0"))
        required_level = self.capabilities.requirement_level(command_capabilities, declared_level)
        if required_level in {"C4", "C5"}:
            raise CompilationError("C4 and C5 executors are fail-closed until explicitly qualified")
        selection = self.selector.select(
            definition.command_id,
            context={
                **runtime_qualification_context(),
                "workspace_snapshot": self.workspace.snapshot_hash(),
                "scope": effective_scope,
                "inputs": node.inputs,
                "capability_ceiling": grant.capability_ceiling,
                "allowed_capabilities": sorted(grant.capabilities),
                "evidence_ids": sorted(context.evidence),
                "budget": context.budget.to_dict(),
            },
            capability_ceiling=grant.capability_ceiling,
            allowed_capabilities=grant.capabilities,
        )
        algorithm = self.algorithms.resolve(selection.selected_algorithm_id)
        requirements = sorted(set(command_capabilities + algorithm.capability_requirements))
        required_level = self.capabilities.requirement_level(requirements, required_level)
        capability_receipt = self.capabilities.check(
            grant,
            required_level=required_level,
            required_capabilities=requirements,
        )
        risk = _maximum([context.risk, definition.risk_policy, algorithm.risk_floor], RISK_ORDER, "L0")
        rollback = _maximum(
            [context.rollback, definition.rollback_policy, algorithm.rollback_class],
            ROLLBACK_ORDER,
            "none",
        )
        approval = _maximum(
            [context.approval, definition.approval_policy],
            APPROVAL_ORDER,
            "automatic",
        )
        evidence = sorted(
            set(context.evidence + definition.evidence_requirements + algorithm.evidence_requirements)
        )
        return {
            "node_id": node.node_id,
            "command_id": definition.command_id,
            "command_definition_id": definition.object_id,
            "algorithm_id": algorithm.algorithm_id,
            "algorithm_definition_id": algorithm.object_id,
            "algorithm_digest": algorithm.implementation_digest,
            "selection_id": selection.object_id,
            "inputs": node.inputs,
            "inputs_hash": sha256_json(node.inputs),
            "depends_on": list(node.depends_on),
            "scope": effective_scope,
            "capability_level": required_level,
            "capability_requirements": requirements,
            "capability_receipt": capability_receipt,
            "risk": risk,
            "rollback_class": rollback,
            "approval_policy": approval,
            "evidence_requirements": evidence,
            "retry_limit": node.retry_limit,
            "checkpoint": node.checkpoint,
            "when": dict(node.when),
        }

    @staticmethod
    def _references(value: Any) -> list[Dict[str, Any]]:
        references: list[Dict[str, Any]] = []
        if isinstance(value, dict):
            if "$from" in value:
                references.append(value)
            for child in value.values():
                references.extend(WorkflowCompiler._references(child))
        elif isinstance(value, list):
            for child in value:
                references.extend(WorkflowCompiler._references(child))
        return references

    def _validate_references(
        self,
        workflow: WorkflowDefinition,
        edges: list[Dict[str, str]],
    ) -> None:
        node_ids = {node.node_id for node in workflow.nodes}
        for node in workflow.nodes:
            nested_workflow_command = node.command_id.split("@", 1)[0] in {
                "workflow.create",
                "workflow.compile",
                "algorithm.compose",
            }
            reference_source = {"when": node.when}
            if not nested_workflow_command:
                reference_source["inputs"] = node.inputs
            for reference in self._references(reference_source):
                unknown = sorted(set(reference) - {"$from", "path", "default"})
                if unknown:
                    raise CompilationError(f"reference has unknown fields: {unknown}")
                source = reference.get("$from")
                if not isinstance(source, str) or source not in node_ids:
                    raise CompilationError(f"reference source does not exist: {source!r}")
                if source == node.node_id or not self._reachable(source, node.node_id, edges):
                    raise CompilationError(
                        f"node {node.node_id} references non-dependent output {source}"
                    )
                path = reference.get("path", [])
                if not isinstance(path, list) or not all(isinstance(item, (str, int)) for item in path):
                    raise CompilationError("reference path must be an array of strings or integers")
        for reference in self._references(workflow.outputs):
            source = reference.get("$from")
            if not isinstance(source, str) or source not in node_ids:
                raise CompilationError(f"workflow output reference does not exist: {source!r}")

    def _governance_conflicts(self) -> list[str]:
        conflicts: list[str] = []
        active_invariants = set(self.store.active_ids("invariant"))
        invariants = [
            item
            for item in self.store.find("invariant")
            if isinstance(item, InvariantRecord)
            and item.object_id in active_invariants
            and item.status in {"REGISTERED", "VALIDATED"}
        ]
        for index, left in enumerate(invariants):
            for right in invariants[index + 1 :]:
                if (
                    left.name.strip().lower() == right.name.strip().lower()
                    and left.statement.strip() != right.statement.strip()
                    and set(left.scope).intersection(right.scope)
                ):
                    conflicts.append(f"active invariant conflict: {left.object_id} vs {right.object_id}")
        active_decisions = set(self.store.active_ids("decision"))
        decisions = [
            item
            for item in self.store.find("decision")
            if isinstance(item, DecisionRecord)
            and item.object_id in active_decisions
            and item.status == "ACTIVE"
        ]
        for index, left in enumerate(decisions):
            for right in decisions[index + 1 :]:
                if (
                    left.question.strip().lower() == right.question.strip().lower()
                    and left.choice.strip().lower() != right.choice.strip().lower()
                    and set(left.scope).intersection(right.scope)
                ):
                    conflicts.append(f"active decision conflict: {left.object_id} vs {right.object_id}")
        return conflicts

    @staticmethod
    def _topological_order(nodes: list[WorkflowNode]) -> tuple[list[str], list[Dict[str, str]]]:
        by_id = {node.node_id: node for node in nodes}
        if len(by_id) != len(nodes):
            raise CompilationError("workflow node IDs must be unique")
        missing = sorted(
            dependency
            for node in nodes
            for dependency in node.depends_on
            if dependency not in by_id
        )
        if missing:
            raise CompilationError(f"workflow dependencies do not exist: {missing}")
        incoming = {node.node_id: len(set(node.depends_on)) for node in nodes}
        outgoing: Dict[str, list[str]] = defaultdict(list)
        edges: list[Dict[str, str]] = []
        for node in nodes:
            for dependency in sorted(set(node.depends_on)):
                outgoing[dependency].append(node.node_id)
                edges.append({"from": dependency, "to": node.node_id})
        ready = deque(sorted(node_id for node_id, count in incoming.items() if count == 0))
        order: list[str] = []
        while ready:
            node_id = ready.popleft()
            order.append(node_id)
            for target in sorted(outgoing[node_id]):
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)
        if len(order) != len(nodes):
            raise CompilationError("workflow graph contains a cycle")
        return order, sorted(edges, key=lambda item: (item["from"], item["to"]))

    @staticmethod
    def _reachable(source: str, target: str, edges: list[Dict[str, str]]) -> bool:
        outgoing: Dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            outgoing[edge["from"]].append(edge["to"])
        frontier = [source]
        visited = set()
        while frontier:
            current = frontier.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            frontier.extend(outgoing[current])
        return False

    def _target_conflicts(self, nodes: list[Dict[str, Any]], edges: list[Dict[str, str]]) -> list[str]:
        def targets(node: Dict[str, Any]) -> set[str]:
            explicit = set(node["inputs"].get("targets", []))
            changed = {
                str(item.get("path", ""))
                for item in node["inputs"].get("changes", [])
                if item.get("path")
            }
            return explicit.union(changed)

        conflicts: list[str] = []
        for index, left in enumerate(nodes):
            left_targets = targets(left)
            if not left_targets:
                continue
            for right in nodes[index + 1 :]:
                overlap = sorted(left_targets.intersection(targets(right)))
                if not overlap:
                    continue
                serialized = self._reachable(left["node_id"], right["node_id"], edges) or self._reachable(
                    right["node_id"], left["node_id"], edges
                )
                if not serialized:
                    conflicts.append(
                        f"mutation targets {overlap} overlap between {left['node_id']} and {right['node_id']}"
                    )
        return conflicts

    def compile(
        self,
        workflow: WorkflowDefinition,
        *,
        context: CommandContext,
        grant: CapabilityGrant,
    ) -> CompiledWorkflow:
        order, edges = self._topological_order(workflow.nodes)
        self._validate_references(workflow, edges)
        if context.budget.actions is not None and len(workflow.nodes) > context.budget.actions:
            raise CompilationError("workflow node count exceeds action budget")
        if context.budget.retries is not None:
            retries = sum(node.retry_limit for node in workflow.nodes)
            if retries > context.budget.retries:
                raise CompilationError("workflow retry count exceeds retry budget")
        compiled_by_id = {
            node.node_id: self._compile_node(node, context, grant) for node in workflow.nodes
        }
        compiled_nodes = [compiled_by_id[node_id] for node_id in order]
        for node in compiled_nodes:
            if node["capability_level"] in {"C3", "C4", "C5"} and node["retry_limit"]:
                raise CompilationError("mutating nodes cannot retry without a new candidate and approval")
            if node["capability_level"] in {"C3", "C4", "C5"} and node["checkpoint"]:
                raise CompilationError("checkpoints must occur before, not after, mutating nodes")
            if node["capability_level"] in {"C3", "C4", "C5"} and node["rollback_class"] == "none":
                raise CompilationError(f"mutating node {node['node_id']} lacks rollback")
        unresolved = self._target_conflicts(compiled_nodes, edges)
        unresolved.extend(self._governance_conflicts())
        if context.strict and unresolved:
            raise CompilationError(f"strict compilation has unresolved conflicts: {unresolved}")
        capability_level = _maximum(
            [node["capability_level"] for node in compiled_nodes], CAPABILITY_ORDER, "C0"
        )
        capability_requirements = sorted(
            {capability for node in compiled_nodes for capability in node["capability_requirements"]}
        )
        self.capabilities.check(
            grant,
            required_level=capability_level,
            required_capabilities=capability_requirements,
        )
        risk = _maximum([node["risk"] for node in compiled_nodes], RISK_ORDER, "L0")
        approval_policy = _maximum(
            [node["approval_policy"] for node in compiled_nodes], APPROVAL_ORDER, "automatic"
        )
        evidence_requirements = sorted(
            {item for node in compiled_nodes for item in node["evidence_requirements"]}
        )
        rollback_graph = {
            node["node_id"]: {
                "class": node["rollback_class"],
                "depends_on": list(node["depends_on"]),
            }
            for node in reversed(compiled_nodes)
            if node["capability_level"] in {"C3", "C4", "C5"}
        }
        material = {
            "workflow_id": workflow.workflow_id,
            "source_snapshot_hash": self.workspace.snapshot_hash(),
            "command_context": context.to_dict(),
            "nodes": compiled_nodes,
            "edges": edges,
            "execution_order": order,
            "capability_level": capability_level,
            "capability_requirements": capability_requirements,
            "risk": risk,
            "evidence_requirements": evidence_requirements,
            "approval_policy": approval_policy,
            "budget": context.budget.to_dict(),
            "rollback_graph": rollback_graph,
            "unresolved": unresolved,
            "created_at": utc_now(),
        }
        graph_material = {key: value for key, value in material.items() if key != "created_at"}
        graph_material["command_context"] = {
            key: material["command_context"].get(key)
            for key in (
                "scope",
                "evidence",
                "approval",
                "risk",
                "rollback",
                "budget",
                "timeout",
                "strict",
                "simulate",
            )
        }
        graph_material["nodes"] = [
            {key: value for key, value in node.items() if key != "selection_id"}
            for node in compiled_nodes
        ]
        graph_hash = sha256_json(graph_material)
        compiled = CompiledWorkflow(**material, graph_hash=graph_hash)
        self.store.register(compiled)
        return compiled

    def compile_invocation(
        self,
        invocation: CommandInvocation,
        *,
        context: Optional[CommandContext],
        grant: CapabilityGrant,
    ) -> CompiledWorkflow:
        effective_context = context or CommandContext.from_mapping(invocation.modifiers)
        definition = self.commands.resolve(invocation.command_id)
        if not invocation.command_definition_id:
            raise CompilationError("command invocation must bind an exact command definition ID")
        if invocation.command_definition_id != definition.object_id:
            raise CompilationError("command invocation definition binding is stale or mismatched")
        workflow = WorkflowDefinition(
            name=f"invocation-{invocation.object_id.split(':')[-1][:16]}",
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id="command",
                    command_id=invocation.command_id,
                    inputs=invocation.inputs,
                )
            ],
            outputs={"result": "command.output"},
            description="One-node semantic command workflow",
        )
        self.store.register(invocation)
        self.store.register(workflow)
        return self.compile(workflow, context=effective_context, grant=grant)
