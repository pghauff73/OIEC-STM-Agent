from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Tuple

from ..errors import EGCFError
from .primitives import normalize_primitive


REF_KINDS = {"input", "parameter", "state", "node", "constant"}
PORT_ROLES = {"INPUT", "OUTPUT", "PARAMETER"}
CONTROL_KINDS = {"next", "true", "false", "loop", "backtrack", "terminate", "exception"}


def _shape(values: Iterable[int]) -> Tuple[int, ...]:
    result = tuple(int(value) for value in values)
    if any(value < 1 for value in result):
        raise EGCFError("SAA shapes must contain positive dimensions")
    return result


def attribute_items(values: Mapping[str, Any] | Iterable[tuple[str, Any]] = ()) -> Tuple[tuple[str, Any], ...]:
    if isinstance(values, Mapping):
        items = values.items()
    else:
        items = values
    normalized = []
    for key, value in items:
        name = str(key).strip()
        if not name:
            raise EGCFError("SAA attribute names must be non-empty")
        normalized.append((name, value))
    return tuple(sorted(normalized, key=lambda item: item[0]))


@dataclass(frozen=True)
class OperandRef:
    kind: str
    position: int = -1
    node_id: str = ""
    output_index: int = 0
    value: Any = None

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().lower()
        if kind not in REF_KINDS:
            raise EGCFError(f"unsupported SAA operand kind: {self.kind!r}")
        object.__setattr__(self, "kind", kind)
        if kind in {"input", "parameter", "state"}:
            if int(self.position) < 0:
                raise EGCFError(f"{kind} operand requires a non-negative position")
        elif kind == "node":
            if not str(self.node_id).strip():
                raise EGCFError("node operand requires node_id")
            if int(self.output_index) < 0:
                raise EGCFError("node output_index cannot be negative")
        elif kind == "constant":
            if isinstance(self.value, (dict, list, set)):
                raise EGCFError("SAA constants must be scalar or tuple values")

    @classmethod
    def input(cls, position: int) -> "OperandRef":
        return cls("input", position=position)

    @classmethod
    def parameter(cls, position: int) -> "OperandRef":
        return cls("parameter", position=position)

    @classmethod
    def state(cls, position: int) -> "OperandRef":
        return cls("state", position=position)

    @classmethod
    def node(cls, node_id: str, output_index: int = 0) -> "OperandRef":
        return cls("node", node_id=node_id, output_index=output_index)

    @classmethod
    def constant(cls, value: Any) -> "OperandRef":
        return cls("constant", value=value)


@dataclass(frozen=True)
class PortSpec:
    role: str
    position: int
    name: str = ""
    data_type: str = "scalar"
    shape: Tuple[int, ...] = ()
    source: OperandRef | None = None

    def __post_init__(self) -> None:
        role = str(self.role).strip().upper()
        if role not in PORT_ROLES:
            raise EGCFError(f"unsupported SAA port role: {self.role!r}")
        if int(self.position) < 0:
            raise EGCFError("SAA port position cannot be negative")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "shape", _shape(self.shape))
        if role == "OUTPUT" and self.source is None:
            raise EGCFError("SAA output ports require a source binding")
        if role != "OUTPUT" and self.source is not None:
            raise EGCFError("only SAA output ports may bind a source")


@dataclass(frozen=True)
class StateSpec:
    position: int
    name: str = ""
    data_type: str = "scalar"
    shape: Tuple[int, ...] = ()
    initial: OperandRef | None = None
    update: OperandRef | None = None

    def __post_init__(self) -> None:
        if int(self.position) < 0:
            raise EGCFError("SAA state position cannot be negative")
        object.__setattr__(self, "shape", _shape(self.shape))


@dataclass(frozen=True)
class AlgorithmNodeSpec:
    node_id: str
    primitive: str
    operands: Tuple[OperandRef, ...] = ()
    attributes: Tuple[tuple[str, Any], ...] = ()
    result_count: int = 1

    def __post_init__(self) -> None:
        node_id = str(self.node_id).strip()
        if not node_id:
            raise EGCFError("SAA node_id must be non-empty")
        primitive = normalize_primitive(self.primitive).name
        if int(self.result_count) < 0:
            raise EGCFError("SAA result_count cannot be negative")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "primitive", primitive)
        object.__setattr__(self, "operands", tuple(self.operands))
        object.__setattr__(self, "attributes", attribute_items(self.attributes))


@dataclass(frozen=True)
class ControlEdgeSpec:
    source: str
    target: str
    kind: str = "next"
    label: str = ""

    def __post_init__(self) -> None:
        source = str(self.source).strip()
        target = str(self.target).strip()
        kind = str(self.kind).strip().lower()
        if not source or not target:
            raise EGCFError("SAA control edges require source and target")
        if kind not in CONTROL_KINDS:
            raise EGCFError(f"unsupported SAA control edge kind: {self.kind!r}")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "label", str(self.label).strip())


@dataclass(frozen=True)
class AlgorithmStructureSpec:
    name: str
    inputs: Tuple[PortSpec, ...] = ()
    outputs: Tuple[PortSpec, ...] = ()
    parameters: Tuple[PortSpec, ...] = ()
    states: Tuple[StateSpec, ...] = ()
    nodes: Tuple[AlgorithmNodeSpec, ...] = ()
    control_edges: Tuple[ControlEdgeSpec, ...] = ()
    entry_nodes: Tuple[str, ...] = ()
    termination_nodes: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "states", tuple(self.states))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "control_edges", tuple(self.control_edges))
        object.__setattr__(self, "entry_nodes", tuple(str(value) for value in self.entry_nodes))
        object.__setattr__(self, "termination_nodes", tuple(str(value) for value in self.termination_nodes))


@dataclass(frozen=True)
class CanonicalAlgorithmIR:
    schema_version: int
    canonicalizer_version: str
    structural_hash: str
    canonical_payload: Mapping[str, Any]
    canonicalization_strength: str
    exact_permutations_considered: int
    source_node_map: Tuple[tuple[str, int], ...]
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonicalizer_version": self.canonicalizer_version,
            "structural_hash": self.structural_hash,
            "canonical_payload": dict(self.canonical_payload),
            "canonicalization_strength": self.canonicalization_strength,
            "exact_permutations_considered": self.exact_permutations_considered,
            "source_node_map": [list(item) for item in self.source_node_map],
            "warnings": list(self.warnings),
        }
