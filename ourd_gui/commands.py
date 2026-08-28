from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


def safe_default_modifiers() -> Dict[str, Any]:
    return {
        "dry_run": True,
        "why": True,
        "scope": ["**"],
        "evidence": [],
        "approval": "automatic",
        "risk": "L0",
        "rollback": "none",
        "budget": {},
        "timeout": None,
        "trace": True,
        "json_output": True,
        "graph": True,
        "record": True,
        "replay": "",
        "strict": False,
        "simulate": False,
    }


@dataclass(frozen=True)
class ObjectiveRequest:
    objective: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    modifiers: Dict[str, Any] = field(default_factory=safe_default_modifiers)


@dataclass(frozen=True)
class CommandRequest:
    command_id: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    modifiers: Dict[str, Any] = field(default_factory=safe_default_modifiers)


@dataclass(frozen=True)
class ApprovalRequest:
    plan_id: str
    approver: str
    authority: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    expires_at: str = ""
    use_limit: int = 1


@dataclass(frozen=True)
class ExecutionRequest:
    plan_id: str
    approval_id: str = ""
    pause_at_checkpoint: bool = False
    resume: bool = False


@dataclass(frozen=True)
class ReplayRequest:
    plan_id: str
    modifiers: Dict[str, Any] = field(default_factory=safe_default_modifiers)

