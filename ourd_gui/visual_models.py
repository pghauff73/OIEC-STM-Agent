from __future__ import annotations

import json
import math
import struct
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


MAX_MESH_VERTICES = 100_000
MAX_MESH_EDGES = 200_000


Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class MeshData:
    name: str
    vertices: tuple[Vec3, ...]
    edges: tuple[tuple[int, int], ...]
    source_path: str = ""

    def bounding_box(self) -> tuple[Vec3, Vec3]:
        if not self.vertices:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        minimum = tuple(min(vertex[index] for vertex in self.vertices) for index in range(3))
        maximum = tuple(max(vertex[index] for vertex in self.vertices) for index in range(3))
        return minimum, maximum


@dataclass(frozen=True)
class BezierCurve3D:
    curve_id: str
    name: str
    control_points: tuple[Vec3, Vec3, Vec3, Vec3]

    @classmethod
    def default(cls, name: str = "Curve 1") -> "BezierCurve3D":
        return cls(
            curve_id=str(uuid.uuid4()),
            name=name,
            control_points=(
                (-1.5, 0.0, 0.0),
                (-0.5, 1.0, 0.75),
                (0.5, -1.0, 0.75),
                (1.5, 0.0, 0.0),
            ),
        )

    def with_point(self, index: int, value: Vec3) -> "BezierCurve3D":
        if index not in range(4):
            raise IndexError(index)
        points = list(self.control_points)
        points[index] = tuple(float(component) for component in value)  # type: ignore[assignment]
        return BezierCurve3D(self.curve_id, self.name, tuple(points))  # type: ignore[arg-type]


