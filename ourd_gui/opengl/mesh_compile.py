from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..mesh_formats import Color, MeshData, MeshFace, Vec2, Vec3
from .math3d import cross, length, normalize, sub

MAX_GPU_VERTICES = 1_000_000
MAX_GPU_TRIANGLES = 2_000_000

ColorF = tuple[float, float, float, float]


@dataclass(frozen=True)
class RenderVertex:
    position: Vec3
    normal: Vec3
    uv: Vec2
    color: ColorF


@dataclass(frozen=True)
class CompiledMaterial:
    name: str
    base_color: ColorF
    texture_path: str = ""


@dataclass(frozen=True)
class DrawBatch:
    material_index: int
    indices: tuple[int, ...]

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3


@dataclass(frozen=True)
class CompiledMesh:
    vertices: tuple[RenderVertex, ...]
    batches: tuple[DrawBatch, ...]
    materials: tuple[CompiledMaterial, ...]
    minimum: Vec3
    maximum: Vec3
    warnings: tuple[str, ...] = ()

    @property
    def triangle_count(self) -> int:
        return sum(batch.triangle_count for batch in self.batches)

    def vertex_bytes(self) -> bytes:
        payload = bytearray()
        for vertex in self.vertices:
            payload.extend(
                struct.pack(
                    "<12f",
                    vertex.position[0],
                    vertex.position[1],
                    vertex.position[2],
                    vertex.normal[0],
                    vertex.normal[1],
                    vertex.normal[2],
                    vertex.uv[0],
                    vertex.uv[1],
                    vertex.color[0],
                    vertex.color[1],
                    vertex.color[2],
                    vertex.color[3],
                )
            )
        return bytes(payload)


@dataclass(frozen=True)
class TriangulationResult:
    triangles: tuple[tuple[int, int, int], ...]
    fallback_used: bool = False


def _color_f(color: Color | None) -> ColorF:
    if color is None:
        return 1.0, 1.0, 1.0, 1.0
    return tuple(max(0.0, min(1.0, component / 255.0)) for component in color)  # type: ignore[return-value]


def _face_normal(points: Sequence[Vec3]) -> Vec3:
    if len(points) < 3:
        return 0.0, 0.0, 1.0
    nx = ny = nz = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        nx += (current[1] - following[1]) * (current[2] + following[2])
        ny += (current[2] - following[2]) * (current[0] + following[0])
        nz += (current[0] - following[0]) * (current[1] + following[1])
    candidate = (nx, ny, nz)
    if length(candidate) > 1e-12:
        return normalize(candidate)
    origin = points[0]
    for index in range(1, len(points) - 1):
        candidate = cross(sub(points[index], origin), sub(points[index + 1], origin))
        if length(candidate) > 1e-12:
            return normalize(candidate)
    return 0.0, 0.0, 1.0


def _dominant_projection(points: Sequence[Vec3]) -> tuple[tuple[float, float], ...]:
    normal = _face_normal(points)
    axis = max(range(3), key=lambda index: abs(normal[index]))
    if axis == 0:
        return tuple((point[1], point[2]) for point in points)
    if axis == 1:
        return tuple((point[0], point[2]) for point in points)
    return tuple((point[0], point[1]) for point in points)


