from __future__ import annotations

from typing import Any, Dict

from ..errors import EGCFError
from ..ids import sha256_json
from .base import ExecutorAdapter


class CodexAdapter(ExecutorAdapter):
    name = "codex"
    version = "1"

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object"},
                side_effects=["host-declared-only"],
                idempotency="host-declared",
                data_boundary="host-provided bounded result is untrusted data",
                rollback="host-managed",
            ),
            "role": "primitive provider",
            "authority": False,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "declared_capabilities": plan_node.get("inputs", {}).get("capabilities", [])}

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"simulated": True, "adapter": self.name}

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        result = kwargs.get("codex_result")
        if result is None:
            raise EGCFError("Codex adapter requires a host-provided bounded result")
        return {
            "result": result,
            "result_hash": sha256_json(result),
            "untrusted_data": True,
            "instructions_accepted": False,
            "authority_transfer": False,
        }

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": "result" in execution, "authority_transfer": False}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "HOST_MANAGED"}
