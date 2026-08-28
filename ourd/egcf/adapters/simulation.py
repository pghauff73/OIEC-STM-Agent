from __future__ import annotations

from typing import Any, Dict
from pathlib import Path

from ..errors import EGCFError
from ..simulation import SimulationEngine
from .base import ExecutorAdapter


class SimulationAdapter(ExecutorAdapter):
    name = "simulation"
    version = "1"

    def __init__(self, workspace_root: Path):
        self.engine = SimulationEngine()
        self.workspace_root = workspace_root

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object"},
                side_effects=["disposable-temporary-state"],
                idempotency="deterministic-for-canonical-input",
                data_boundary="synthetic or disposable state only",
                rollback="discard-or-simulated-inverse",
            ),
            "capability_level": "C2",
            "capabilities": ["simulation.run"],
            "real_side_effects": False,
        }

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "simulated": True, "node_id": plan_node["node_id"]}

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        command_id = plan_node["command_id"]
        inputs = plan_node["inputs"]
        if command_id == "simulate.worktree@1":
            return self.engine.worktree(self.workspace_root, inputs.get("changes", []))
        if command_id == "simulate.migration@1":
            return self.engine.migration(inputs.get("before", {}), inputs.get("operations", []))
        if command_id == "simulate.rollback@1":
            return self.engine.rollback(inputs["simulation"])
        return {
            "simulated": True,
            "command_id": command_id,
            "inputs": inputs,
            "fidelity_limits": ["declarative v1 simulation", "no real executor invoked"],
        }

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        if not kwargs.get("simulation_authorized", False):
            raise EGCFError("simulation adapter requires explicit simulation mode")
        return self.simulate(plan_node)

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {"verified": execution.get("simulated") is True, "simulated": True}

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        if "rollback_operations" not in execution:
            return {"simulated": True, "status": "NOT_REQUIRED"}
        return self.engine.rollback(execution)
