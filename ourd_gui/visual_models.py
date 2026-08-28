from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from typing import Sequence

from .mesh_formats import MeshData, Vec3, load_mesh, load_obj, load_ply, load_stl


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


__all__ = [
    "BezierCurve3D",
    "BezierScene",
    "MeshData",
    "Vec3",
    "cubic_bezier_point",
    "load_mesh",
    "load_obj",
    "load_ply",
    "load_stl",
    "normalize_vertices",
    "rotate_point",
    "sample_bezier",
]
