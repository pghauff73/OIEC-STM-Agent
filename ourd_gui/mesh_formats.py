from __future__ import annotations

import math
import shlex
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

MAX_MESH_VERTICES = 100_000
MAX_MESH_EDGES = 200_000
MAX_MESH_FACES = 100_000
MAX_PLY_LIST_ITEMS = 1_000_000

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Color = tuple[int, int, int, int]


@dataclass(frozen=True)
class MeshMaterial:
    name: str
    diffuse: Color = (204, 204, 204, 255)
    diffuse_texture: str = ""


@dataclass(frozen=True)
class MeshFace:
    vertex_indices: tuple[int, ...]
    texcoord_indices: tuple[int, ...] = ()
    material: str = ""


@dataclass(frozen=True)
class MeshData:
    name: str
    vertices: tuple[Vec3, ...]
    edges: tuple[tuple[int, int], ...]
    faces: tuple[MeshFace, ...] = ()
    texcoords: tuple[Vec2, ...] = ()
    vertex_colors: tuple[Color | None, ...] = ()
    materials: tuple[MeshMaterial, ...] = ()
    texture_paths: tuple[str, ...] = ()
    source_path: str = ""
    format_name: str = ""
    encoding: str = ""
    warnings: tuple[str, ...] = ()

    def bounding_box(self) -> tuple[Vec3, Vec3]:
        if not self.vertices:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        minimum = tuple(min(vertex[index] for vertex in self.vertices) for index in range(3))
        maximum = tuple(max(vertex[index] for vertex in self.vertices) for index in range(3))
        return minimum, maximum  # type: ignore[return-value]

    @property
    def has_texture_mapping(self) -> bool:
        return bool(self.texcoords and any(face.texcoord_indices for face in self.faces))

    @property
    def has_vertex_colors(self) -> bool:
        return any(color is not None for color in self.vertex_colors)


@dataclass(frozen=True)
class MeshDependencyDiscovery:
    files: tuple[Path, ...] = ()
    textures: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()


