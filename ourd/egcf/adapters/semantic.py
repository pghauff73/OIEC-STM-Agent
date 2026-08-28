from __future__ import annotations

from typing import Any, Dict

from ..context import CommandContext
from ..handlers import SemanticHandlers
from ..models import CapabilityGrant
from .base import ExecutorAdapter


class SemanticAdapter(ExecutorAdapter):
    name = "semantic"
    version = "1"

    def __init__(self, handlers: SemanticHandlers, context: CommandContext, grant: CapabilityGrant):
        self.handlers = handlers
        self.context = context
        self.grant = grant
        self._last_approval_id = ""

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object"},
                side_effects=["append-only-internal-records"],
                idempotency="content-addressed-records",
                data_boundary="workspace reads and governed internal state",
                rollback="append-only-supersedence-or-compensation",
            ),
            "capability_level": "C1",
            "capabilities": ["registry.read", "analysis.reason", "evidence.analyse"],
            "workspace_mutation": False,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": plan_node["capability_level"] in {"C0", "C1", "C2", "C3"},
            "command_id": plan_node["command_id"],
        }

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "simulated": True,
            "command_id": plan_node["command_id"],
            "inputs": plan_node["inputs"],
            "fidelity_limits": ["semantic handler not invoked"],
        }

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        self._last_approval_id = str(kwargs.get("approval_id", ""))
        return self.handlers.execute(
            plan_node["command_id"],
            plan_node["inputs"],
            context=self.context,
            grant=self.grant,
            approval=dict(kwargs.get("approval", {})),
            approval_id=str(kwargs.get("approval_id", "")),
        )

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": execution.get("ok") is True, "read_only": execution.get("read_only", True)}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return self.handlers.compensate(
            plan_node["command_id"],
            plan_node["inputs"],
            execution,
            authority=self._last_approval_id or "execution-failure-compensation",
        )