def _signed_area(points: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _cross2(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> bool:
    d1 = _cross2(point, a, b)
    d2 = _cross2(point, b, c)
    d3 = _cross2(point, c, a)
    has_negative = d1 < -1e-10 or d2 < -1e-10 or d3 < -1e-10
    has_positive = d1 > 1e-10 or d2 > 1e-10 or d3 > 1e-10
    return not (has_negative and has_positive)


def triangulate_polygon(points: Sequence[Vec3]) -> TriangulationResult:
    count = len(points)
    if count < 3:
        return TriangulationResult(())
    if count == 3:
        return TriangulationResult(((0, 1, 2),))

    projected = _dominant_projection(points)
    area = _signed_area(projected)
    if abs(area) <= 1e-12:
        return TriangulationResult(
            tuple((0, index, index + 1) for index in range(1, count - 1)),
            fallback_used=True,
        )
    orientation = 1.0 if area > 0.0 else -1.0
    remaining = list(range(count))
    triangles: list[tuple[int, int, int]] = []
    guard = count * count

    while len(remaining) > 3 and guard > 0:
        guard -= 1
        ear_found = False
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            a, b, c = projected[previous], projected[current], projected[following]
            if orientation * _cross2(a, b, c) <= 1e-12:
                continue
            if any(
                candidate not in {previous, current, following}
                and _point_in_triangle(projected[candidate], a, b, c)
                for candidate in remaining
            ):
                continue
            triangles.append((previous, current, following))
            del remaining[position]
            ear_found = True
            break
        if not ear_found:
            return TriangulationResult(
                tuple((0, index, index + 1) for index in range(1, count - 1)),
                fallback_used=True,
            )

    if len(remaining) == 3:
        triangles.append((remaining[0], remaining[1], remaining[2]))
    return TriangulationResult(tuple(triangles))


def _smooth_normals(mesh: MeshData) -> tuple[Vec3, ...]:
    accumulated = [[0.0, 0.0, 0.0] for _ in mesh.vertices]
    for face in mesh.faces:
        valid = [index for index in face.vertex_indices if 0 <= index < len(mesh.vertices)]
        if len(valid) < 3:
            continue
        points = [mesh.vertices[index] for index in valid]
        normal = _face_normal(points)
        for vertex_index in valid:
            accumulated[vertex_index][0] += normal[0]
            accumulated[vertex_index][1] += normal[1]
            accumulated[vertex_index][2] += normal[2]
    return tuple(normalize(tuple(value)) for value in accumulated)  # type: ignore[arg-type]


def _resolve_texture(mesh: MeshData, raw: str) -> str:
    if not raw:
        return ""
    source_parent = Path(mesh.source_path).resolve().parent if mesh.source_path else Path(".")
    candidate = (source_parent / raw).resolve()
    if candidate.is_file():
        return str(candidate)
    raw_name = Path(raw).name.casefold()
    for texture in mesh.texture_paths:
        path = Path(texture)
        if path.name.casefold() == raw_name and path.is_file():
            return str(path.resolve())
    return ""


def _materials(mesh: MeshData) -> tuple[CompiledMaterial, ...]:
    values = [CompiledMaterial("__default__", (0.8, 0.8, 0.8, 1.0), "")]
    for material in mesh.materials:
        values.append(
            CompiledMaterial(
                material.name,
                _color_f(material.diffuse),
                _resolve_texture(mesh, material.diffuse_texture),
            )
        )
    return tuple(values)


def _bounds(vertices: Sequence[Vec3]) -> tuple[Vec3, Vec3]:
    if not vertices:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    minimum = tuple(min(vertex[axis] for vertex in vertices) for axis in range(3))
    maximum = tuple(max(vertex[axis] for vertex in vertices) for axis in range(3))
    return minimum, maximum  # type: ignore[return-value]


def compile_mesh(mesh: MeshData) -> CompiledMesh:
    if len(mesh.vertices) > MAX_GPU_VERTICES:
        raise ValueError(f"mesh exceeds GPU compile vertex limit ({MAX_GPU_VERTICES})")
    warnings = list(mesh.warnings)
    materials = _materials(mesh)
    material_lookup = {material.name: index for index, material in enumerate(materials)}
    normals = _smooth_normals(mesh)
    vertex_lookup: dict[tuple[int, int, int], int] = {}
    vertices: list[RenderVertex] = []
    batches: dict[int, list[int]] = {}
    triangle_count = 0

    faces: Iterable[MeshFace]
    if mesh.faces:
        faces = mesh.faces
    else:
        warnings.append("mesh has no polygon faces; OpenGL triangle rendering is empty")
        faces = ()

    for face_index, face in enumerate(faces):
        corner_vertex_indices = tuple(
            index for index in face.vertex_indices if 0 <= index < len(mesh.vertices)
        )
        if len(corner_vertex_indices) < 3:
            warnings.append(f"face {face_index} has fewer than three valid vertices")
            continue
        points = tuple(mesh.vertices[index] for index in corner_vertex_indices)
        triangulation = triangulate_polygon(points)
        if triangulation.fallback_used:
            warnings.append(f"face {face_index} used fan triangulation fallback")
        material_index = material_lookup.get(face.material, 0)
        batch = batches.setdefault(material_index, [])

        texcoord_indices = face.texcoord_indices
        if texcoord_indices and len(texcoord_indices) != len(face.vertex_indices):
            warnings.append(f"face {face_index} UV index count does not match vertex count")
            texcoord_indices = ()

        original_to_valid: list[int] = []
        for original_corner, vertex_index in enumerate(face.vertex_indices):
            if 0 <= vertex_index < len(mesh.vertices):
                original_to_valid.append(original_corner)
        if len(original_to_valid) != len(corner_vertex_indices):
            warnings.append(f"face {face_index} contained invalid vertex indices")

        gpu_corners: list[int] = []
        for valid_corner, vertex_index in enumerate(corner_vertex_indices):
            original_corner = original_to_valid[valid_corner]
            texcoord_index = -1
            if texcoord_indices:
                candidate = texcoord_indices[original_corner]
                if 0 <= candidate < len(mesh.texcoords):
                    texcoord_index = candidate
            key = (vertex_index, texcoord_index, material_index)
            gpu_index = vertex_lookup.get(key)
            if gpu_index is None:
                uv = mesh.texcoords[texcoord_index] if texcoord_index >= 0 else (0.0, 0.0)
                vertex_color = (
                    mesh.vertex_colors[vertex_index]
                    if vertex_index < len(mesh.vertex_colors)
                    else None
                )
                gpu_index = len(vertices)
                if gpu_index >= MAX_GPU_VERTICES:
                    raise ValueError("expanded GPU vertex limit exceeded")
                vertex_lookup[key] = gpu_index
                vertices.append(
                    RenderVertex(
                        mesh.vertices[vertex_index],
                        normals[vertex_index] if vertex_index < len(normals) else (0.0, 0.0, 1.0),
                        uv,
                        _color_f(vertex_color),
                    )
                )
            gpu_corners.append(gpu_index)

        for a, b, c in triangulation.triangles:
            if max(a, b, c) >= len(gpu_corners):
                continue
            batch.extend((gpu_corners[a], gpu_corners[b], gpu_corners[c]))
            triangle_count += 1
            if triangle_count > MAX_GPU_TRIANGLES:
                raise ValueError(f"mesh exceeds GPU triangle limit ({MAX_GPU_TRIANGLES})")

    minimum, maximum = _bounds(mesh.vertices)
    draw_batches = tuple(
        DrawBatch(material_index, tuple(indices))
        for material_index, indices in sorted(batches.items())
        if indices
    )
    return CompiledMesh(
        tuple(vertices),
        draw_batches,
        materials,
        minimum,
        maximum,
        tuple(dict.fromkeys(warnings)),
    )
