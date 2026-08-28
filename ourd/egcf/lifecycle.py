from __future__ import annotations

from typing import Any, Dict, Iterable

from .errors import EGCFError


TRANSITIONS: Dict[str, set[str]] = {
    "DISCOVERED": {"INTERPRETED", "REFUSED"},
    "INTERPRETED": {"MODELLED", "REFUSED"},
    "MODELLED": {"RESOLVED", "REFUSED"},
    "RESOLVED": {"QUALIFIED", "REFUSED"},
    "QUALIFIED": {"COMPILED", "REFUSED"},
    "COMPILED": {"SIMULATED", "AWAITING_APPROVAL", "AUTHORIZED", "COMPLETED", "REFUSED"},
    "SIMULATED": {"AWAITING_APPROVAL", "COMPLETED", "FAILED", "REFUSED"},
    "AWAITING_APPROVAL": {"AUTHORIZED", "REFUSED"},
    "AUTHORIZED": {"EXECUTING", "REFUSED"},
    "EXECUTING": {"VERIFYING", "FAILED", "ROLLED_BACK", "PARTIALLY_COMPENSATED"},
    "VERIFYING": {"COMPLETED", "FAILED", "ROLLED_BACK", "PARTIALLY_COMPENSATED"},
}

TERMINAL = {"COMPLETED", "REFUSED", "FAILED", "ROLLED_BACK", "PARTIALLY_COMPENSATED", "SUPERSEDED"}

CANONICAL_STAGES = (
    "DISCOVERED",
    "INTERPRETED",
    "MODELLED",
    "RESOLVED",
    "QUALIFIED",
    "COMPILED",
    "SIMULATED",
    "AWAITING_APPROVAL",
    "AUTHORIZED",
    "EXECUTING",
    "VERIFYING",
    "COMPLETED",
)


class Lifecycle:
    def __init__(self, initial: str = "DISCOVERED"):
        if initial not in TRANSITIONS and initial not in TERMINAL:
            raise EGCFError(f"unknown lifecycle state: {initial}")
        self.state = initial
        self.history = [initial]

    def transition(self, target: str) -> str:
        allowed = TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise EGCFError(f"illegal lifecycle transition: {self.state} -> {target}")
        self.state = target
        self.history.append(target)
        return target

    def compress(self, stages: Iterable[str]) -> list[str]:
        for stage in stages:
            self.transition(stage)
        return list(self.history)

    def projection(self) -> list[Dict[str, Any]]:
        visited = set(self.history)
        terminal = self.state in TERMINAL
        entries: list[Dict[str, Any]] = []
        for stage in CANONICAL_STAGES:
            if stage in visited:
                status = "completed" if stage != self.state or terminal else "current"
                reason = ""
            elif terminal:
                status = "not_required"
                reason = f"not traversed for terminal outcome {self.state}"
            else:
                status = "blocked"
                reason = f"awaiting completion of {self.state}"
            entries.append({"stage": stage, "status": status, "reason": reason})
        for state in self.history:
            if state not in CANONICAL_STAGES:
                entries.append(
                    {
                        "stage": state,
                        "status": "completed" if terminal else "current",
                        "reason": "terminal or control state",
                    }
                )
        return entries
