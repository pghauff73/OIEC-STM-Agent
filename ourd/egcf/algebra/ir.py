from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..errors import EGCFError
from .graph import canonicalize_structure
from .models import (
    AlgorithmNodeSpec,
    AlgorithmStructureSpec,
    CanonicalAlgorithmIR,
    ControlEdgeSpec,
    OperandRef,
    PortSpec,
    StateSpec,
    attribute_items,
)


def operand_from_mapping(value: Any) -> OperandRef:
    if isinstance(value, OperandRef):
        return value
    if not isinstance(value, Mapping):
        return OperandRef.constant(value)
    keys = set(value)
    if "input" in value:
        if keys != {"input"}:
            raise EGCFError("SAA input references accept only the input field")
        return OperandRef.input(int(value["input"]))
    if "parameter" in value:
        if keys != {"parameter"}:
            raise EGCFError("SAA parameter references accept only the parameter field")
        return OperandRef.parameter(int(value["parameter"]))
    if "state" in value:
        if keys != {"state"}:
            raise EGCFError("SAA state references accept only the state field")
        return OperandRef.state(int(value["state"]))
    if "node" in value:
        unknown = keys - {"node", "output"}
        if unknown:
            raise EGCFError(f"SAA node reference has unknown fields: {sorted(unknown)}")
        return OperandRef.node(str(value["node"]), int(value.get("output", 0)))
    if "constant" in value:
        if keys != {"constant"}:
            raise EGCFError("SAA constant references accept only the constant field")
        return OperandRef.constant(value["constant"])
    raise EGCFError("SAA operand mapping must identify input, parameter, state, node, or constant")


def _port_from_mapping(value: Mapping[str, Any], role: str) -> PortSpec:
    unknown = set(value) - {"position", "name", "data_type", "shape", "source"}
    if unknown:
        raise EGCFError(f"SAA port has unknown fields: {sorted(unknown)}")
    source = value.get("source")
    return PortSpec(
        role=role,
        position=int(value["position"]),
        name=str(value.get("name", "")),
        data_type=str(value.get("data_type", "scalar")),
        shape=tuple(int(item) for item in value.get("shape", ())),
        source=operand_from_mapping(source) if source is not None else None,
    )


def _state_from_mapping(value: Mapping[str, Any]) -> StateSpec:
    unknown = set(value) - {"position", "name", "data_type", "shape", "initial", "update"}
    if unknown:
        raise EGCFError(f"SAA state has unknown fields: {sorted(unknown)}")
    initial = value.get("initial")
    update = value.get("update")
    return StateSpec(
        position=int(value["position"]),
        name=str(value.get("name", "")),
        data_type=str(value.get("data_type", "scalar")),
        shape=tuple(int(item) for item in value.get("shape", ())),
        initial=operand_from_mapping(initial) if initial is not None else None,
        update=operand_from_mapping(update) if update is not None else None,
    )


def _node_from_mapping(value: Mapping[str, Any]) -> AlgorithmNodeSpec:
    unknown = set(value) - {"id", "primitive", "operands", "attributes", "result_count"}
    if unknown:
        raise EGCFError(f"SAA node has unknown fields: {sorted(unknown)}")
    return AlgorithmNodeSpec(
        node_id=str(value["id"]),
        primitive=str(value["primitive"]),
        operands=tuple(operand_from_mapping(item) for item in value.get("operands", ())),
        attributes=attribute_items(value.get("attributes", {})),
        result_count=int(value.get("result_count", 1)),
    )


def _edge_from_mapping(value: Mapping[str, Any]) -> ControlEdgeSpec:
    unknown = set(value) - {"from", "to", "kind", "label"}
    if unknown:
        raise EGCFError(f"SAA control edge has unknown fields: {sorted(unknown)}")
    return ControlEdgeSpec(
        source=str(value["from"]),
        target=str(value["to"]),
        kind=str(value.get("kind", "next")),
        label=str(value.get("label", "")),
    )


def structure_from_mapping(payload: Mapping[str, Any]) -> AlgorithmStructureSpec:
    """Compile a strict declarative structural specification into the SAA-1 IR input model."""

    allowed = {
        "name",
        "inputs",
        "outputs",
        "parameters",
        "states",
        "nodes",
        "control_edges",
        "entry_nodes",
        "termination_nodes",
        "metadata",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise EGCFError(f"SAA structure has unknown fields: {sorted(unknown)}")
    return AlgorithmStructureSpec(
        name=str(payload.get("name", "anonymous")),
        inputs=tuple(_port_from_mapping(item, "INPUT") for item in payload.get("inputs", ())),
        outputs=tuple(_port_from_mapping(item, "OUTPUT") for item in payload.get("outputs", ())),
        parameters=tuple(
            _port_from_mapping(item, "PARAMETER") for item in payload.get("parameters", ())
        ),
        states=tuple(_state_from_mapping(item) for item in payload.get("states", ())),
        nodes=tuple(_node_from_mapping(item) for item in payload.get("nodes", ())),
        control_edges=tuple(_edge_from_mapping(item) for item in payload.get("control_edges", ())),
        entry_nodes=tuple(str(item) for item in payload.get("entry_nodes", ())),
        termination_nodes=tuple(str(item) for item in payload.get("termination_nodes", ())),
        metadata=dict(payload.get("metadata", {})),
    )


def canonicalize_mapping(
    payload: Mapping[str, Any],
    *,
    max_exact_permutations: int = 10_000,
) -> CanonicalAlgorithmIR:
    return canonicalize_structure(
        structure_from_mapping(payload),
        max_exact_permutations=max_exact_permutations,
    )


def canonicalize_many(
    payloads: Sequence[Mapping[str, Any]],
    *,
    max_exact_permutations: int = 10_000,
) -> tuple[CanonicalAlgorithmIR, ...]:
    return tuple(
        canonicalize_mapping(item, max_exact_permutations=max_exact_permutations)
        for item in payloads
    )
