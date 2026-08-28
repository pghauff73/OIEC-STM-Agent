from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Optional

from .errors import CompilationError


RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2}
APPROVAL_ORDER = {"automatic": 0, "policy": 1, "human": 2, "quorum": 3}
ROLLBACK_ORDER = {"none": 0, "best_effort": 1, "compensating": 2, "exact": 3}


@dataclass
class Budget:
    tokens: Optional[int] = None
    wall_seconds: Optional[float] = None
    actions: Optional[int] = None
    subprocesses: Optional[int] = None
    writes: Optional[int] = None
    write_bytes: Optional[int] = None
    network_requests: Optional[int] = None
    network_bytes: Optional[int] = None
    cost_micros: Optional[int] = None
    retries: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def narrow(self, child: "Budget") -> "Budget":
        values: Dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            parent_value = getattr(self, name)
            child_value = getattr(child, name)
            if parent_value is None:
                values[name] = child_value
            elif child_value is None:
                values[name] = parent_value
            else:
                values[name] = min(parent_value, child_value)
        return Budget(**values)

    def require_nonnegative(self) -> None:
        for name, value in self.to_dict().items():
            if value is not None and value < 0:
                raise CompilationError(f"budget {name} cannot be negative")

    @classmethod
    def from_value(cls, value: Any) -> "Budget":
        if value in (None, ""):
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            budget = cls(**value)
            budget.require_nonnegative()
            return budget
        if not isinstance(value, str):
            raise CompilationError("budget must be a mapping or comma-separated key=value string")
        payload: Dict[str, Any] = {}
        for item in value.split(","):
            key, separator, raw = item.partition("=")
            key = key.strip().replace("-", "_")
            if not separator or key not in cls.__dataclass_fields__:
                raise CompilationError(f"invalid budget item: {item!r}")
            payload[key] = float(raw) if key == "wall_seconds" else int(raw)
        budget = cls(**payload)
        budget.require_nonnegative()
        return budget


def _max_by_order(left: str, right: str, order: Dict[str, int], label: str) -> str:
    if left not in order or right not in order:
        raise CompilationError(f"invalid {label}: {left!r} or {right!r}")
    return max((left, right), key=order.__getitem__)


def scope_contains(parent: str, child: str) -> bool:
    normalized_parent = parent.strip().replace("\\", "/")
    normalized_child = child.strip().replace("\\", "/")
    if normalized_parent in {"*", "**", "."}:
        return True
    if normalized_parent == normalized_child:
        return True
    if normalized_parent.endswith("/**"):
        prefix = normalized_parent[:-3].rstrip("/")
        return normalized_child == prefix or normalized_child.startswith(f"{prefix}/")
    if any(character in normalized_child for character in "*?["):
        return False
    return fnmatch.fnmatchcase(normalized_child, normalized_parent)


def narrow_scope(parent: Iterable[str], child: Iterable[str]) -> list[str]:
    parent_scope = list(dict.fromkeys(parent))
    child_scope = list(dict.fromkeys(child))
    if not child_scope:
        return parent_scope
    uncovered = [
        item for item in child_scope if not any(scope_contains(container, item) for container in parent_scope)
    ]
    if uncovered:
        raise CompilationError(f"child scope broadens parent scope: {uncovered}")
    return child_scope


@dataclass
class CommandContext:
    dry_run: bool = False
    why: bool = False
    scope: list[str] = field(default_factory=lambda: ["**"])
    evidence: list[str] = field(default_factory=list)
    approval: str = "automatic"
    risk: str = "L0"
    rollback: str = "none"
    budget: Budget = field(default_factory=Budget)
    timeout: Optional[float] = None
    trace: bool = False
    json_output: bool = False
    graph: bool = False
    record: bool = False
    replay: str = ""
    strict: bool = False
    simulate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["budget"] = self.budget.to_dict()
        return payload

    def inherit(self, child: "CommandContext") -> "CommandContext":
        timeout_values = [value for value in (self.timeout, child.timeout) if value is not None]
        return CommandContext(
            dry_run=self.dry_run or child.dry_run,
            why=self.why or child.why,
            scope=narrow_scope(self.scope, child.scope),
            evidence=list(dict.fromkeys([*self.evidence, *child.evidence])),
            approval=_max_by_order(self.approval, child.approval, APPROVAL_ORDER, "approval"),
            risk=_max_by_order(self.risk, child.risk, RISK_ORDER, "risk"),
            rollback=_max_by_order(self.rollback, child.rollback, ROLLBACK_ORDER, "rollback"),
            budget=self.budget.narrow(child.budget),
            timeout=min(timeout_values) if timeout_values else None,
            trace=self.trace or child.trace,
            json_output=self.json_output or child.json_output,
            graph=self.graph or child.graph,
            record=self.record or child.record,
            replay=child.replay or self.replay,
            strict=self.strict or child.strict,
            simulate=self.simulate or child.simulate,
        )

    @classmethod
    def from_mapping(cls, payload: Optional[Dict[str, Any]] = None) -> "CommandContext":
        data = dict(payload or {})
        aliases = {"json": "json_output"}
        for source, target in aliases.items():
            if source in data:
                data[target] = data.pop(source)
        data["budget"] = Budget.from_value(data.get("budget"))
        context = cls(**data)
        if context.risk not in RISK_ORDER:
            raise CompilationError(f"invalid risk: {context.risk}")
        if context.approval not in APPROVAL_ORDER:
            raise CompilationError(f"invalid approval: {context.approval}")
        if context.rollback not in ROLLBACK_ORDER:
            raise CompilationError(f"invalid rollback: {context.rollback}")
        if context.timeout is not None and context.timeout <= 0:
            raise CompilationError("timeout must be greater than zero")
        if context.simulate and data.get("real_execution_success"):
            raise CompilationError("simulation cannot record real execution success")
        return context
