from __future__ import annotations

from typing import Any, Dict

from ..errors import EGCFError
from .base import ExecutorAdapter


class ModelAdapter(ExecutorAdapter):
    name = "model"
    version = "1"

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object", "required": ["model_identity"]},
                side_effects=[],
                idempotency="proposal-only",
                data_boundary="model output remains untrusted proposal data",
                rollback="not-required",
            ),
            "authority": False,
            "proposal_only": True,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        identity = plan_node.get("inputs", {}).get("model_identity")
        return {"ok": isinstance(identity, dict), "model_identity": identity}

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"simulated": True, "proposal_only": True, "inputs": plan_node.get("inputs", {})}

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        proposal = kwargs.get("model_proposal")
        if proposal is None:
            raise EGCFError("model adapter requires an externally executed, schema-validated proposal")
        return {"proposal": proposal, "proposal_only": True, "approval": False}

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": "proposal" in execution, "authority": False}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "NOT_REQUIRED"}
