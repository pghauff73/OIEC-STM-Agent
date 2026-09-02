from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence

from ..errors import EGCFError
from ..ids import canonical_json, sha256_json
from .models import (
    AlgorithmNodeSpec,
    AlgorithmStructureSpec,
    CanonicalAlgorithmIR,
    OperandRef,
)
from .primitives import PRIMITIVES


CANONICALIZER_VERSION = "saa-structural-ir-v1"
IDENTITY_IGNORED_ATTRIBUTE_KEYS = {
    "comment",
    "description",
    "display_name",
    "name",
    "source_column",
    "source_file",
    "source_line",
}


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return {"number": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EGCFError("SAA canonical values cannot contain NaN or infinity")
        if value == 0.0:
            value = 0.0
        return {"number": format(value, ".17g")}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise EGCFError(f"unsupported SAA canonical value type: {type(value).__name__}")


def _attributes(node: AlgorithmNodeSpec) -> list[list[Any]]:
    return [
        [key, _canonical_value(value)]
        for key, value in node.attributes
        if key not in IDENTITY_IGNORED_ATTRIBUTE_KEYS
    ]


def _position_map(values: Sequence[Any], role: str) -> dict[int, Any]:
    result: dict[int, Any] = {}
    for item in values:
        position = int(item.position)
        if position in result:
            raise EGCFError(f"duplicate SAA {role} position: {position}")
        result[position] = item
    expected = list(range(len(values)))
    if sorted(result) != expected:
        raise EGCFError(
            f"SAA {role} positions must be contiguous 0..{max(len(values) - 1, 0)}"
        )
    return result


def _validate_ref(
    ref: OperandRef,
    *,
    inputs: Mapping[int, Any],
    parameters: Mapping[int, Any],
    states: Mapping[int, Any],
    nodes: Mapping[str, AlgorithmNodeSpec],
) -> None:
    if ref.kind == "input" and ref.position not in inputs:
        raise EGCFError(f"SAA reference uses unknown input position {ref.position}")
    if ref.kind == "parameter" and ref.position not in parameters:
        raise EGCFError(f"SAA reference uses unknown parameter position {ref.position}")
    if ref.kind == "state" and ref.position not in states:
        raise EGCFError(f"SAA reference uses unknown state position {ref.position}")
    if ref.kind == "node":
        target = nodes.get(ref.node_id)
        if target is None:
            raise EGCFError(f"SAA reference uses unknown node {ref.node_id!r}")
        if ref.output_index >= target.result_count:
            raise EGCFError(
                f"SAA reference output {ref.output_index} exceeds node {ref.node_id!r} result count"
            )


def validate_structure(spec: AlgorithmStructureSpec) -> None:
    inputs = _position_map(spec.inputs, "input")
    outputs = _position_map(spec.outputs, "output")
    parameters = _position_map(spec.parameters, "parameter")
    states = _position_map(spec.states, "state")
    if any(item.role != "INPUT" for item in spec.inputs):
        raise EGCFError("SAA inputs must use INPUT port role")
    if any(item.role != "OUTPUT" for item in spec.outputs):
        raise EGCFError("SAA outputs must use OUTPUT port role")
    if any(item.role != "PARAMETER" for item in spec.parameters):
        raise EGCFError("SAA parameters must use PARAMETER port role")
    node_map = {node.node_id: node for node in spec.nodes}
    if len(node_map) != len(spec.nodes):
        raise EGCFError("SAA node IDs must be unique")
    if not spec.nodes:
        raise EGCFError("SAA structural IR requires at least one node")

    for node in spec.nodes:
        for ref in node.operands:
            _validate_ref(
                ref,
                inputs=inputs,
                parameters=parameters,
                states=states,
                nodes=node_map,
            )
    for output in outputs.values():
        assert output.source is not None
        _validate_ref(
            output.source,
            inputs=inputs,
            parameters=parameters,
            states=states,
            nodes=node_map,
        )
    for state in states.values():
        for ref in (state.initial, state.update):
            if ref is not None:
                _validate_ref(
                    ref,
                    inputs=inputs,
                    parameters=parameters,
                    states=states,
                    nodes=node_map,
                )
    for edge in spec.control_edges:
        if edge.source not in node_map or edge.target not in node_map:
            raise EGCFError("SAA control edge references an unknown node")
    for node_id in (*spec.entry_nodes, *spec.termination_nodes):
        if node_id not in node_map:
            raise EGCFError(f"SAA external node reference does not exist: {node_id!r}")
    for node_id in spec.termination_nodes:
        if node_map[node_id].primitive != "TERMINATE":
            raise EGCFError("SAA termination_nodes must identify TERMINATE primitives")


def _external_tags(spec: AlgorithmStructureSpec) -> dict[str, list[Any]]:
    tags: dict[str, list[Any]] = defaultdict(list)
    for output in spec.outputs:
        if output.source is not None and output.source.kind == "node":
            tags[output.source.node_id].append(
                ["output", output.position, output.source.output_index]
            )
    for state in spec.states:
        for kind, ref in (("initial", state.initial), ("update", state.update)):
            if ref is not None and ref.kind == "node":
                tags[ref.node_id].append(
                    [f"state_{kind}", state.position, ref.output_index]
                )
    for node_id in spec.entry_nodes:
        tags[node_id].append(["entry"])
    for node_id in spec.termination_nodes:
        tags[node_id].append(["termination"])
    return {key: sorted(value, key=canonical_json) for key, value in tags.items()}


def _ref_skeleton(ref: OperandRef) -> Any:
    if ref.kind == "node":
        return ["node", ref.output_index]
    if ref.kind == "constant":
        return ["constant", _canonical_value(ref.value)]
    prefix = {"input": "u", "parameter": "p", "state": "x"}[ref.kind]
    return [prefix, ref.position]


def _static_material(node: AlgorithmNodeSpec, tags: Mapping[str, list[Any]]) -> dict[str, Any]:
    operands = [_ref_skeleton(ref) for ref in node.operands]
    if PRIMITIVES[node.primitive].commutative:
        operands = sorted(operands, key=canonical_json)
    return {
        "primitive": node.primitive,
        "operands": operands,
        "attributes": _attributes(node),
        "result_count": node.result_count,
        "external_tags": tags.get(node.node_id, []),
    }


def _ref_color(ref: OperandRef, colors: Mapping[str, str]) -> Any:
    if ref.kind == "node":
        return ["node", colors[ref.node_id], ref.output_index]
    return _ref_skeleton(ref)


def _refine_colors(spec: AlgorithmStructureSpec) -> dict[str, str]:
    tags = _external_tags(spec)
    nodes = {node.node_id: node for node in spec.nodes}
    incoming: dict[str, list[Any]] = defaultdict(list)
    outgoing: dict[str, list[Any]] = defaultdict(list)
    for edge in spec.control_edges:
        outgoing[edge.source].append([edge.kind, edge.label, edge.target])
        incoming[edge.target].append([edge.kind, edge.label, edge.source])

    colors = {
        node_id: sha256_json(_static_material(node, tags))
        for node_id, node in nodes.items()
    }
    for _ in range(max(2, len(nodes) + 1)):
        revised: dict[str, str] = {}
        for node_id, node in nodes.items():
            operands = [_ref_color(ref, colors) for ref in node.operands]
            if PRIMITIVES[node.primitive].commutative:
                operands = sorted(operands, key=canonical_json)
            material = {
                "static": _static_material(node, tags),
                "operands": operands,
                "incoming": sorted(
                    [[kind, label, colors[source]] for kind, label, source in incoming[node_id]],
                    key=canonical_json,
                ),
                "outgoing": sorted(
                    [[kind, label, colors[target]] for kind, label, target in outgoing[node_id]],
                    key=canonical_json,
                ),
            }
            revised[node_id] = sha256_json(material)
        if revised == colors:
            break
        colors = revised
    return colors


def _ref_token(ref: OperandRef, node_index: Mapping[str, int]) -> Any:
    if ref.kind == "node":
        return ["n", node_index[ref.node_id], ref.output_index]
    if ref.kind == "constant":
        return ["c", _canonical_value(ref.value)]
    prefix = {"input": "u", "parameter": "p", "state": "x"}[ref.kind]
    return [prefix, ref.position]


def _port_payload(port: Any) -> dict[str, Any]:
    return {
        "position": int(port.position),
        "data_type": str(port.data_type),
        "shape": list(port.shape),
    }


def _serialize_exact(spec: AlgorithmStructureSpec, order: Sequence[str]) -> dict[str, Any]:
    node_map = {node.node_id: node for node in spec.nodes}
    node_index = {node_id: index for index, node_id in enumerate(order)}
    nodes = []
    for node_id in order:
        node = node_map[node_id]
        operands = [_ref_token(ref, node_index) for ref in node.operands]
        if PRIMITIVES[node.primitive].commutative:
            operands = sorted(operands, key=canonical_json)
        nodes.append(
            {
                "primitive": node.primitive,
                "operands": operands,
                "attributes": _attributes(node),
                "result_count": node.result_count,
            }
        )
    outputs = []
    for port in sorted(spec.outputs, key=lambda item: item.position):
        assert port.source is not None
        outputs.append({**_port_payload(port), "source": _ref_token(port.source, node_index)})
    states = []
    for state in sorted(spec.states, key=lambda item: item.position):
        states.append(
            {
                "position": state.position,
                "data_type": state.data_type,
                "shape": list(state.shape),
                "initial": _ref_token(state.initial, node_index) if state.initial else None,
                "update": _ref_token(state.update, node_index) if state.update else None,
            }
        )
    return {
        "schema_version": 1,
        "inputs": [_port_payload(item) for item in sorted(spec.inputs, key=lambda item: item.position)],
        "parameters": [
            _port_payload(item) for item in sorted(spec.parameters, key=lambda item: item.position)
        ],
        "outputs": outputs,
        "states": states,
        "nodes": nodes,
        "control_edges": sorted(
            [
                [node_index[edge.source], node_index[edge.target], edge.kind, edge.label]
                for edge in spec.control_edges
            ],
            key=canonical_json,
        ),
        "entry_nodes": sorted(node_index[node_id] for node_id in spec.entry_nodes),
        "termination_nodes": sorted(node_index[node_id] for node_id in spec.termination_nodes),
    }


def _serialize_refined(spec: AlgorithmStructureSpec, colors: Mapping[str, str]) -> dict[str, Any]:
    tags = _external_tags(spec)
    nodes = []
    for node in spec.nodes:
        operands = [_ref_color(ref, colors) for ref in node.operands]
        if PRIMITIVES[node.primitive].commutative:
            operands = sorted(operands, key=canonical_json)
        nodes.append(
            {
                "color": colors[node.node_id],
                "primitive": node.primitive,
                "operands": operands,
                "attributes": _attributes(node),
                "result_count": node.result_count,
                "external_tags": tags.get(node.node_id, []),
            }
        )
    return {
        "schema_version": 1,
        "strength": "REFINED_FINGERPRINT",
        "inputs": [_port_payload(item) for item in sorted(spec.inputs, key=lambda item: item.position)],
        "parameters": [
            _port_payload(item) for item in sorted(spec.parameters, key=lambda item: item.position)
        ],
        "outputs": sorted(
            [
                {
                    **_port_payload(port),
                    "source": (
                        ["node-color", colors[port.source.node_id], port.source.output_index]
                        if port.source and port.source.kind == "node"
                        else _ref_skeleton(port.source) if port.source else None
                    ),
                }
                for port in spec.outputs
            ],
            key=canonical_json,
        ),
        "states": sorted(
            [
                {
                    "position": state.position,
                    "data_type": state.data_type,
                    "shape": list(state.shape),
                    "initial": (
                        ["node-color", colors[state.initial.node_id], state.initial.output_index]
                        if state.initial and state.initial.kind == "node"
                        else _ref_skeleton(state.initial) if state.initial else None
                    ),
                    "update": (
                        ["node-color", colors[state.update.node_id], state.update.output_index]
                        if state.update and state.update.kind == "node"
                        else _ref_skeleton(state.update) if state.update else None
                    ),
                }
                for state in spec.states
            ],
            key=canonical_json,
        ),
        "nodes": sorted(nodes, key=canonical_json),
        "control_edges": sorted(
            [
                [colors[edge.source], colors[edge.target], edge.kind, edge.label]
                for edge in spec.control_edges
            ],
            key=canonical_json,
        ),
        "entry_nodes": sorted(colors[node_id] for node_id in spec.entry_nodes),
        "termination_nodes": sorted(colors[node_id] for node_id in spec.termination_nodes),
    }


def _permutation_bound(groups: Sequence[Sequence[str]]) -> int:
    total = 1
    for group in groups:
        total *= math.factorial(len(group))
    return total


def canonicalize_structure(
    spec: AlgorithmStructureSpec,
    *,
    max_exact_permutations: int = 10_000,
) -> CanonicalAlgorithmIR:
    """Return a deterministic structural identity independent of source node/variable names.

    Exact graph canonicalization is attempted inside stable refinement color classes. If the
    symmetry search would exceed ``max_exact_permutations`` the result is explicitly downgraded
    to an invariant refined fingerprint rather than falsely claiming exact graph equivalence.
    """

    validate_structure(spec)
    if max_exact_permutations < 1:
        raise EGCFError("max_exact_permutations must be positive")
    colors = _refine_colors(spec)
    grouped: dict[str, list[str]] = defaultdict(list)
    for node_id, color in colors.items():
        grouped[color].append(node_id)
    groups = [tuple(sorted(grouped[color])) for color in sorted(grouped)]
    permutation_count = _permutation_bound(groups)

    if permutation_count <= max_exact_permutations:
        best_json: str | None = None
        best_payload: dict[str, Any] | None = None
        best_order: tuple[str, ...] | None = None
        for group_permutations in itertools.product(
            *(itertools.permutations(group) for group in groups)
        ):
            order = tuple(node_id for group in group_permutations for node_id in group)
            payload = _serialize_exact(spec, order)
            serialized = canonical_json(payload)
            if best_json is None or serialized < best_json:
                best_json = serialized
                best_payload = payload
                best_order = order
        assert best_payload is not None and best_order is not None
        return CanonicalAlgorithmIR(
            schema_version=1,
            canonicalizer_version=CANONICALIZER_VERSION,
            structural_hash=sha256_json(best_payload),
            canonical_payload=best_payload,
            canonicalization_strength="EXACT_STRUCTURAL",
            exact_permutations_considered=permutation_count,
            source_node_map=tuple(
                sorted(
                    ((node_id, index) for index, node_id in enumerate(best_order)),
                    key=lambda item: item[0],
                )
            ),
        )

    payload = _serialize_refined(spec, colors)
    warning = (
        f"exact structural canonicalization would require {permutation_count} permutations; "
        "using invariant refinement fingerprint"
    )
    return CanonicalAlgorithmIR(
        schema_version=1,
        canonicalizer_version=CANONICALIZER_VERSION,
        structural_hash=sha256_json(payload),
        canonical_payload=payload,
        canonicalization_strength="REFINED_FINGERPRINT",
        exact_permutations_considered=0,
        source_node_map=tuple(
            (node_id, index)
            for index, node_id in enumerate(sorted(colors, key=lambda key: (colors[key], key)))
        ),
        warnings=(warning,),
    )
