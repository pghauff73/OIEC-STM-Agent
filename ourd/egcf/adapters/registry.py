from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .agent import AgentAdapter
from .codex import CodexAdapter
from .eon import EONAdapter
from .mcp import MCPAdapter
from .model import ModelAdapter
from .shell import ShellAdapter
from .simulation import SimulationAdapter
from .skill import SkillAdapter


def adapter_inventory(
    workspace_root: Path,
    authority_path: Path | None = None,
) -> Dict[str, Dict[str, Any]]:
    adapters = [
        CodexAdapter(),
        MCPAdapter(),
        SkillAdapter(),
        AgentAdapter(),
        ModelAdapter(),
        SimulationAdapter(workspace_root),
        ShellAdapter(workspace_root, authority_path),
        EONAdapter(workspace_root, authority_path),
    ]
    inventory = {
        adapter.name: {
            **adapter.describe_capabilities(),
            "registered": True,
            "direct_command_access": False,
        }
        for adapter in adapters
    }
    inventory["engine-control"] = {
        "name": "engine-control",
        "version": "1",
        "input_schema": {"type": "object"},
        "side_effects": ["append-only-approval-records", "execution-plan-control"],
        "idempotency": "exact-plan-and-use-limit-bound",
        "data_boundary": "EGCF canonical objects only",
        "rollback": "target-plan-specific",
        "capability_level": "C1",
        "capabilities": ["workflow.plan", "eon.plan"],
        "authority_transfer": False,
        "registered": True,
        "direct_command_access": False,
    }
    return inventory
