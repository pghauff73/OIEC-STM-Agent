from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...agent import OURDAgent
from ..errors import EGCFError
from .base import ExecutorAdapter


class ShellAdapter(ExecutorAdapter):
    name = "shell"
    version = "1"

    def __init__(self, workspace_root: Path, authority_path: Path | None):
        self.workspace_root = workspace_root
        self.authority_path = authority_path

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object", "required": ["command"]},
                side_effects=["exact-authorized-argv-only"],
                idempotency="command-specific",
                data_boundary="sanitized child process environment",
                rollback="not-available-for-mutation",
            ),
            "capabilities": ["exact authorized argv only"],
            "shell": False,
            "arbitrary_execution": False,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": "command" in plan_node.get("inputs", {})}

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"simulated": True, "argv_source": plan_node.get("inputs", {}).get("command", "")}

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        command = str(plan_node.get("inputs", {}).get("command", ""))
        if not command:
            raise EGCFError("shell adapter requires an exact command string")
        with OURDAgent(self.workspace_root, authority_path=self.authority_path) as agent:
            return agent.run_command(command, int(plan_node.get("inputs", {}).get("timeout", 120)))

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": execution.get("ok") is True, "returncode": execution.get("returncode")}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "NOT_AVAILABLE", "reason": "shell adapter exposes no mutation commands"}