@dataclass
class BezierScene:
    curves: list[BezierCurve3D] = field(default_factory=list)
    revision: int = 0

    def clone(self) -> "BezierScene":
        return BezierScene(curves=list(self.curves), revision=self.revision)

    def to_json(self) -> str:
        payload = {
            "schema_version": 1,
            "revision": self.revision,
            "curves": [
                {
                    "curve_id": curve.curve_id,
                    "name": curve.name,
                    "control_points": [list(point) for point in curve.control_points],
                }
                for curve in self.curves
            ],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "BezierScene":
        payload = json.loads(text)
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported 3D Bezier scene schema")
        curves: list[BezierCurve3D] = []
        for raw in payload.get("curves", []):
            if not isinstance(raw, dict):
                continue
            points = raw.get("control_points")
            if not isinstance(points, list) or len(points) != 4:
                raise ValueError("each cubic Bezier curve requires four control points")
            converted: list[Vec3] = []
            for point in points:
                if not isinstance(point, list) or len(point) != 3:
                    raise ValueError("Bezier control point must contain x, y, z")
                converted.append(tuple(float(value) for value in point))  # type: ignore[arg-type]
            curves.append(
                BezierCurve3D(
                    curve_id=str(raw.get("curve_id") or uuid.uuid4()),
                    name=str(raw.get("name") or f"Curve {len(curves) + 1}"),
                    control_points=tuple(converted),  # type: ignore[arg-type]
                )
            )
        return cls(curves=curves, revision=max(0, int(payload.get("revision", 0))))


def cubic_bezier_point(curve: BezierCurve3D, t: float) -> Vec3:
    t = max(0.0, min(float(t), 1.0))
    u = 1.0 - t
    weights = (u * u * u, 3.0 * u * u * t, 3.0 * u * t * t, t * t * t)
    return tuple(
        sum(weights[index] * curve.control_points[index][axis] for index in range(4))
        for axis in range(3)
    )  # type: ignore[return-value]


def sample_bezier(curve: BezierCurve3D, samples: int = 48) -> tuple[Vec3, ...]:
    samples = max(2, min(int(samples), 512))
    return tuple(cubic_bezier_point(curve, index / (samples - 1)) for index in range(samples))


def _unique_edges(edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    normalized = set()
    for left, right in edges:
        if left == right or left < 0 or right < 0:
            continue
        normalized.add((left, right) if left < right else (right, left))
        if len(normalized) >= MAX_MESH_EDGES:
            break
    return tuple(sorted(normalized))


def load_obj(path: Path) -> MeshData:
    vertices: list[Vec3] = []
    edges: list[tuple[int, int]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = raw.strip().split()
        if not fields:
            continue
        if fields[0] == "v" and len(fields) >= 4:
            if len(vertices) >= MAX_MESH_VERTICES:
                break
            try:
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
            except ValueError:
                continue
        elif fields[0] == "f" and len(fields) >= 3:
            face: list[int] = []
            for token in fields[1:]:
                head = token.split("/", 1)[0]
                try:
                    index = int(head)
                except ValueError:
                    continue
                if index < 0:
                    index = len(vertices) + index
                else:
                    index -= 1
                if 0 <= index < len(vertices):
                    face.append(index)
            if len(face) >= 2:
                for index, left in enumerate(face):
                    edges.append((left, face[(index + 1) % len(face)]))
    return MeshData(path.name, tuple(vertices), _unique_edges(edges), str(path))


def load_stl(path: Path) -> MeshData:
    content = path.read_bytes()
    vertices: list[Vec3] = []
    edges: list[tuple[int, int]] = []
    if len(content) >= 84:
        triangle_count = struct.unpack_from("<I", content, 80)[0]
        expected_size = 84 + triangle_count * 50
    else:
        triangle_count = 0
        expected_size = -1
    if expected_size == len(content):
        for triangle in range(min(triangle_count, MAX_MESH_VERTICES // 3)):
            base = 84 + triangle * 50 + 12
            indices = []
            for offset in range(3):
                vertex = struct.unpack_from("<fff", content, base + offset * 12)
                indices.append(len(vertices))
                vertices.append(tuple(float(value) for value in vertex))  # type: ignore[arg-type]
            edges.extend(
                (
                    (indices[0], indices[1]),
                    (indices[1], indices[2]),
                    (indices[2], indices[0]),
                )
            )
    else:
        triangle: list[int] = []
        for raw in content.decode("utf-8", errors="replace").splitlines():
            fields = raw.strip().split()
            if fields[:1] != ["vertex"] or len(fields) < 4:
                continue
            if len(vertices) >= MAX_MESH_VERTICES:
                break
            try:
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
            except ValueError:
                continue
            triangle.append(len(vertices) - 1)
            if len(triangle) == 3:
                edges.extend(
                    (
                        (triangle[0], triangle[1]),
                        (triangle[1], triangle[2]),
                        (triangle[2], triangle[0]),
                    )
                )
                triangle = []
    return MeshData(path.name, tuple(vertices), _unique_edges(edges), str(path))


def load_mesh(path: Path) -> MeshData:
    suffix = path.suffix.casefold()
    if suffix == ".obj":
        return load_obj(path)
    if suffix == ".stl":
        return load_stl(path)
    raise ValueError(f"unsupported 3D mesh type: {suffix or '(none)'}")


def rotate_point(point: Vec3, yaw: float, pitch: float) -> Vec3:
    x, y, z = point
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    x1 = cy * x + sy * z
    z1 = -sy * x + cy * z
    y1 = cp * y - sp * z1
    z2 = sp * y + cp * z1
    return x1, y1, z2


def normalize_vertices(vertices: Sequence[Vec3]) -> tuple[Vec3, ...]:
    if not vertices:
        return ()
    minimum = [min(vertex[index] for vertex in vertices) for index in range(3)]
    maximum = [max(vertex[index] for vertex in vertices) for index in range(3)]
    center = [(minimum[index] + maximum[index]) / 2.0 for index in range(3)]
    extent = max(maximum[index] - minimum[index] for index in range(3)) or 1.0
    return tuple(
        tuple((vertex[index] - center[index]) / extent * 2.0 for index in range(3))
        for vertex in vertices
    )  # type: ignore[return-value]