def _unique_edges(edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    normalized: set[tuple[int, int]] = set()
    for left, right in edges:
        if left == right or left < 0 or right < 0:
            continue
        normalized.add((left, right) if left < right else (right, left))
        if len(normalized) >= MAX_MESH_EDGES:
            break
    return tuple(sorted(normalized))


def _edges_from_faces(faces: Sequence[MeshFace]) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for face in faces:
        indices = face.vertex_indices
        if len(indices) < 2:
            continue
        for index, left in enumerate(indices):
            edges.append((left, indices[(index + 1) % len(indices)]))
    return _unique_edges(edges)


def _to_color(values: Sequence[float | int]) -> Color:
    normalized: list[int] = []
    for raw in list(values)[:4]:
        value = float(raw)
        if 0.0 <= value <= 1.0:
            value *= 255.0
        normalized.append(max(0, min(255, int(round(value)))))
    while len(normalized) < 4:
        normalized.append(255)
    return normalized[0], normalized[1], normalized[2], normalized[3]


def _safe_dependency(base: Path, raw: str) -> tuple[Path | None, str]:
    value = raw.strip().strip('"').strip("'")
    if not value:
        return None, "empty dependency path"
    candidate = (base / value).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None, f"dependency outside mesh directory skipped: {value}"
    if not candidate.is_file():
        return None, f"dependency missing: {value}"
    return candidate, ""


def _map_filename(fields: list[str]) -> str:
    if not fields:
        return ""
    # Wavefront map options precede the filename. The final token is the common,
    # interoperable filename position and supports quoted spaces via shlex.
    return fields[-1]


def parse_mtl(path: Path) -> tuple[tuple[MeshMaterial, ...], tuple[str, ...]]:
    materials: list[MeshMaterial] = []
    warnings: list[str] = []
    current_name = ""
    diffuse: Color = (204, 204, 204, 255)
    texture = ""

    def flush() -> None:
        nonlocal current_name, diffuse, texture
        if current_name:
            materials.append(MeshMaterial(current_name, diffuse, texture))
        current_name = ""
        diffuse = (204, 204, 204, 255)
        texture = ""

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return (), (f"MTL unreadable: {exc}",)
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            fields = shlex.split(stripped, comments=True, posix=True)
        except ValueError:
            fields = stripped.split()
        if not fields:
            continue
        key = fields[0]
        if key == "newmtl":
            flush()
            current_name = " ".join(fields[1:]).strip() or "unnamed"
        elif key == "Kd" and len(fields) >= 4:
            try:
                diffuse = _to_color(tuple(float(value) for value in fields[1:4]))
            except ValueError:
                warnings.append(f"invalid Kd in {path.name}: {stripped}")
        elif key == "d" and len(fields) >= 2:
            try:
                alpha = max(0, min(255, int(round(float(fields[1]) * 255.0))))
                diffuse = diffuse[:3] + (alpha,)
            except ValueError:
                warnings.append(f"invalid dissolve in {path.name}: {stripped}")
        elif key == "Tr" and len(fields) >= 2:
            try:
                alpha = max(0, min(255, int(round((1.0 - float(fields[1])) * 255.0))))
                diffuse = diffuse[:3] + (alpha,)
            except ValueError:
                warnings.append(f"invalid transparency in {path.name}: {stripped}")
        elif key == "map_Kd" and len(fields) >= 2:
            texture = _map_filename(fields[1:])
    flush()
    return tuple(materials), tuple(dict.fromkeys(warnings))


def discover_mesh_dependencies(path: Path) -> MeshDependencyDiscovery:
    path = path.resolve()
    suffix = path.suffix.casefold()
    files: list[Path] = []
    textures: list[Path] = []
    warnings: list[str] = []
    if suffix == ".obj":
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return MeshDependencyDiscovery(warnings=(f"OBJ dependency scan failed: {exc}",))
        for raw in lines:
            fields = raw.strip().split()
            if fields[:1] != ["mtllib"]:
                continue
            for name in fields[1:]:
                material_path, warning = _safe_dependency(path.parent, name)
                if warning:
                    warnings.append(warning)
                if material_path is None:
                    continue
                files.append(material_path)
                materials, material_warnings = parse_mtl(material_path)
                warnings.extend(material_warnings)
                for material in materials:
                    if not material.diffuse_texture:
                        continue
                    texture_path, texture_warning = _safe_dependency(
                        material_path.parent,
                        material.diffuse_texture,
                    )
                    if texture_warning:
                        warnings.append(texture_warning)
                    if texture_path is not None:
                        textures.append(texture_path)
                        files.append(texture_path)
    elif suffix == ".ply":
        try:
            header, _ = _ply_header(path.read_bytes())
        except (OSError, ValueError) as exc:
            return MeshDependencyDiscovery(warnings=(f"PLY dependency scan failed: {exc}",))
        for comment in header.comments:
            fields = comment.strip().split(maxsplit=1)
            if len(fields) != 2 or fields[0].casefold() not in {
                "texturefile",
                "texture_file",
            }:
                continue
            texture_path, warning = _safe_dependency(path.parent, fields[1])
            if warning:
                warnings.append(warning)
            if texture_path is not None:
                textures.append(texture_path)
                files.append(texture_path)
    return MeshDependencyDiscovery(
        files=tuple(dict.fromkeys(files)),
        textures=tuple(dict.fromkeys(textures)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def load_obj(path: Path) -> MeshData:
    vertices: list[Vec3] = []
    vertex_colors: list[Color | None] = []
    texcoords: list[Vec2] = []
    faces: list[MeshFace] = []
    materials: dict[str, MeshMaterial] = {}
    warnings: list[str] = []
    current_material = ""
    texture_paths: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read OBJ: {exc}") from exc
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        key = fields[0]
        if key == "mtllib":
            for raw_name in fields[1:]:
                material_path, warning = _safe_dependency(path.parent, raw_name)
                if warning:
                    warnings.append(warning)
                if material_path is None:
                    continue
                parsed, parsed_warnings = parse_mtl(material_path)
                warnings.extend(parsed_warnings)
                for material in parsed:
                    texture_path = material.diffuse_texture
                    if texture_path:
                        resolved, texture_warning = _safe_dependency(
                            material_path.parent,
                            texture_path,
                        )
                        if texture_warning:
                            warnings.append(texture_warning)
                        texture_path = str(resolved) if resolved is not None else ""
                        if texture_path:
                            texture_paths.append(texture_path)
                    materials[material.name] = MeshMaterial(
                        material.name,
                        material.diffuse,
                        texture_path,
                    )
        elif key == "usemtl":
            current_material = " ".join(fields[1:]).strip()
        elif key == "v" and len(fields) >= 4:
            if len(vertices) >= MAX_MESH_VERTICES:
                warnings.append("OBJ vertex limit reached")
                break
            try:
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
                color = _to_color(tuple(float(value) for value in fields[4:8])) if len(fields) >= 7 else None
                vertex_colors.append(color)
            except ValueError:
                warnings.append(f"invalid OBJ vertex: {stripped}")
        elif key == "vt" and len(fields) >= 2:
            try:
                texcoords.append((float(fields[1]), float(fields[2]) if len(fields) >= 3 else 0.0))
            except ValueError:
                warnings.append(f"invalid OBJ texture coordinate: {stripped}")
        elif key == "f" and len(fields) >= 4:
            if len(faces) >= MAX_MESH_FACES:
                warnings.append("OBJ face limit reached")
                break
            face_vertices: list[int] = []
            face_uvs: list[int] = []
            for token in fields[1:]:
                parts = token.split("/")
                try:
                    vertex_index = int(parts[0])
                except (ValueError, IndexError):
                    continue
                vertex_index = len(vertices) + vertex_index if vertex_index < 0 else vertex_index - 1
                if not 0 <= vertex_index < len(vertices):
                    continue
                face_vertices.append(vertex_index)
                if len(parts) >= 2 and parts[1]:
                    try:
                        uv_index = int(parts[1])
                    except ValueError:
                        uv_index = 0
                    uv_index = len(texcoords) + uv_index if uv_index < 0 else uv_index - 1
                    face_uvs.append(uv_index if 0 <= uv_index < len(texcoords) else -1)
            if len(face_vertices) >= 3:
                valid_uvs = tuple(face_uvs) if len(face_uvs) == len(face_vertices) and all(index >= 0 for index in face_uvs) else ()
                faces.append(MeshFace(tuple(face_vertices), valid_uvs, current_material))
    while len(vertex_colors) < len(vertices):
        vertex_colors.append(None)
    return MeshData(
        name=path.name,
        vertices=tuple(vertices),
        edges=_edges_from_faces(faces),
        faces=tuple(faces),
        texcoords=tuple(texcoords),
        vertex_colors=tuple(vertex_colors),
        materials=tuple(materials[name] for name in sorted(materials)),
        texture_paths=tuple(dict.fromkeys(texture_paths)),
        source_path=str(path),
        format_name="OBJ",
        encoding="ascii",
        warnings=tuple(dict.fromkeys(warnings)),
    )


def load_stl(path: Path) -> MeshData:
    content = path.read_bytes()
    vertices: list[Vec3] = []
    faces: list[MeshFace] = []
    warnings: list[str] = []
    if len(content) >= 84:
        triangle_count = struct.unpack_from("<I", content, 80)[0]
        expected_size = 84 + triangle_count * 50
    else:
        triangle_count = 0
        expected_size = -1
    if expected_size == len(content):
        encoding = "binary_little_endian"
        for triangle in range(min(triangle_count, MAX_MESH_FACES, MAX_MESH_VERTICES // 3)):
            base = 84 + triangle * 50 + 12
            indices: list[int] = []
            for offset in range(3):
                vertex = struct.unpack_from("<fff", content, base + offset * 12)
                indices.append(len(vertices))
                vertices.append(tuple(float(value) for value in vertex))  # type: ignore[arg-type]
            faces.append(MeshFace(tuple(indices)))
            attribute = struct.unpack_from("<H", content, 84 + triangle * 50 + 48)[0]
            if attribute:
                warnings.append(
                    "binary STL facet attribute bytes detected; color/texture meaning is nonstandard and was not interpreted"
                )
    else:
        encoding = "ascii"
        triangle: list[int] = []
        for raw in content.decode("utf-8", errors="replace").splitlines():
            fields = raw.strip().split()
            if fields[:1] != ["vertex"] or len(fields) < 4:
                continue
            if len(vertices) >= MAX_MESH_VERTICES or len(faces) >= MAX_MESH_FACES:
                warnings.append("STL geometry limit reached")
                break
            try:
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
            except ValueError:
                continue
            triangle.append(len(vertices) - 1)
            if len(triangle) == 3:
                faces.append(MeshFace(tuple(triangle)))
                triangle = []
    if not faces:
        warnings.append("STL contains no parsed triangles")
    warnings.append("STL has no standard UV/material texture mapping")
    return MeshData(
        name=path.name,
        vertices=tuple(vertices),
        edges=_edges_from_faces(faces),
        faces=tuple(faces),
        vertex_colors=tuple(None for _ in vertices),
        source_path=str(path),
        format_name="STL",
        encoding=encoding,
        warnings=tuple(dict.fromkeys(warnings)),
    )


_PLY_TYPES = {
    "char": ("b", 1),
    "int8": ("b", 1),
    "uchar": ("B", 1),
    "uint8": ("B", 1),
    "short": ("h", 2),
    "int16": ("h", 2),
    "ushort": ("H", 2),
    "uint16": ("H", 2),
    "int": ("i", 4),
    "int32": ("i", 4),
    "uint": ("I", 4),
    "uint32": ("I", 4),
    "float": ("f", 4),
    "float32": ("f", 4),
    "double": ("d", 8),
    "float64": ("d", 8),
}


@dataclass(frozen=True)
class _PlyProperty:
    name: str
    scalar_type: str = ""
    list_count_type: str = ""
    list_value_type: str = ""

    @property
    def is_list(self) -> bool:
        return bool(self.list_count_type)


@dataclass(frozen=True)
class _PlyElement:
    name: str
    count: int
    properties: tuple[_PlyProperty, ...]


@dataclass(frozen=True)
class _PlyHeader:
    encoding: str
    elements: tuple[_PlyElement, ...]
    comments: tuple[str, ...]


def _ply_header(content: bytes) -> tuple[_PlyHeader, int]:
    offset = 0
    lines: list[str] = []
    for raw in content.splitlines(keepends=True):
        offset += len(raw)
        try:
            line = raw.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("PLY header must be ASCII") from exc
        lines.append(line)
        if line == "end_header":
            break
        if offset > 1_000_000:
            raise ValueError("PLY header exceeds bounded size")
    if not lines or lines[0] != "ply" or lines[-1] != "end_header":
        raise ValueError("invalid PLY header")
    encoding = ""
    comments: list[str] = []
    elements: list[tuple[str, int, list[_PlyProperty]]] = []
    current: list[_PlyProperty] | None = None
    for line in lines[1:-1]:
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "format" and len(fields) >= 2:
            encoding = fields[1]
        elif fields[0] in {"comment", "obj_info"}:
            comments.append(line.split(maxsplit=1)[1] if " " in line else "")
        elif fields[0] == "element" and len(fields) >= 3:
            try:
                count = int(fields[2])
            except ValueError as exc:
                raise ValueError(f"invalid PLY element count: {line}") from exc
            if count < 0:
                raise ValueError("PLY element count cannot be negative")
            current = []
            elements.append((fields[1], count, current))
        elif fields[0] == "property" and current is not None:
            if len(fields) >= 5 and fields[1] == "list":
                if fields[2] not in _PLY_TYPES or fields[3] not in _PLY_TYPES:
                    raise ValueError(f"unsupported PLY list type: {line}")
                current.append(_PlyProperty(fields[4], "", fields[2], fields[3]))
            elif len(fields) >= 3:
                if fields[1] not in _PLY_TYPES:
                    raise ValueError(f"unsupported PLY scalar type: {line}")
                current.append(_PlyProperty(fields[2], fields[1]))
    if encoding not in {"ascii", "binary_little_endian", "binary_big_endian"}:
        raise ValueError(f"unsupported PLY encoding: {encoding!r}")
    return (
        _PlyHeader(
            encoding,
            tuple(_PlyElement(name, count, tuple(properties)) for name, count, properties in elements),
            tuple(comments),
        ),
        offset,
    )


def _ply_ascii_record(tokens: list[str], properties: Sequence[_PlyProperty]) -> dict[str, object]:
    result: dict[str, object] = {}
    cursor = 0
    for prop in properties:
        if prop.is_list:
            if cursor >= len(tokens):
                raise ValueError("truncated PLY ASCII list")
            count = int(tokens[cursor])
            cursor += 1
            if count < 0 or count > MAX_PLY_LIST_ITEMS or cursor + count > len(tokens):
                raise ValueError("invalid PLY ASCII list count")
            result[prop.name] = tuple(_ply_cast(tokens[cursor + index], prop.list_value_type) for index in range(count))
            cursor += count
        else:
            if cursor >= len(tokens):
                raise ValueError("truncated PLY ASCII record")
            result[prop.name] = _ply_cast(tokens[cursor], prop.scalar_type)
            cursor += 1
    return result


def _ply_cast(value: str, type_name: str) -> float | int:
    code = _PLY_TYPES[type_name][0]
    return float(value) if code in {"f", "d"} else int(value)


def _unpack_scalar(content: bytes, offset: int, type_name: str, endian: str) -> tuple[float | int, int]:
    code, size = _PLY_TYPES[type_name]
    if offset + size > len(content):
        raise ValueError("truncated binary PLY")
    return struct.unpack_from(endian + code, content, offset)[0], offset + size


def _ply_binary_record(
    content: bytes,
    offset: int,
    properties: Sequence[_PlyProperty],
    endian: str,
) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    for prop in properties:
        if prop.is_list:
            count_raw, offset = _unpack_scalar(content, offset, prop.list_count_type, endian)
            count = int(count_raw)
            if count < 0 or count > MAX_PLY_LIST_ITEMS:
                raise ValueError("invalid binary PLY list count")
            values: list[float | int] = []
            for _ in range(count):
                value, offset = _unpack_scalar(content, offset, prop.list_value_type, endian)
                values.append(value)
            result[prop.name] = tuple(values)
        else:
            result[prop.name], offset = _unpack_scalar(content, offset, prop.scalar_type, endian)
    return result, offset


def _pick(record: dict[str, object], names: Sequence[str], default: object = None) -> object:
    for name in names:
        if name in record:
            return record[name]
    return default


def _ply_vertex(record: dict[str, object]) -> tuple[Vec3, Color | None, Vec2 | None]:
    try:
        point = (float(record["x"]), float(record["y"]), float(record["z"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("PLY vertex requires x/y/z properties") from exc
    red = _pick(record, ("red", "r"))
    green = _pick(record, ("green", "g"))
    blue = _pick(record, ("blue", "b"))
    alpha = _pick(record, ("alpha", "a"), 255)
    color = None
    if red is not None and green is not None and blue is not None:
        color = _to_color((red, green, blue, alpha))  # type: ignore[arg-type]
    u = _pick(record, ("u", "s", "texture_u", "texcoord_u"))
    v = _pick(record, ("v", "t", "texture_v", "texcoord_v"))
    uv = (float(u), float(v)) if u is not None and v is not None else None
    return point, color, uv


def _ply_face(
    record: dict[str, object],
    texcoords: list[Vec2],
    vertex_uv_available: bool,
) -> MeshFace | None:
    raw_indices = _pick(record, ("vertex_indices", "vertex_index", "vertices"))
    if not isinstance(raw_indices, tuple):
        return None
    indices = tuple(int(value) for value in raw_indices)
    if len(indices) < 3:
        return None
    raw_uv = _pick(record, ("texcoord", "texcoords", "texture_coordinates"))
    uv_indices: tuple[int, ...] = ()
    if isinstance(raw_uv, tuple) and len(raw_uv) >= len(indices) * 2:
        appended: list[int] = []
        for index in range(len(indices)):
            texcoords.append((float(raw_uv[index * 2]), float(raw_uv[index * 2 + 1])))
            appended.append(len(texcoords) - 1)
        uv_indices = tuple(appended)
    elif vertex_uv_available:
        uv_indices = indices
    material_index = _pick(record, ("material_index", "texnumber", "texture_index"))
    material = f"material:{int(material_index)}" if material_index is not None else ""
    return MeshFace(indices, uv_indices, material)


def load_ply(path: Path) -> MeshData:
    content = path.read_bytes()
    header, offset = _ply_header(content)
    vertices: list[Vec3] = []
    vertex_colors: list[Color | None] = []
    vertex_uvs: list[Vec2 | None] = []
    texcoords: list[Vec2] = []
    faces: list[MeshFace] = []
    warnings: list[str] = []
    records: dict[str, list[dict[str, object]]] = {}

    if header.encoding == "ascii":
        text = content[offset:].decode("ascii", errors="replace").splitlines()
        line_index = 0
        for element in header.elements:
            bucket: list[dict[str, object]] = []
            for _ in range(element.count):
                while line_index < len(text) and not text[line_index].strip():
                    line_index += 1
                if line_index >= len(text):
                    raise ValueError(f"truncated ASCII PLY element {element.name}")
                bucket.append(_ply_ascii_record(text[line_index].split(), element.properties))
                line_index += 1
            records[element.name] = bucket
    else:
        endian = "<" if header.encoding == "binary_little_endian" else ">"
        cursor = offset
        for element in header.elements:
            bucket = []
            for _ in range(element.count):
                record, cursor = _ply_binary_record(content, cursor, element.properties, endian)
                bucket.append(record)
            records[element.name] = bucket

    for record in records.get("vertex", [])[:MAX_MESH_VERTICES]:
        point, color, uv = _ply_vertex(record)
        vertices.append(point)
        vertex_colors.append(color)
        vertex_uvs.append(uv)
    if len(records.get("vertex", [])) > MAX_MESH_VERTICES:
        warnings.append("PLY vertex limit reached")

    vertex_uv_available = bool(vertices) and all(uv is not None for uv in vertex_uvs)
    if vertex_uv_available:
        texcoords.extend(uv for uv in vertex_uvs if uv is not None)
    for record in records.get("face", [])[:MAX_MESH_FACES]:
        face = _ply_face(record, texcoords, vertex_uv_available)
        if face is None:
            continue
        if all(0 <= index < len(vertices) for index in face.vertex_indices):
            faces.append(face)
    if len(records.get("face", [])) > MAX_MESH_FACES:
        warnings.append("PLY face limit reached")

    textures: list[str] = []
    for comment in header.comments:
        fields = comment.strip().split(maxsplit=1)
        if len(fields) != 2 or fields[0].casefold() not in {"texturefile", "texture_file"}:
            continue
        texture_path, warning = _safe_dependency(path.parent, fields[1])
        if warning:
            warnings.append(warning)
        if texture_path is not None:
            textures.append(str(texture_path))
    materials = (
        tuple(
            MeshMaterial(
                name=f"material:{index}",
                diffuse=_to_color(
                    (
                        record.get("diffuse_red", 204),
                        record.get("diffuse_green", 204),
                        record.get("diffuse_blue", 204),
                        record.get("alpha", 255),
                    )
                ),
            )
            for index, record in enumerate(records.get("material", []))
        )
        if records.get("material")
        else ()
    )
    if textures and not texcoords:
        warnings.append("PLY texture file found but no supported texture coordinates were parsed")
    return MeshData(
        name=path.name,
        vertices=tuple(vertices),
        edges=_edges_from_faces(faces),
        faces=tuple(faces),
        texcoords=tuple(texcoords),
        vertex_colors=tuple(vertex_colors),
        materials=materials,
        texture_paths=tuple(dict.fromkeys(textures)),
        source_path=str(path),
        format_name="PLY",
        encoding=header.encoding,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def load_mesh(path: Path) -> MeshData:
    suffix = path.suffix.casefold()
    if suffix == ".obj":
        return load_obj(path)
    if suffix == ".stl":
        return load_stl(path)
    if suffix == ".ply":
        return load_ply(path)
    raise ValueError(f"unsupported 3D mesh type: {suffix or '(none)'}")
