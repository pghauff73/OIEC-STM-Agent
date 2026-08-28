from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable

from .errors import EGCFError
from .schemas import validate_json_value


DomainOperation = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class DomainPack:
    name: str
    version: int
    commands: tuple[str, ...]
    operations: Dict[str, DomainOperation]
    input_contracts: Dict[str, Dict[str, Any]]
    output_contracts: Dict[str, Dict[str, Any]]
    units: Dict[str, str] = field(default_factory=dict)
    tolerances: Dict[str, float] = field(default_factory=dict)
    datasets: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    evidence_policy: Dict[str, Any] = field(default_factory=dict)
    authority_transfer: bool = False

    @property
    def pack_id(self) -> str:
        return f"{self.name}@{self.version}"


class DomainPackRegistry:
    def __init__(self):
        self._packs: Dict[str, DomainPack] = {}

    def register(self, pack: DomainPack) -> None:
        if pack.authority_transfer:
            raise EGCFError("domain packs cannot transfer or broaden authority")
        if set(pack.commands) != set(pack.operations):
            raise EGCFError("domain pack commands and operations must match exactly")
        if set(pack.commands) != set(pack.input_contracts):
            raise EGCFError("domain pack commands and input contracts must match exactly")
        if set(pack.commands) != set(pack.output_contracts):
            raise EGCFError("domain pack commands and output contracts must match exactly")
        if pack.pack_id in self._packs:
            raise EGCFError(f"domain pack already registered: {pack.pack_id}")
        self._packs[pack.pack_id] = pack

    def describe(self, pack_id: str) -> Dict[str, Any]:
        pack = self._packs.get(pack_id)
        if pack is None:
            raise EGCFError(f"unknown domain pack: {pack_id}")
        return {
            "pack_id": pack.pack_id,
            "commands": list(pack.commands),
            "input_contracts": pack.input_contracts,
            "output_contracts": pack.output_contracts,
            "units": pack.units,
            "tolerances": pack.tolerances,
            "datasets": list(pack.datasets),
            "invariants": list(pack.invariants),
            "evidence_policy": pack.evidence_policy,
            "authority_transfer": False,
        }

    def execute(self, pack_id: str, command: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pack = self._packs.get(pack_id)
        if pack is None or command not in pack.operations:
            raise EGCFError(f"domain operation is not registered: {pack_id}:{command}")
        validate_json_value(pack.input_contracts[command], inputs, f"$domain.{pack_id}.{command}.input")
        result = pack.operations[command](dict(inputs))
        validate_json_value(
            pack.output_contracts[command],
            result,
            f"$domain.{pack_id}.{command}.output",
        )
        return {
            **result,
            "domain_pack": pack.pack_id,
            "evidence_policy": pack.evidence_policy,
            "authority_transfer": False,
        }


def _grammar_parse(inputs: Dict[str, Any]) -> Dict[str, Any]:
    text = str(inputs.get("text", ""))
    mode = str(inputs.get("mode", "tokens"))
    if mode == "json":
        try:
            return {"valid": True, "tree": json.loads(text), "mode": mode}
        except json.JSONDecodeError as exc:
            return {"valid": False, "error": str(exc), "mode": mode}
    return {"valid": True, "tokens": re.findall(r"\w+|[^\w\s]", text, re.UNICODE), "mode": mode}


def _grammar_transform(inputs: Dict[str, Any]) -> Dict[str, Any]:
    text = str(inputs.get("text", ""))
    transformed = text
    for source, target in dict(inputs.get("replacements", {})).items():
        transformed = transformed.replace(str(source), str(target))
    return {"text": transformed, "changed": transformed != text}


def _grammar_compare(inputs: Dict[str, Any]) -> Dict[str, Any]:
    left = str(inputs.get("text", ""))
    right = str(inputs.get("other", ""))
    return {
        "equal": left == right,
        "left_tokens": re.findall(r"\w+", left),
        "right_tokens": re.findall(r"\w+", right),
    }


def _grammar_verify(inputs: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _grammar_parse(inputs)
    return {"verified": parsed.get("valid", False), "parse": parsed}


def grammar_pack() -> DomainPack:
    commands = ("parse", "transform", "compare", "verify")
    return DomainPack(
        name="grammar",
        version=1,
        commands=commands,
        operations={
            "parse": _grammar_parse,
            "transform": _grammar_transform,
            "compare": _grammar_compare,
            "verify": _grammar_verify,
        },
        input_contracts={
            "parse": _object_schema({"text": {"type": "string"}, "mode": {"type": "string"}}),
            "transform": _object_schema({"text": {"type": "string"}, "replacements": {"type": "object"}}),
            "compare": _object_schema({"text": {"type": "string"}, "other": {"type": "string"}}),
            "verify": _object_schema({"text": {"type": "string"}, "mode": {"type": "string"}}),
        },
        output_contracts={
            "parse": _object_schema(
                {
                    "valid": {"type": "boolean"},
                    "tree": {"type": ["object", "array", "string", "number", "boolean", "null"]},
                    "tokens": {"type": "array"},
                    "mode": {"type": "string"},
                    "error": {"type": "string"},
                }
            ),
            "transform": _object_schema({"text": {"type": "string"}, "changed": {"type": "boolean"}}),
            "compare": _object_schema(
                {
                    "equal": {"type": "boolean"},
                    "left_tokens": {"type": "array"},
                    "right_tokens": {"type": "array"},
                }
            ),
            "verify": _object_schema({"verified": {"type": "boolean"}, "parse": {"type": "object"}}),
        },
        datasets=("caller-supplied-text",),
        invariants=("input text is treated as data", "no authority transfer"),
        evidence_policy={
            "oracle": "deterministic-python-parser",
            "model_narrative_qualifies": False,
        },
    )


def _object_schema(properties: Dict[str, Any], required: tuple[str, ...] = ()) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _physics_simulate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    position = float(inputs.get("position", 0.0))
    velocity = float(inputs.get("velocity", 0.0))
    acceleration = float(inputs.get("acceleration", 0.0))
    duration = float(inputs.get("duration", 1.0))
    return {
        "simulated": True,
        "position": position + velocity * duration + 0.5 * acceleration * duration * duration,
        "velocity": velocity + acceleration * duration,
        "model": "constant acceleration",
        "units": inputs.get("units", {"position": "m", "time": "s"}),
    }


def physics_pack() -> DomainPack:
    return DomainPack(
        name="physics",
        version=1,
        commands=("simulate",),
        operations={"simulate": _physics_simulate},
        input_contracts={
            "simulate": _object_schema(
                {
                    "position": {"type": "number"},
                    "velocity": {"type": "number"},
                    "acceleration": {"type": "number"},
                    "duration": {"type": "number"},
                    "units": {"type": "object"},
                }
            )
        },
        output_contracts={
            "simulate": _object_schema(
                {
                    "simulated": {"type": "boolean"},
                    "position": {"type": "number"},
                    "velocity": {"type": "number"},
                    "model": {"type": "string"},
                    "units": {"type": "object"},
                },
                ("simulated", "position", "velocity", "model", "units"),
            )
        },
        units={"position": "caller-declared", "time": "caller-declared"},
        tolerances={"floating_point": 1e-12},
        datasets=("caller-supplied-initial-state",),
        invariants=("simulation evidence remains labelled", "no authority transfer"),
        evidence_policy={"oracle": "closed-form-constant-acceleration", "model_narrative_qualifies": False},
    )


def _geometry_operation(verb: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    points = [(float(item[0]), float(item[1])) for item in inputs.get("points", [])]
    if not points:
        return {"points": [], "status": "NO_DATA"}
    centroid = [
        sum(item[0] for item in points) / len(points),
        sum(item[1] for item in points) / len(points),
    ]
    if verb == "fit":
        mean_x, mean_y = centroid
        denominator = sum((x - mean_x) ** 2 for x, _ in points)
        slope = None if denominator == 0 else sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
        intercept = None if slope is None else mean_y - slope * mean_x
        return {"model": "line", "slope": slope, "intercept": intercept, "centroid": centroid}
    if verb == "optimise":
        return {"objective": "minimum squared distance", "point": centroid}
    distances = [math.dist(points[index], points[(index + 1) % len(points)]) for index in range(len(points))] if len(points) > 1 else []
    return {"point_count": len(points), "centroid": centroid, "closed_perimeter": sum(distances)}


def geometry_pack() -> DomainPack:
    commands = ("analyse", "fit", "optimise")
    output_properties = {
        "points": {"type": "array"}, "status": {"type": "string"}, "model": {"type": "string"},
        "slope": {"type": ["number", "null"]}, "intercept": {"type": ["number", "null"]},
        "centroid": {"type": "array"}, "objective": {"type": "string"}, "point": {"type": "array"},
        "point_count": {"type": "integer"}, "closed_perimeter": {"type": "number"},
    }
    return DomainPack(
        name="geometry", version=1, commands=commands,
        operations={command: (lambda inputs, command=command: _geometry_operation(command, inputs)) for command in commands},
        input_contracts={command: _object_schema({"points": {"type": "array"}}) for command in commands},
        output_contracts={command: _object_schema(output_properties) for command in commands},
        units={"coordinates": "caller-declared"}, tolerances={"floating_point": 1e-12},
        datasets=("caller-supplied-2d-points",),
        invariants=("input points are immutable", "no authority transfer"),
        evidence_policy={"oracle": "deterministic-analytic-geometry", "model_narrative_qualifies": False},
    )


def _vision_operation(verb: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    if verb == "segment":
        threshold = float(inputs.get("threshold", 0.5))
        pixels = inputs.get("pixels", [])
        return {"mask": [[1 if float(value) >= threshold else 0 for value in row] for row in pixels], "threshold": threshold}
    if verb == "track":
        tracks: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
        for frame_index, detections in enumerate(inputs.get("frames", [])):
            for detection_index, detection in enumerate(detections):
                tracks[str(detection.get("id", detection_index))].append({"frame": frame_index, **detection})
        return {"tracks": dict(tracks), "model": "provided identity association"}
    threshold = float(inputs.get("threshold", 0.0))
    return {"detections": [item for item in inputs.get("detections", []) if float(item.get("score", 0.0)) >= threshold], "threshold": threshold}


def vision_pack() -> DomainPack:
    commands = ("detect", "segment", "track")
    inputs = {
        "detect": _object_schema({"detections": {"type": "array"}, "threshold": {"type": "number"}}),
        "segment": _object_schema({"pixels": {"type": "array"}, "threshold": {"type": "number"}}),
        "track": _object_schema({"frames": {"type": "array"}}),
    }
    outputs = {
        "detect": _object_schema({"detections": {"type": "array"}, "threshold": {"type": "number"}}),
        "segment": _object_schema({"mask": {"type": "array"}, "threshold": {"type": "number"}}),
        "track": _object_schema({"tracks": {"type": "object"}, "model": {"type": "string"}}),
    }
    return DomainPack(
        name="vision", version=1, commands=commands,
        operations={command: (lambda values, command=command: _vision_operation(command, values)) for command in commands},
        input_contracts=inputs, output_contracts=outputs,
        datasets=("caller-supplied-detections-or-pixels",),
        tolerances={"threshold": 0.0}, invariants=("no learned inference is implied", "no authority transfer"),
        evidence_policy={"oracle": "deterministic-threshold-or-identity", "model_narrative_qualifies": False},
    )


def _robotics_operation(verb: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    grid = inputs.get("grid", [])
    start = tuple(inputs.get("start", (0, 0)))
    goal = tuple(inputs.get("goal", start))
    if verb == "verify":
        path = [tuple(item) for item in inputs.get("path", [])]
        valid = bool(path) and path[0] == start and path[-1] == goal
        for left, right in zip(path, path[1:]):
            valid = valid and abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1
        return {"verified": valid}
    frontier = deque([start])
    previous = {start: None}
    height = len(grid)
    width = len(grid[0]) if height else 0
    while frontier:
        current = frontier.popleft()
        if current == goal:
            break
        for delta in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (current[0] + delta[0], current[1] + delta[1])
            if 0 <= neighbor[0] < height and 0 <= neighbor[1] < width and not grid[neighbor[0]][neighbor[1]] and neighbor not in previous:
                previous[neighbor] = current
                frontier.append(neighbor)
    if goal not in previous:
        return {"path": [], "found": False, "simulated": True}
    path = []
    current = goal
    while current is not None:
        path.append(list(current))
        current = previous[current]
    return {"path": list(reversed(path)), "found": True, "simulated": True}


def robotics_pack() -> DomainPack:
    return DomainPack(
        name="robotics", version=1, commands=("plan", "verify"),
        operations={"plan": lambda values: _robotics_operation("plan", values), "verify": lambda values: _robotics_operation("verify", values)},
        input_contracts={
            "plan": _object_schema({"grid": {"type": "array"}, "start": {"type": "array"}, "goal": {"type": "array"}}),
            "verify": _object_schema({"grid": {"type": "array"}, "start": {"type": "array"}, "goal": {"type": "array"}, "path": {"type": "array"}}),
        },
        output_contracts={
            "plan": _object_schema({"path": {"type": "array"}, "found": {"type": "boolean"}, "simulated": {"type": "boolean"}}),
            "verify": _object_schema({"verified": {"type": "boolean"}}),
        },
        datasets=("caller-supplied-occupancy-grid",), invariants=("four-neighbour motion", "no authority transfer"),
        evidence_policy={"oracle": "deterministic-breadth-first-search", "model_narrative_qualifies": False},
    )


def _cad_operation(verb: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    vertices = list(inputs.get("vertices", []))
    faces = list(inputs.get("faces", []))
    if verb == "validate":
        invalid = [face for face in faces if len(face) < 3 or any(index < 0 or index >= len(vertices) for index in face)]
        return {"valid": not invalid, "invalid_faces": invalid}
    edges = Counter(tuple(sorted((face[index], face[(index + 1) % len(face)]))) for face in faces for index in range(len(face)) if len(face) >= 2)
    if verb == "topology":
        return {"vertices": len(vertices), "faces": len(faces), "edges": len(edges), "boundary_edges": [list(edge) for edge, count in edges.items() if count == 1]}
    if verb == "simplify":
        target_faces = max(0, int(inputs.get("target_faces", len(faces))))
        return {"vertices": vertices, "faces": faces[:target_faces], "method": "deterministic prefix candidate", "validation_required": True}
    return {"vertices": len(vertices), "faces": len(faces), "triangles": sum(max(0, len(face) - 2) for face in faces)}


def cad_pack() -> DomainPack:
    commands = ("mesh", "topology", "simplify", "validate")
    output_properties = {
        "valid": {"type": "boolean"}, "invalid_faces": {"type": "array"},
        "vertices": {"type": ["integer", "array"]}, "faces": {"type": ["integer", "array"]},
        "edges": {"type": "integer"}, "boundary_edges": {"type": "array"},
        "method": {"type": "string"}, "validation_required": {"type": "boolean"},
        "triangles": {"type": "integer"},
    }
    return DomainPack(
        name="cad", version=1, commands=commands,
        operations={command: (lambda values, command=command: _cad_operation(command, values)) for command in commands},
        input_contracts={command: _object_schema({"vertices": {"type": "array"}, "faces": {"type": "array"}, "target_faces": {"type": "integer"}}) for command in commands},
        output_contracts={command: _object_schema(output_properties) for command in commands},
        datasets=("caller-supplied-indexed-mesh",), invariants=("indices remain bounded", "no authority transfer"),
        evidence_policy={"oracle": "deterministic-mesh-accounting", "model_narrative_qualifies": False},
    )


def built_in_domain_packs() -> DomainPackRegistry:
    registry = DomainPackRegistry()
    for pack in (grammar_pack(), physics_pack(), geometry_pack(), vision_pack(), robotics_pack(), cad_pack()):
        registry.register(pack)
    return registry
