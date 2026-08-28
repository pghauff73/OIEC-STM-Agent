from __future__ import annotations

from typing import Any, Callable, Dict

from ..errors import ApprovalError, EGCFError
from .base import ExecutorAdapter


class EngineControlAdapter(ExecutorAdapter):
    name = "engine-control"
    version = "1"

    def __init__(
        self,
        *,
        authorize: Callable[..., str],
        execute_plan: Callable[..., Dict[str, Any]],
    ):
        self._authorize = authorize
        self._execute_plan = execute_plan

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object"},
                side_effects=["append-only-approval-records", "execution-plan-control"],
                idempotency="exact-plan-and-use-limit-bound",
                data_boundary="EGCF canonical objects only",
                rollback="target-plan-specific",
            ),
            "capability_level": "C1",
            "capabilities": ["workflow.plan", "eon.plan"],
            "authority_transfer": False,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        command_id = plan_node["command_id"]
        return {
            "ok": command_id in {"eon.authorise@1", "workflow.execute@1"},
            "command_id": command_id,
        }

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "simulated": True,
            "command_id": plan_node["command_id"],
            "authority_transfer": False,
        }

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        inputs = plan_node["inputs"]
        if plan_node["command_id"] == "eon.authorise@1":
            if inputs.get("human_confirmation") is not True:
                raise ApprovalError("eon authorise requires explicit human_confirmation=true")
            approval_id = self._authorize(
                str(inputs["plan_id"]),
                approver=str(inputs["approver"]),
                authority=str(inputs["authority"]),
                constraints=dict(inputs.get("constraints", {})),
                expires_at=str(inputs.get("expires_at", "")),
                use_limit=int(inputs.get("use_limit", 1)),
            )
            return {
                "ok": True,
                "approval_id": approval_id,
                "plan_id": str(inputs["plan_id"]),
                "authority_transfer": False,
            }
        if plan_node["command_id"] == "workflow.execute@1":
            return self._execute_plan(
                str(inputs["plan_id"]),
                approval_id=str(inputs.get("approval_id", "")),
                pause_at_checkpoint=bool(inputs.get("pause_at_checkpoint", False)),
                resume=bool(inputs.get("resume", False)),
            )
        raise EGCFError(f"unsupported engine control command: {plan_node['command_id']}")

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": execution.get("ok") is True, "authority_transfer": False}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "TARGET_PLAN_MANAGED"}
