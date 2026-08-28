from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

Vec3 = tuple[float, float, float]
Mat4 = tuple[float, ...]


def _vec3(value: Iterable[float]) -> Vec3:
    items = tuple(float(component) for component in value)
    if len(items) != 3:
        raise ValueError("expected 3-vector")
    return items  # type: ignore[return-value]


def add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def mul(a: Vec3, scalar: float) -> Vec3:
    return a[0] * scalar, a[1] * scalar, a[2] * scalar


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3, *, fallback: Vec3 = (0.0, 0.0, 1.0)) -> Vec3:
    magnitude = length(a)
    if magnitude <= 1e-12 or not math.isfinite(magnitude):
        return fallback
    inverse = 1.0 / magnitude
    return a[0] * inverse, a[1] * inverse, a[2] * inverse


def identity() -> Mat4:
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def mat_mul(left: Mat4, right: Mat4) -> Mat4:
    if len(left) != 16 or len(right) != 16:
        raise ValueError("matrices must be 4x4")
    values = [0.0] * 16
    for column in range(4):
        for row in range(4):
            values[column * 4 + row] = sum(
                left[k * 4 + row] * right[column * 4 + k]
                for k in range(4)
            )
    return tuple(values)


def translation(x: float, y: float, z: float) -> Mat4:
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        float(x), float(y), float(z), 1.0,
    )


def scale(x: float, y: float, z: float) -> Mat4:
    return (
        float(x), 0.0, 0.0, 0.0,
        0.0, float(y), 0.0, 0.0,
        0.0, 0.0, float(z), 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def rotation_x(angle: float) -> Mat4:
    c = math.cos(angle)
    s = math.sin(angle)
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, c, s, 0.0,
        0.0, -s, c, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def rotation_z(angle: float) -> Mat4:
    c = math.cos(angle)
    s = math.sin(angle)
    return (
        c, s, 0.0, 0.0,
        -s, c, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def perspective(fov_y_radians: float, aspect: float, near: float, far: float) -> Mat4:
    if not 0.0 < fov_y_radians < math.pi:
        raise ValueError("perspective field of view must lie in (0, pi)")
    if aspect <= 0.0 or near <= 0.0 or far <= near:
        raise ValueError("invalid perspective bounds")
    f = 1.0 / math.tan(fov_y_radians / 2.0)
    return (
        f / aspect, 0.0, 0.0, 0.0,
        0.0, f, 0.0, 0.0,
        0.0, 0.0, (far + near) / (near - far), -1.0,
        0.0, 0.0, (2.0 * far * near) / (near - far), 0.0,
    )


def orthographic(left: float, right: float, bottom: float, top: float, near: float, far: float) -> Mat4:
    if right == left or top == bottom or far == near:
        raise ValueError("degenerate orthographic bounds")
    return (
        2.0 / (right - left), 0.0, 0.0, 0.0,
        0.0, 2.0 / (top - bottom), 0.0, 0.0,
        0.0, 0.0, -2.0 / (far - near), 0.0,
        -(right + left) / (right - left),
        -(top + bottom) / (top - bottom),
        -(far + near) / (far - near),
        1.0,
    )


def look_at(eye: Vec3, target: Vec3, up: Vec3) -> Mat4:
    forward = normalize(sub(target, eye), fallback=(0.0, 1.0, 0.0))
    side = normalize(cross(forward, up), fallback=(1.0, 0.0, 0.0))
    true_up = cross(side, forward)
    return (
        side[0], true_up[0], -forward[0], 0.0,
        side[1], true_up[1], -forward[1], 0.0,
        side[2], true_up[2], -forward[2], 0.0,
        -dot(side, eye), -dot(true_up, eye), dot(forward, eye), 1.0,
    )


def normalization_matrix(minimum: Vec3, maximum: Vec3) -> Mat4:
    center = tuple((minimum[index] + maximum[index]) / 2.0 for index in range(3))
    extent = max(maximum[index] - minimum[index] for index in range(3)) or 1.0
    factor = 2.0 / extent
    return mat_mul(
        scale(factor, factor, factor),
        translation(-center[0], -center[1], -center[2]),
    )


@dataclass(frozen=True)
class RenderCamera:
    view: str = "perspective"
    yaw: float = math.radians(-25.0)
    pitch: float = math.radians(20.0)
    distance: float = 3.6
    fov_y_degrees: float = 45.0
    ortho_scale: float = 1.25

    def matrices(self, aspect: float) -> tuple[Mat4, Mat4]:
        view_name = self.view.casefold()
        if view_name == "perspective":
            pitch = max(math.radians(-89.0), min(math.radians(89.0), self.pitch))
            distance = max(1.2, float(self.distance))
            eye = (
                distance * math.cos(pitch) * math.sin(self.yaw),
                -distance * math.cos(pitch) * math.cos(self.yaw),
                distance * math.sin(pitch),
            )
            view_matrix = look_at(eye, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            projection = perspective(
                math.radians(max(10.0, min(120.0, self.fov_y_degrees))),
                aspect,
                0.05,
                50.0,
            )
            return view_matrix, projection

        distance = 4.0
        if view_name == "front":
            eye, up = (0.0, -distance, 0.0), (0.0, 0.0, 1.0)
        elif view_name == "top":
            eye, up = (0.0, 0.0, distance), (0.0, 1.0, 0.0)
        elif view_name == "side":
            eye, up = (distance, 0.0, 0.0), (0.0, 0.0, 1.0)
        else:
            raise ValueError(f"unknown camera view: {self.view}")
        view_matrix = look_at(eye, (0.0, 0.0, 0.0), up)
        span_y = max(0.1, float(self.ortho_scale))
        span_x = span_y * max(0.1, aspect)
        projection = orthographic(-span_x, span_x, -span_y, span_y, -10.0, 10.0)
        return view_matrix, projection
