from __future__ import annotations

import ast
import itertools
import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable

from ..persistence import redact
from ..workspace import Workspace
from .assurance import AssuranceManager
from .capabilities import CapabilityResolver
from .compiler import WorkflowCompiler
from .context import CommandContext
from .decisions import DecisionManager
from .domains import built_in_domain_packs
from .errors import EGCFError
from .evidence import EvidenceManager
from .experiments import ExperimentDesigner
from .ids import sha256_json, utc_now
from .ieps import IEPS
from .invariants import InvariantManager
from .models import (
    AlgorithmDefinition,
    ApprovalRecord,
    CapabilityGrant,
    ClaimRecord,
    CommandDefinition,
    DecisionRecord,
    ExecutionPlan,
    ExecutionRecord,
    FailureRecord,
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
from .simulation import SimulationEngine
from .store import EGCFStore


class SemanticHandlers:
    def __init__(
        self,
        *,
        store: EGCFStore,
        workspace: Workspace,
        commands: CommandRegistry,
        algorithms: AlgorithmRegistry,
        capabilities: CapabilityResolver,
        compiler: WorkflowCompiler,
    ):
        self.store = store
        self.workspace = workspace
        self.commands = commands
        self.algorithms = algorithms
        self.capabilities = capabilities
        self.compiler = compiler
        self.selector = SelectionEngine(store, algorithms)
        self.evidence = EvidenceManager(store)
        self.ieps = IEPS(self.evidence)
        self.invariants = InvariantManager(store)
        self.decisions = DecisionManager(store)
        self.assurance = AssuranceManager(
            store, self.evidence, self.invariants, self.decisions
        )
        self.experiments = ExperimentDesigner()
        self.simulation = SimulationEngine()
        self.domain_packs = built_in_domain_packs()

    def execute(
        self,
        command_id: str,
        inputs: Dict[str, Any],
        *,
        context: CommandContext,
        grant: CapabilityGrant,
        approval: Dict[str, Any] | None = None,
        approval_id: str = "",
    ) -> Dict[str, Any]:
        base = command_id.split("@", 1)[0]
        namespace, verb = base.split(".", 1)
        method = getattr(self, f"_{namespace}_{verb.replace('-', '_')}", None)
        if method is not None:
            result = method(
                inputs,
                context=context,
                grant=grant,
                approval=dict(approval or {}),
                approval_id=approval_id,
            )
        else:
            group_method = getattr(self, f"_{namespace}", None)
            if group_method is not None:
                result = group_method(
                    verb,
                    inputs,
                    context=context,
                    grant=grant,
                    approval=dict(approval or {}),
                    approval_id=approval_id,
                )
            else:
                result = self._generic(namespace, verb, inputs, context=context)
        return {
            "ok": True,
            "command_id": command_id,
            "read_only": namespace not in {"eon"},
            "result": redact(result),
            "provenance": {
                "source_snapshot_hash": self.workspace.snapshot_hash(),
                "handler": f"builtin:{namespace}.{verb}",
                "recorded_at": utc_now(),
            },
        }

    @staticmethod
    def _generic(
        namespace: str,
        verb: str,
        inputs: Dict[str, Any],
        *,
        context: CommandContext,
    ) -> Dict[str, Any]:
        return {
            "status": "READ_ONLY_RESULT",
            "operation": f"{namespace}.{verb}",
            "inputs": inputs,
            "assumptions": list(inputs.get("assumptions", [])),
            "limitations": [
                "v1 generic semantic adapter",
                "no external or workspace mutation executor invoked",
            ],
            "strict": context.strict,
        }

    def _capability_list(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {
            "capabilities": [
                {"object_id": spec.object_id, **spec.to_dict()} for spec in self.capabilities.specs()
            ]
        }

    def _capability_describe(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        spec = self.capabilities.describe(str(inputs["name"]))
        return {"object_id": spec.object_id, **spec.to_dict()}

    def _capability_graph(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        specs = self.capabilities.specs()
        return {
            "nodes": [
                *[{"id": level, "type": "level"} for level in ("C0", "C1", "C2", "C3", "C4", "C5")],
                *[{"id": spec.name, "type": "capability", "level": spec.level} for spec in specs],
            ],
            "edges": [{"from": spec.level, "to": spec.name, "relation": "classifies"} for spec in specs],
        }

    def _capability_check(
        self,
        inputs: Dict[str, Any],
        *,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        return self.capabilities.check(
            grant,
            required_level=str(inputs.get("level", "C0")),
            required_capabilities=list(inputs.get("capabilities", [])),
        )

    def _capability_request(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.capabilities.request(
            str(inputs.get("subject", "current task")),
            inputs.get("capabilities", []),
            inputs.get("scope", ["**"]),
            str(inputs.get("justification", "")),
        )

    def _capability_audit(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {
            "grants": self.store.list("capability-grant"),
            "supersedence": self.store.list("supersedence"),
            "event_head": self.store.events.head,
        }

    def _capability_explain(
        self,
        inputs: Dict[str, Any],
        *,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        required = list(inputs.get("capabilities", []))
        level = self.capabilities.requirement_level(required, str(inputs.get("level", "C0")))
        try:
            check = self.capabilities.check(
                grant, required_level=level, required_capabilities=required
            )
        except Exception as exc:
            return {"allowed": False, "required_level": level, "reason": str(exc)}
        return check

    @staticmethod
    def _normalise_eon_changes(changes: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        normalised = []
        for index, raw in enumerate(changes):
            change = dict(raw)
            operation = str(change.get("type", change.get("operation", "")))
            if operation not in {"write", "replace"}:
                raise EGCFError(f"EON change {index} has unsupported operation {operation!r}")
            path = str(change.get("path", ""))
            if not path:
                raise EGCFError(f"EON change {index} requires a path")
            item: Dict[str, Any] = {"type": operation, "path": path}
            if operation == "write":
                if "content" not in change:
                    raise EGCFError(f"EON write change {index} requires content")
                item["content"] = str(change["content"])
            else:
                if "old" not in change or "new" not in change:
                    raise EGCFError(f"EON replace change {index} requires old and new")
                item.update(
                    {
                        "old": str(change["old"]),
                        "new": str(change["new"]),
                        "count": int(change.get("count", 1)),
                    }
                )
            normalised.append(item)
        return normalised

    def _eon_draft(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        changes = self._normalise_eon_changes(inputs.get("changes", [])) if inputs.get("changes") else []
        return {
            "status": "DRAFT",
            "summary": str(inputs.get("summary", "")),
            "changes": changes,
            "preconditions": list(inputs.get("preconditions", [])),
            "postconditions": list(inputs.get("postconditions", [])),
            "invariants": list(inputs.get("invariants", [])),
            "evidence": list(inputs.get("evidence", [])),
            "risk": str(inputs.get("risk", "L1")),
            "rollback": str(inputs.get("rollback", "exact")),
            "authority": False,
        }

    def _eon_validate(
        self,
        inputs: Dict[str, Any],
        *,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        changes = self._normalise_eon_changes(inputs.get("changes", []))
        if not changes:
            raise EGCFError("EON validation requires at least one change")
        targets = []
        for change in changes:
            target = self.workspace.require_scope(
                change["path"],
                grant.scope,
                grant.resources.get("forbidden_paths", []),
            )
            targets.append(target)
        duplicates = sorted(path for path, count in Counter(targets).items() if count > 1)
        if duplicates:
            raise EGCFError(f"EON draft has duplicate targets: {duplicates}")
        return {
            "status": "VALID",
            "changes": changes,
            "targets": targets,
            "capability_required": "C3",
            "approval_required": "human",
            "rollback_required": "exact",
        }

    def _eon_compile(
        self,
        inputs: Dict[str, Any],
        *,
        context: CommandContext,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        validated = self._eon_validate(inputs, grant=grant)
        workflow = WorkflowDefinition(
            name=str(inputs.get("name", "eon-action")),
            version=1,
            parameters={},
            nodes=[
                WorkflowNode(
                    node_id="execute",
                    command_id="eon.execute@1",
                    inputs={**inputs, "changes": validated["changes"]},
                )
            ],
            outputs={"result": {"$from": "execute"}},
            description=str(inputs.get("summary", "Compiled EON action")),
        )
        workflow_id = self.store.register(workflow)
        compiled = self.compiler.compile(workflow, context=context, grant=grant)
        return {
            "workflow_definition_id": workflow_id,
            "compiled_workflow_id": compiled.object_id,
            "graph_hash": compiled.graph_hash,
            "approval_policy": compiled.approval_policy,
            "rollback_graph": compiled.rollback_graph,
        }

    def _eon_simulate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        changes = self._normalise_eon_changes(inputs.get("changes", []))
        return {
            "simulated": True,
            "changes": changes,
            "targets": [change["path"] for change in changes],
            "workspace_mutation": False,
            "fidelity_limits": [
                "candidate bytes are not staged",
                "repository-native verification is not executed",
            ],
        }

    def _eon_compare(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        current = self._normalise_eon_changes(inputs.get("current", {}).get("changes", []))
        other = self._normalise_eon_changes(inputs.get("other", {}).get("changes", []))
        current_by_path = {item["path"]: item for item in current}
        other_by_path = {item["path"]: item for item in other}
        paths = sorted(set(current_by_path).union(other_by_path))
        return {
            "same": current == other,
            "differences": [
                {
                    "path": path,
                    "current": current_by_path.get(path),
                    "other": other_by_path.get(path),
                }
                for path in paths
                if current_by_path.get(path) != other_by_path.get(path)
            ],
        }

    def _algorithm_register(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        definition = AlgorithmDefinition(**inputs["definition"])
        if definition.status not in {"PROPOSED", "CANDIDATE"}:
            raise EGCFError("algorithm register may create only PROPOSED or CANDIDATE records")
        object_id = self.algorithms.register(definition)
        return {"algorithm_definition_id": object_id, "algorithm_id": definition.algorithm_id}

    def _algorithm_search(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        command_id = self.commands.resolve(str(inputs["command_id"])).command_id
        return {
            "command_id": command_id,
            "algorithms": [
                {"object_id": algorithm.object_id, **algorithm.to_dict(), "algorithm_id": algorithm.algorithm_id}
                for algorithm in self.algorithms.search(command_id)
            ],
        }

    def _algorithm_compare(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        algorithms = [self.algorithms.resolve(identifier) for identifier in inputs.get("algorithm_ids", [])]
        return {
            "algorithms": [
                {
                    "algorithm_id": algorithm.algorithm_id,
                    "status": algorithm.status,
                    "capability_level": algorithm.capability_level,
                    "risk_floor": algorithm.risk_floor,
                    "rollback_class": algorithm.rollback_class,
                    "known_failures": algorithm.known_failures,
                    "qualification_count": len(self.algorithms.qualifications(algorithm)),
                }
                for algorithm in algorithms
            ]
        }

    def _algorithm_qualify(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        qualification_id = self.algorithms.qualify(
            str(inputs["algorithm_id"]),
            context=dict(inputs.get("context", {})),
            evidence_ids=inputs.get("evidence_ids", []),
            tests=inputs.get("tests", []),
            benchmarks=inputs.get("benchmarks", []),
            known_failures=inputs.get("known_failures", []),
            qualified_by=str(inputs.get("qualified_by", "external qualifier")),
            expires_at=str(inputs.get("expires_at", "")),
        )
        return {"qualification_id": qualification_id}

    def _algorithm_select(
        self,
        inputs: Dict[str, Any],
        *,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        command = self.commands.resolve(str(inputs["command_id"]))
        decision = self.selector.select(
            command.command_id,
            context={
                **runtime_qualification_context(),
                **dict(inputs.get("context", {})),
                "capability_ceiling": grant.capability_ceiling,
                "allowed_capabilities": sorted(grant.capabilities),
                "evidence_ids": sorted(inputs.get("evidence_ids", [])),
                "budget": dict(inputs.get("budget", {})),
            },
            capability_ceiling=grant.capability_ceiling,
            allowed_capabilities=grant.capabilities,
            invariant_names=inputs.get("invariants", []),
            budget=inputs.get("budget", {}),
        )
        return {"selection_id": decision.object_id, **decision.to_dict()}

    def _algorithm_explain(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        selection = self.store.get(str(inputs["selection_id"]))
        return {"selection_id": selection.object_id, **selection.to_dict()}

    def _algorithm_benchmark(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        samples = [float(value) for value in inputs.get("samples", [])]
        return {
            "algorithm_id": str(inputs.get("algorithm_id", "")),
            "sample_count": len(samples),
            "minimum": min(samples) if samples else None,
            "maximum": max(samples) if samples else None,
            "mean": sum(samples) / len(samples) if samples else None,
            "unit": str(inputs.get("unit", "seconds")),
        }

    def _algorithm_compose(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        workflow = self._workflow_from_inputs(inputs)
        workflow_id = self.store.register(workflow)
        return {
            "workflow_definition_id": workflow_id,
            "workflow_id": workflow.workflow_id,
            "status": "CANDIDATE_COMPOSITION",
            "qualification_required": True,
        }

    def _algorithm_evolve(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        current = self.algorithms.resolve(str(inputs["algorithm_id"]))
        updates = dict(inputs.get("updates", {}))
        allowed_updates = {
            "applicability",
            "known_failures",
            "evidence_requirements",
            "qualification_policy",
            "provenance",
            "owner",
        }
        unknown = sorted(set(updates) - allowed_updates)
        if unknown:
            raise EGCFError(f"algorithm evolution cannot alter executable fields: {unknown}")
        updates["version"] = current.version + 1
        updates["status"] = "CANDIDATE"
        evolved = replace(current, **updates)
        evolved_id = self.store.register(evolved)
        return {
            "algorithm_definition_id": evolved_id,
            "algorithm_id": evolved.algorithm_id,
            "supersedes_after_qualification": current.object_id,
        }

    def _algorithm_retire(
        self,
        inputs: Dict[str, Any],
        *,
        approval: Dict[str, Any],
        approval_id: str,
        **_: Any,
    ) -> Dict[str, Any]:
        if not approval.get("human") or not approval_id:
            raise EGCFError("algorithm retirement requires exact human approval")
        return {
            "retired_definition_id": self.algorithms.retire(
                str(inputs["algorithm_id"]), authority=approval_id
            )
        }

    def _evidence_collect(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        reported_producer = str(inputs.get("producer", "external"))
        producer = reported_producer
        if producer.startswith(("deterministic-", "human-")):
            producer = f"reported-{producer}"
        environment = dict(inputs.get("environment", {}))
        environment["reported_source_snapshot_hash"] = str(
            inputs.get("source_snapshot_hash", "")
        )
        artifact_id = self.evidence.collect(
            subject_id=str(inputs["subject_id"]),
            content=inputs.get("content"),
            category=str(inputs.get("category", "observation")),
            producer=producer,
            method="reported",
            source_snapshot_hash=self.workspace.snapshot_hash(),
            target=str(inputs.get("target", "")),
            oracle=str(inputs.get("oracle", "")),
            environment=environment,
            command_id=str(inputs.get("command_id", "")),
            algorithm_id=str(inputs.get("algorithm_id", "")),
            claim_ids=inputs.get("claim_ids", []),
            requirement_ids=inputs.get("requirement_ids", []),
            success=inputs.get("success"),
            limitations=inputs.get("limitations", []),
            independence_group=str(inputs.get("independence_group", "")),
            simulated=bool(inputs.get("simulated", False)),
            path=str(inputs.get("path", "")),
        )
        return {"evidence_id": artifact_id}

    def _evidence_classify(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        content = str(inputs.get("content", "")).lower()
        category = "observation"
        for candidate, markers in {
            "counterexample": ("counterexample", "fails for", "reproducer"),
            "test": ("test", "passed", "failed"),
            "boundary": ("scope", "boundary", "permission"),
            "invariant": ("invariant", "preserve", "unchanged"),
        }.items():
            if any(marker in content for marker in markers):
                category = candidate
                break
        return {"category": category, "proposal_only": True}

    def _evidence_compare(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        artifacts = [self.store.get(identifier) for identifier in inputs.get("evidence_ids", [])]
        return {
            "items": [
                {
                    "id": artifact.object_id,
                    "sha256": getattr(artifact, "sha256", ""),
                    "success": getattr(artifact, "success", None),
                    "category": getattr(artifact, "category", ""),
                    "simulated": getattr(artifact, "simulated", False),
                }
                for artifact in artifacts
            ]
        }

    def _evidence_graph(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.evidence.graph(str(inputs["subject_id"]))

    def _evidence_export(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        subject_id = str(inputs["subject_id"])
        return {
            "subject_id": subject_id,
            "requirements": [
                {"id": identifier, **record.to_dict()}
                for identifier, record in self.evidence.requirements(subject_id)
            ],
            "evidence": [
                {"id": record.object_id, **record.to_dict()}
                for record in self.evidence.artifacts(subject_id)
            ],
        }

    def _evidence_confidence(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        assessment = self.evidence.confidence(
            str(inputs["subject_id"]), str(inputs.get("policy", "egcf-default-v1"))
        )
        return {"confidence_id": assessment.object_id, **assessment.to_dict()}

    def _evidence_conflicts(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"conflicts": self.evidence.conflicts(str(inputs["subject_id"]))}

    def _evidence_history(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        subject_id = str(inputs["subject_id"])
        return {
            "evidence": [
                {"id": record.object_id, **record.to_dict()}
                for record in self.evidence.artifacts(subject_id)
            ]
        }

    def _ieps_generate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        requirements = []
        for item in inputs.get("requirements", []):
            requirements.append(
                self.ieps.oracle(
                    str(inputs["subject_id"]),
                    str(item["name"]),
                    str(item["category"]),
                    str(item.get("oracle", "")),
                    mandatory=bool(item.get("mandatory", True)),
                    freshness_seconds=int(item.get("freshness_seconds", 0)),
                    independence_group=str(item.get("independence_group", item["name"])),
                )
            )
        return {"requirement_ids": requirements, "status": "CANDIDATE_EVIDENCE_PLAN"}

    def _ieps_coverage(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.coverage(str(inputs["subject_id"]))

    def _ieps_oracle(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        requirement_id = self.ieps.oracle(
            str(inputs["subject_id"]),
            str(inputs["name"]),
            str(inputs["category"]),
            str(inputs.get("oracle", "")),
            mandatory=bool(inputs.get("mandatory", True)),
            freshness_seconds=int(inputs.get("freshness_seconds", 0)),
            independence_group=str(inputs.get("independence_group", inputs["name"])),
        )
        return {"requirement_id": requirement_id}

    def _ieps_counterexamples(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.counterexamples(inputs.get("candidates", []), inputs.get("predicate_results", []))

    def _ieps_uniqueness(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.uniqueness(str(inputs["subject_id"]))

    def _ieps_mutation(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.mutation(inputs.get("mutations", []))

    def _ieps_shrink(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.shrink(inputs.get("sequence", []), inputs.get("required_items", []))

    def _ieps_qualify(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.qualify(str(inputs["subject_id"]))

    def _ieps_gate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.ieps.gate(str(inputs["subject_id"]))

    def _invariant_discover(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        identifiers = self.invariants.discover(
            inputs.get("statements", []),
            inputs.get("scope", ["**"]),
            str(inputs.get("source", "model proposal")),
        )
        return {"candidate_invariant_ids": identifiers, "registered": False}

    def _invariant_register(
        self,
        inputs: Dict[str, Any],
        *,
        approval: Dict[str, Any],
        approval_id: str,
        **_: Any,
    ) -> Dict[str, Any]:
        if not approval.get("human") or not approval_id:
            raise EGCFError("invariant registration requires exact human approval")
        identifier = self.invariants.register(
            name=str(inputs["name"]),
            statement=str(inputs["statement"]),
            scope=inputs.get("scope", ["**"]),
            validator=dict(inputs["validator"]),
            evidence_ids=inputs.get("evidence_ids", []),
            falsifier=str(inputs["falsifier"]),
            authority=approval_id,
            counterexamples=inputs.get("counterexamples", []),
        )
        return {"invariant_id": identifier}

    def _invariant_validate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        identifier = self.invariants.validate(
            str(inputs["invariant_id"]), bool(inputs["success"]), inputs.get("evidence_ids", [])
        )
        return {"invariant_id": identifier}

    def _invariant_compare(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        records = [self.store.get(identifier) for identifier in inputs.get("invariant_ids", [])]
        return {"invariants": [{"id": record.object_id, **record.to_dict()} for record in records]}

    def _invariant_conflicts(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"conflicts": self.invariants.conflicts()}

    def _invariant_supersede(
        self,
        inputs: Dict[str, Any],
        *,
        approval: Dict[str, Any],
        approval_id: str,
        **_: Any,
    ) -> Dict[str, Any]:
        if not approval.get("human") or not approval_id:
            raise EGCFError("invariant supersedence requires exact human approval")
        record = InvariantRecord(**inputs["new_record"])
        identifier = self.invariants.supersede(
            str(inputs["old_id"]), record, str(inputs["reason"]), approval_id
        )
        return {"invariant_id": identifier}

    def _decision_create(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        if inputs.get("activate"):
            raise EGCFError(
                "decision.create only creates proposals; activation requires an approved decision.supersede transaction"
            )
        identifier = self.decisions.create(
            question=str(inputs["question"]),
            alternatives=inputs.get("alternatives", []),
            choice=str(inputs["choice"]),
            rationale=str(inputs.get("rationale", "")),
            evidence_ids=inputs.get("evidence_ids", []),
            constraints=inputs.get("constraints", []),
            owner=str(inputs.get("owner", "model proposal")),
            scope=inputs.get("scope", ["**"]),
            activate=False,
            authority="",
        )
        return {"decision_id": identifier}

    def _decision_query(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"decisions": self.decisions.query(str(inputs.get("text", "")), inputs.get("scope", []))}

    def _decision_history(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"decisions": [{"id": record.object_id, **record.to_dict()} for record in self.decisions.records()]}

    def _decision_conflicts(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"conflicts": self.decisions.conflicts()}

    def _decision_explain(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        record = self.store.get(str(inputs["decision_id"]))
        return {"decision_id": record.object_id, **record.to_dict()}

    def _decision_supersede(
        self,
        inputs: Dict[str, Any],
        *,
        approval: Dict[str, Any],
        approval_id: str,
        **_: Any,
    ) -> Dict[str, Any]:
        if not approval.get("human") or not approval_id:
            raise EGCFError("decision supersedence requires exact human approval")
        identifier = self.decisions.supersede(
            str(inputs["old_id"]),
            choice=str(inputs["choice"]),
            rationale=str(inputs["rationale"]),
            evidence_ids=inputs.get("evidence_ids", []),
            authority=approval_id,
        )
        return {"decision_id": identifier}

    def compensate(
        self,
        command_id: str,
        inputs: Dict[str, Any],
        execution: Dict[str, Any],
        *,
        authority: str,
    ) -> Dict[str, Any]:
        result = dict(execution.get("result", {}))
        if command_id == "invariant.register@1":
            created = self.store.get(str(result["invariant_id"]))
            if not isinstance(created, InvariantRecord):
                raise EGCFError("registered invariant compensation target is invalid")
            tombstone = replace(
                created,
                status="SUPERSEDED",
                authority=authority,
                created_at=utc_now(),
                supersedes=created.object_id,
            )
            restored_id = self.store.register(tombstone)
            self.store.supersede(created.object_id, restored_id, "compensated invariant registration", authority)
            return {"status": "COMPENSATED", "replacement_id": restored_id}
        if command_id in {"invariant.supersede@1", "decision.supersede@1"}:
            new_id = str(result.get("invariant_id", result.get("decision_id", "")))
            old = self.store.get(str(inputs["old_id"]))
            if isinstance(old, InvariantRecord):
                restored = replace(old, created_at=utc_now(), supersedes=new_id, authority=authority)
            elif isinstance(old, DecisionRecord):
                restored = replace(old, status="ACTIVE", created_at=utc_now(), supersedes=new_id)
            else:
                raise EGCFError("governance compensation source is invalid")
            restored_id = self.store.register(restored)
            self.store.supersede(new_id, restored_id, "compensated governance supersedence", authority)
            return {"status": "COMPENSATED", "replacement_id": restored_id}
        if command_id == "algorithm.retire@1":
            retired_id = str(result["retired_definition_id"])
            supersedences = self.store.find(
                "supersedence",
                lambda item: getattr(item, "new_id", "") == retired_id,
            )
            if not supersedences:
                raise EGCFError("algorithm retirement compensation lineage is missing")
            previous = self.store.get(supersedences[-1].old_id)
            if not isinstance(previous, AlgorithmDefinition):
                raise EGCFError("algorithm retirement compensation source is invalid")
            restored = replace(previous, status="QUALIFIED")
            restored_id = self.store.register(restored)
            self.store.supersede(retired_id, restored_id, "compensated algorithm retirement", authority)
            return {"status": "COMPENSATED", "replacement_id": restored_id}
        return {"status": "NOT_REQUIRED", "workspace_mutation": False}

    def _assurance_generate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        approval_facts: Dict[str, Any] = {
            "satisfied": False,
            "source": "no immutable approval supplied",
        }
        approval_id = str(inputs.get("approval_id", ""))
        if approval_id:
            approval = self.store.get(approval_id)
            if not isinstance(approval, ApprovalRecord) or not approval.human:
                raise EGCFError("assurance approval_id is not an immutable human approval")
            approval_facts = {
                "satisfied": True,
                "approval_id": approval.object_id,
                "plan_id": approval.plan_id,
                "plan_hash": approval.plan_hash,
                "approver": approval.approver,
            }
        elif inputs.get("approval_facts"):
            approval_facts["reported_claim"] = dict(inputs["approval_facts"])
        case = self.assurance.generate(
            str(inputs["subject_id"]),
            str(inputs.get("top_claim", "The subject satisfies its engineering requirements")),
            capability_facts=dict(inputs.get("capability_facts", {})),
            approval_facts=approval_facts,
            rollback_argument=dict(inputs.get("rollback_argument", {})),
            uncertainties=list(inputs.get("uncertainties", [])),
        )
        return {"assurance_case_id": case.object_id, **case.to_dict()}

    def _workflow_from_inputs(self, inputs: Dict[str, Any]) -> WorkflowDefinition:
        nodes = [
            WorkflowNode(
                node_id=str(item["node_id"]),
                command_id=str(item["command_id"]),
                inputs=dict(item.get("inputs", {})),
                depends_on=list(item.get("depends_on", [])),
                when=dict(item.get("when", {})),
                retry_limit=int(item.get("retry_limit", 0)),
                checkpoint=bool(item.get("checkpoint", False)),
            )
            for item in inputs.get("nodes", [])
        ]
        return WorkflowDefinition(
            name=str(inputs.get("name", "workflow")),
            version=int(inputs.get("version", 1)),
            parameters=dict(inputs.get("parameters", {})),
            nodes=nodes,
            outputs=dict(inputs.get("outputs", {})),
            description=str(inputs.get("description", "")),
        )

    def _workflow_create(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        workflow = self._workflow_from_inputs(inputs)
        return {"workflow_definition_id": self.store.register(workflow), "workflow_id": workflow.workflow_id}

    def _workflow_compile(
        self,
        inputs: Dict[str, Any],
        *,
        context: CommandContext,
        grant: CapabilityGrant,
        **_: Any,
    ) -> Dict[str, Any]:
        if "workflow_definition_id" in inputs:
            workflow = self.store.get(str(inputs["workflow_definition_id"]))
            if not isinstance(workflow, WorkflowDefinition):
                raise EGCFError("workflow_definition_id does not reference a workflow")
        else:
            workflow = self._workflow_from_inputs(inputs)
            self.store.register(workflow)
        compiled = self.compiler.compile(workflow, context=context, grant=grant)
        return {"compiled_workflow_id": compiled.object_id, **compiled.to_dict()}

    def _workflow_monitor(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        plan_id = str(inputs.get("plan_id", ""))
        executions = self.store.find(
            "execution", lambda item: getattr(item, "plan_id", "") == plan_id
        )
        return {
            "plan_id": plan_id,
            "executions": [{"id": record.object_id, **record.to_dict()} for record in executions],
        }

    def _workflow_pause(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        plan_id = str(inputs.get("plan_id", ""))
        plan = self.store.get(plan_id)
        if not isinstance(plan, ExecutionPlan):
            raise EGCFError("workflow pause requires an execution plan")
        record = ExecutionRecord(
            plan_id=plan_id,
            node_id="__control__",
            algorithm_id="workflow.control@1",
            executor="egcf-engine",
            inputs_hash=sha256_json(inputs),
            output={"checkpoint": inputs.get("checkpoint", "next")},
            status="PAUSE_REQUESTED",
            usage={"actions": 0},
            evidence_ids=[],
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        control_id = self.store.register(record, event_type="egcf_workflow_pause_requested")
        return {"plan_id": plan_id, "status": "PAUSE_REQUESTED", "control_id": control_id}

    def _workflow_resume(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        plan_id = str(inputs.get("plan_id", ""))
        plan = self.store.get(plan_id)
        if not isinstance(plan, ExecutionPlan):
            raise EGCFError("workflow resume requires an execution plan")
        paused = self.store.find(
            "execution",
            lambda item: isinstance(item, ExecutionRecord)
            and item.plan_id == plan_id
            and item.status == "PAUSED",
        )
        if not paused:
            raise EGCFError("workflow has no persisted paused checkpoint")
        record = ExecutionRecord(
            plan_id=plan_id,
            node_id="__control__",
            algorithm_id="workflow.control@1",
            executor="egcf-engine",
            inputs_hash=sha256_json(inputs),
            output={"paused_execution_id": paused[-1].object_id},
            status="RESUME_REQUESTED",
            usage={"actions": 0},
            evidence_ids=[],
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        control_id = self.store.register(record, event_type="egcf_workflow_resume_requested")
        return {
            "plan_id": plan_id,
            "status": "RESUME_REQUESTED",
            "control_id": control_id,
            "revalidation_required": True,
        }

    def _workflow_replay(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        plan = self.store.get(str(inputs["plan_id"]))
        return {
            "historical_plan_id": plan.object_id,
            "current_snapshot": self.workspace.snapshot_hash(),
            "historical_snapshot": getattr(plan, "source_snapshot_hash", ""),
            "reauthorization_required": True,
            "same_snapshot": getattr(plan, "source_snapshot_hash", "") == self.workspace.snapshot_hash(),
        }

    def _workflow_branch(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        workflow = self.store.get(str(inputs["workflow_definition_id"]))
        if not isinstance(workflow, WorkflowDefinition):
            raise EGCFError("branch source is not a workflow definition")
        branched = replace(
            workflow,
            name=str(inputs.get("name", f"{workflow.name}-branch")),
            version=1,
            description=str(inputs.get("description", workflow.description)),
        )
        return {"workflow_definition_id": self.store.register(branched), "supersedes": ""}

    def _workflow_merge(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        workflows = [self.store.get(identifier) for identifier in inputs.get("workflow_definition_ids", [])]
        if not all(isinstance(item, WorkflowDefinition) for item in workflows):
            raise EGCFError("workflow merge inputs must all be workflow definitions")
        nodes: Dict[str, WorkflowNode] = {}
        conflicts = []
        for workflow in workflows:
            for node in workflow.nodes:
                if node.node_id in nodes and asdict(nodes[node.node_id]) != asdict(node):
                    conflicts.append({"node_id": node.node_id, "variants": [asdict(nodes[node.node_id]), asdict(node)]})
                else:
                    nodes[node.node_id] = node
        if conflicts:
            return {"status": "CONFLICTED", "conflicts": conflicts, "merged": False}
        merged = WorkflowDefinition(
            name=str(inputs.get("name", "merged-workflow")),
            version=1,
            parameters={},
            nodes=list(nodes.values()),
            outputs={},
            description="Merged workflow with provenance-preserved inputs",
        )
        return {"status": "MERGED", "workflow_definition_id": self.store.register(merged), "conflicts": []}

    def _experiment(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        parameters = dict(inputs.get("parameters", {}))
        if verb == "factorial":
            return {"design": self.experiments.factorial(parameters)}
        if verb == "ofat":
            return {"design": self.experiments.ofat(dict(inputs.get("baseline", {})), parameters)}
        if verb == "covering":
            design = self.experiments.covering(parameters, int(inputs.get("strength", 2)))
            return {"design": design, "runs": len(design), "strength": 2}
        if verb == "analyse":
            return self.experiments.analyse(inputs.get("results", []), str(inputs.get("outcome", "outcome")))
        if verb == "repeat":
            return {"design": list(inputs.get("design", [])) * max(1, int(inputs.get("repeats", 1)))}
        if verb == "compare":
            return {"designs": inputs.get("designs", []), "comparison": "explicit result data required"}
        return {
            "design_kind": verb,
            "parameters": parameters,
            "baseline": inputs.get("baseline", {}),
            "status": "DESIGNED",
        }

    def _simulate_migration(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.simulation.migration(dict(inputs.get("before", {})), inputs.get("operations", []))

    def _simulate_rollback(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.simulation.rollback(dict(inputs["simulation"]))

    def _cfel_classify(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        observed = str(inputs.get("observed", ""))
        normalized = observed.lower()
        categories = []
        for category, markers in {
            "authority": ("permission", "authority", "forbidden", "denied"),
            "scope": ("scope", "path", "escape", "target"),
            "evidence": ("evidence", "oracle", "coverage", "confidence"),
            "algorithm": ("algorithm", "qualification", "selection"),
            "execution": ("return code", "exception", "timeout", "crash"),
            "rollback": ("rollback", "restore", "compensat"),
            "drift": ("stale", "drift", "snapshot", "hash mismatch"),
        }.items():
            if any(marker in normalized for marker in markers):
                categories.append(category)
        if not categories:
            categories = ["unknown"]
        record = FailureRecord(
            subject_id=str(inputs.get("subject_id", "")),
            expected=str(inputs.get("expected", "")),
            observed=observed,
            active_dimension=str(inputs.get("active_dimension", categories[0])),
            frozen_dimensions=list(inputs.get("frozen_dimensions", [])),
            evidence_ids=list(inputs.get("evidence_ids", [])),
            retry_count=int(inputs.get("retry_count", 0)),
            status="CLASSIFIED",
            created_at=utc_now(),
        )
        failure_id = self.store.register(record)
        return {"failure_id": failure_id, "categories": categories, "proposal_only": False}

    def _cfel(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        if verb == "observe":
            return self._cfel_classify(inputs)
        failures = self.store.list("failure")
        if verb == "compare":
            return {"failures": failures}
        if verb == "diagnose":
            return {"hypotheses": inputs.get("hypotheses", []), "failures": failures, "one_active_dimension": True}
        if verb == "recover":
            return {"recovery_plan": inputs.get("recovery_plan", []), "approval_required": True}
        if verb == "learn":
            return {"candidate_decision": inputs.get("lesson", ""), "append_only": True}
        if verb == "stability":
            fingerprints = [item["payload"].get("observed", "") for item in failures]
            return {"failure_count": len(failures), "stable": len(set(fingerprints)) <= 1 if fingerprints else True}
        if verb == "regression":
            return {"baseline": inputs.get("baseline"), "current": inputs.get("current"), "regressed": inputs.get("baseline") != inputs.get("current")}
        return self._generic("cfel", verb, inputs, context=CommandContext())

    def _hrt(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        text = str(inputs.get("text", inputs.get("request", ""))).strip()
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
        assumptions = list(inputs.get("assumptions", []))
        ambiguity_markers = [marker for marker in ("maybe", "either", "or", "unsure", "?") if marker in text.lower()]
        if verb == "interpret":
            return {"objective": sentences[0] if sentences else text, "statements": sentences, "assumptions": assumptions, "ambiguities": ambiguity_markers}
        if verb == "assumptions":
            return {"assumptions": assumptions, "implicit_candidates": [item for item in sentences if item.lower().startswith(("assume", "given"))]}
        if verb == "ambiguity":
            return {"ambiguous": bool(ambiguity_markers), "markers": ambiguity_markers, "clarification_required": bool(ambiguity_markers)}
        if verb == "clarify":
            return {"questions": [f"Clarify: {item}" for item in inputs.get("ambiguities", ambiguity_markers)]}
        if verb == "claims":
            return {"claims": sentences}
        if verb == "provenance":
            return {"source": inputs.get("source", "user"), "text_hash": sha256_json(text), "recorded_at": utc_now()}
        if verb == "summary":
            return {"summary": " ".join(sentences[:3])}
        return {"explanation": text, "assumptions": assumptions, "ambiguities": ambiguity_markers}

    def _ourd(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        objects = list(inputs.get("objects", []))
        relations = list(inputs.get("relations", []))
        boundaries = list(inputs.get("boundaries", []))
        if verb == "graph":
            return {"nodes": objects, "edges": relations}
        if verb == "impact":
            changed = set(inputs.get("changed", []))
            adjacency: Dict[str, set[str]] = defaultdict(set)
            for relation in relations:
                if isinstance(relation, dict) and "from" in relation and "to" in relation:
                    adjacency[str(relation["from"])].add(str(relation["to"]))
            impacted = set(changed)
            frontier = list(changed)
            while frontier:
                current = frontier.pop()
                for target in adjacency[current]:
                    if target not in impacted:
                        impacted.add(target)
                        frontier.append(target)
            return {"changed": sorted(changed), "impacted": sorted(impacted)}
        mapping = {
            "model": {"objects": objects, "relations": relations, "boundaries": boundaries},
            "objects": {"objects": objects},
            "relations": {"relations": relations},
            "boundaries": {"boundaries": boundaries},
            "dependencies": {"dependencies": relations},
            "trace": {"trace": inputs.get("trace", [])},
            "scope": {"scope": inputs.get("scope", ["**"])},
            "exclusions": {"exclusions": inputs.get("exclusions", [])},
        }
        return mapping.get(verb, {"objects": objects, "relations": relations})

    def _iurm(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        dimensions = dict(inputs.get("dimensions", {}))
        baseline = dict(inputs.get("baseline", {}))
        if verb == "dimensions":
            return {"dimensions": dimensions, "active_dimension": inputs.get("active_dimension"), "one_at_a_time": True}
        if verb == "baseline":
            return {"baseline": baseline}
        if verb == "vary":
            dimension = str(inputs["dimension"])
            return {"variants": [{**baseline, dimension: value} for value in dimensions.get(dimension, [])], "frozen": sorted(set(dimensions) - {dimension})}
        if verb == "interactions":
            return {"pairs": list(itertools.combinations(sorted(dimensions), 2))}
        if verb == "mvd":
            return {"minimum_viable_dimensions": [name for name, values in dimensions.items() if len(values) > 1]}
        if verb == "optimise":
            candidates = list(inputs.get("candidates", []))
            objective = str(inputs.get("objective", "score"))
            ranked = sorted(candidates, key=lambda item: item.get(objective, float("inf")))
            return {"best": ranked[0] if ranked else None, "ranked": ranked}
        return {"operation": verb, "dimensions": dimensions, "baseline": baseline, "proposal_only": True}

    def _debug(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        if verb == "reproduce":
            return {"steps": inputs.get("steps", []), "expected": inputs.get("expected"), "observed": inputs.get("observed"), "reproduced": inputs.get("expected") != inputs.get("observed")}
        if verb == "minimise":
            return self.ieps.shrink(inputs.get("sequence", []), inputs.get("required_items", []))
        if verb == "bisect":
            revisions = list(inputs.get("revisions", []))
            outcomes = list(inputs.get("outcomes", []))
            first_bad = next((revision for revision, outcome in zip(revisions, outcomes) if not outcome), None)
            return {"first_bad": first_bad, "evaluated": len(outcomes)}
        if verb == "hypotheses":
            return {"hypotheses": [{"statement": item, "status": "UNTESTED"} for item in inputs.get("hypotheses", [])]}
        if verb == "rootcause":
            evidence_ids = list(inputs.get("evidence_ids", []))
            return {"root_cause": inputs.get("root_cause"), "supported": bool(evidence_ids), "evidence_ids": evidence_ids}
        if verb == "verify":
            return {"verified": bool(inputs.get("success")), "evidence_ids": inputs.get("evidence_ids", [])}
        return {"operation": verb, "trace": inputs.get("trace", []), "comparisons": inputs.get("comparisons", [])}

    def _verify(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        results = list(inputs.get("results", []))
        passed = all(bool(item.get("success")) for item in results) if results else False
        return {
            "verification_kind": verb,
            "passed": passed,
            "results": results,
            "uncovered": list(inputs.get("uncovered", [])),
            "execution_required": not results,
        }

    def _performance(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        samples = [float(value) for value in inputs.get("samples", [])]
        summary = {
            "count": len(samples),
            "minimum": min(samples) if samples else None,
            "maximum": max(samples) if samples else None,
            "mean": sum(samples) / len(samples) if samples else None,
        }
        if verb == "regression" and samples:
            baseline = float(inputs.get("baseline", samples[0]))
            summary["regression"] = summary["mean"] > baseline * (1 + float(inputs.get("tolerance", 0.05)))
        return {"performance_kind": verb, **summary, "unit": inputs.get("unit", "seconds")}

    def _security(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        if verb == "threat-model":
            assets = list(inputs.get("assets", []))
            boundaries = list(inputs.get("boundaries", []))
            return {
                "assets": assets,
                "boundaries": boundaries,
                "threats": [
                    {"threat": threat, "status": "UNMITIGATED"}
                    for threat in inputs.get("threats", [])
                ],
            }
        if verb == "secrets":
            patterns = [
                re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s]+"),
                re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
            ]
            findings = []
            for path in self.workspace.iter_files(str(inputs.get("path", "."))):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line_number, line in enumerate(text.splitlines(), 1):
                    if any(pattern.search(line) for pattern in patterns):
                        findings.append({"path": self.workspace.rel(path), "line": line_number, "text": "<redacted>"})
            return {"findings": findings, "count": len(findings)}
        if verb == "sbom":
            manifests = [
                self.workspace.rel(path)
                for path in self.workspace.iter_files()
                if path.name in {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "CMakeLists.txt"}
            ]
            return {"manifests": manifests, "complete": False, "limitations": ["manifest inventory only"]}
        return {"security_kind": verb, "inputs": inputs, "read_only": True}

    def _repo(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        path = str(inputs.get("path", "."))
        files = [self.workspace.rel(candidate) for candidate in self.workspace.iter_files(path)]
        if verb == "graph":
            nodes = [{"id": file, "type": Path(file).suffix or "file"} for file in files]
            edges = []
            import_pattern = re.compile(r"^(?:from|import)\s+([A-Za-z0-9_.]+)", re.M)
            for relative in files:
                if not relative.endswith(".py"):
                    continue
                text = self.workspace.resolve(relative).read_text(encoding="utf-8", errors="replace")
                for module in import_pattern.findall(text):
                    target = module.replace(".", "/") + ".py"
                    if target in files:
                        edges.append({"from": relative, "to": target, "relation": "imports"})
            return {"nodes": nodes, "edges": edges}
        if verb == "symbols":
            symbols = []
            for relative in files:
                if not relative.endswith(".py"):
                    continue
                try:
                    tree = ast.parse(self.workspace.resolve(relative).read_text(encoding="utf-8"))
                except (OSError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append({"path": relative, "name": node.name, "line": node.lineno, "kind": type(node).__name__})
            return {"symbols": symbols}
        if verb == "metrics":
            suffixes = Counter(Path(file).suffix or "<none>" for file in files)
            return {"file_count": len(files), "suffixes": dict(sorted(suffixes.items()))}
        if verb == "hotspots":
            sizes = sorted(
                [
                    {"path": relative, "bytes": self.workspace.resolve(relative).stat().st_size}
                    for relative in files
                ],
                key=lambda item: (-item["bytes"], item["path"]),
            )
            return {"hotspots": sizes[: int(inputs.get("limit", 20))]}
        return {"repository_operation": verb, "files": files, "limitations": ["filesystem evidence only"]}

    def _agent(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        if verb in {"spawn", "specialise"}:
            return {
                "role": inputs.get("role", "reviewer"),
                "child_scope": inputs.get("scope", []),
                "budget": inputs.get("budget", {}),
                "authority_transfer": False,
                "status": "ROLE_SPECIFIED",
            }
        if verb in {"debate", "review", "critic", "consensus", "merge"}:
            positions = list(inputs.get("positions", inputs.get("reviews", [])))
            return {
                "positions": positions,
                "agreements": inputs.get("agreements", []),
                "disagreements": inputs.get("disagreements", positions),
                "approval": False,
                "provenance_preserved": True,
            }
        return {"agent_id": inputs.get("agent_id"), "status": "TERMINATION_REQUESTED", "authority_transfer": False}

    def _physics_simulate(self, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("physics@1", "simulate", inputs)

    def _geometry(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("geometry@1", verb, inputs)

    def _grammar(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("grammar@1", verb, inputs)

    def _vision(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("vision@1", verb, inputs)

    def _robotics(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("robotics@1", verb, inputs)

    def _cad(self, verb: str, inputs: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return self.domain_packs.execute("cad@1", verb, inputs)
