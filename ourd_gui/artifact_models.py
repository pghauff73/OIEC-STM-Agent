from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ArtifactInspection:
    kind: str
    preview_mode: str
    geometry: Mapping[str, Any]
    warnings: tuple[str, ...] = ()


def _bbox(vertices: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    if not vertices:
        return {}
    return {
        "minimum": [min(vertex[index] for vertex in vertices) for index in range(3)],
        "maximum": [max(vertex[index] for vertex in vertices) for index in range(3)],
    }


def inspect_obj(content: bytes, *, max_lines: int = 200_000) -> ArtifactInspection:
    vertices: list[tuple[float, float, float]] = []
    faces = normals = texture_coordinates = 0
    warnings: list[str] = []
    for index, raw in enumerate(content.decode("utf-8", errors="replace").splitlines()):
        if index >= max_lines:
            warnings.append("OBJ line limit reached")
            break
        fields = raw.strip().split()
        if not fields:
            continue
        if fields[0] == "v" and len(fields) >= 4:
            try:
                vertices.append(tuple(float(value) for value in fields[1:4]))
            except ValueError:
                warnings.append(f"invalid vertex at line {index + 1}")
        elif fields[0] == "f":
            faces += 1
        elif fields[0] == "vn":
            normals += 1
        elif fields[0] == "vt":
            texture_coordinates += 1
    return ArtifactInspection(
        kind="OBJ",
        preview_mode="geometry-metadata",
        geometry={
            "vertices": len(vertices),
            "faces": faces,
            "normals": normals,
            "texture_coordinates": texture_coordinates,
            "bounding_box": _bbox(vertices),
        },
        warnings=tuple(dict.fromkeys(warnings)),
    )


def inspect_stl(content: bytes) -> ArtifactInspection:
    warnings: list[str] = []
    vertices: list[tuple[float, float, float]] = []
    triangles = 0
    expected_binary_size = None
    if len(content) >= 84:
        triangles = struct.unpack_from("<I", content, 80)[0]
        expected_binary_size = 84 + triangles * 50
    if expected_binary_size == len(content):
        for index in range(triangles):
            offset = 84 + index * 50 + 12
            for vertex_index in range(3):
                vertices.append(struct.unpack_from("<fff", content, offset + vertex_index * 12))
        mode = "binary"
    else:
        mode = "ascii"
        triangles = 0
        for raw in content.decode("utf-8", errors="replace").splitlines():
            fields = raw.strip().split()
            if fields[:1] == ["facet"]:
                triangles += 1
            if fields[:1] == ["vertex"] and len(fields) >= 4:
                try:
                    vertices.append(tuple(float(value) for value in fields[1:4]))
                except ValueError:
                    warnings.append("invalid ASCII STL vertex")
    return ArtifactInspection(
        kind="STL",
        preview_mode="geometry-metadata",
        geometry={
            "encoding": mode,
            "triangles": triangles,
            "vertices_observed": len(vertices),
            "bounding_box": _bbox(vertices),
        },
        warnings=tuple(dict.fromkeys(warnings)),
    )


def inspect_ply(content: bytes) -> ArtifactInspection:
    text = content[:200_000].decode("ascii", errors="replace")
    header, separator, _ = text.partition("end_header")
    warnings: list[str] = []
    if not separator:
        warnings.append("PLY end_header not found within inspection bound")
    elements: dict[str, int] = {}
    encoding = "unknown"
    properties: list[str] = []
    for line in header.splitlines():
        fields = line.strip().split()
        if fields[:1] == ["format"] and len(fields) >= 2:
            encoding = fields[1]
        elif fields[:1] == ["element"] and len(fields) >= 3:
            try:
                elements[fields[1]] = int(fields[2])
            except ValueError:
                warnings.append(f"invalid PLY element count: {line}")
        elif fields[:1] == ["property"]:
            properties.append(" ".join(fields[1:]))
    return ArtifactInspection(
        kind="PLY",
        preview_mode="geometry-metadata",
        geometry={
            "encoding": encoding,
            "elements": elements,
            "properties": properties,
        },
        warnings=tuple(dict.fromkeys(warnings)),
    )


def inspect_artifact(media_type: str, path: Path, content: bytes) -> ArtifactInspection:
    suffix = path.suffix.casefold()
    media = media_type.casefold()
    if suffix == ".obj" or media in {"model/obj", "text/obj"}:
        return inspect_obj(content)
    if suffix == ".stl" or media in {"model/stl", "application/sla"}:
        return inspect_stl(content)
    if suffix == ".ply" or media in {"model/ply", "application/ply"}:
        return inspect_ply(content)
    if media == "image/svg+xml" or suffix == ".svg":
        return ArtifactInspection("SVG", "text", {}, ("active SVG rendering disabled",))
    if media.startswith("image/") or suffix in {".png", ".gif", ".jpg", ".jpeg"}:
        return ArtifactInspection("image", "image", {})
    if media.startswith("text/") or media in {
        "application/json",
        "application/xml",
        "application/yaml",
    }:
        return ArtifactInspection("text", "text", {})
    return ArtifactInspection("binary", "metadata-only", {})


def compare_geometry(
    left: ArtifactInspection,
    right: ArtifactInspection,
) -> dict[str, Any]:
    keys = sorted(set(left.geometry).union(right.geometry))
    differences: dict[str, Any] = {}
    for key in keys:
        left_value = left.geometry.get(key)
        right_value = right.geometry.get(key)
        if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
            differences[key] = {
                "before": left_value,
                "after": right_value,
                "delta": right_value - left_value,
            }
        elif left_value != right_value:
            differences[key] = {"before": left_value, "after": right_value}
    return {
        "before_kind": left.kind,
        "after_kind": right.kind,
        "differences": differences,
        "warnings": [*left.warnings, *right.warnings],
    }
