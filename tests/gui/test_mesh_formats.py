from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from ourd_gui.mesh_formats import load_mesh
from ourd_gui.visual_assets import VisualAssetRegistry


class MeshFormatTests(unittest.TestCase):
    def test_obj_mtl_uv_and_texture_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            texture = project / "panel.png"
            texture.write_bytes(b"\x89PNG\r\n\x1a\ntexture")
            (project / "panel.mtl").write_text(
                "newmtl panel\n"
                "Kd 0.2 0.4 0.6\n"
                "map_Kd panel.png\n",
                encoding="utf-8",
            )
            obj = project / "body.obj"
            obj.write_text(
                "mtllib panel.mtl\n"
                "v 0 0 0\n"
                "v 1 0 0\n"
                "v 0 1 0\n"
                "vt 0 0\n"
                "vt 1 0\n"
                "vt 0 1\n"
                "usemtl panel\n"
                "f 1/1 2/2 3/3\n",
                encoding="utf-8",
            )
            workspace = root / "workspace"
            workspace.mkdir()
            registry = VisualAssetRegistry(workspace)
            asset = registry.register_file(obj, kind="mesh")
            self.assertTrue(asset.reference.startswith("@mesh:"))
            self.assertEqual(1, len(asset.dependencies))
            self.assertTrue(asset.dependencies[0].startswith("@img:"))
            mesh = load_mesh(registry.path_for(asset.reference))
            self.assertEqual("OBJ", mesh.format_name)
            self.assertEqual("ascii", mesh.encoding)
            self.assertEqual(3, len(mesh.texcoords))
            self.assertTrue(mesh.has_texture_mapping)
            self.assertEqual("panel", mesh.faces[0].material)
            self.assertEqual(1, len(mesh.texture_paths))
            self.assertTrue(Path(mesh.texture_paths[0]).is_file())

    def test_ascii_ply_colors_uv_and_texture_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "atlas.png").write_bytes(b"\x89PNG\r\n\x1a\natlas")
            path = root / "mesh.ply"
            path.write_text(
                "ply\n"
                "format ascii 1.0\n"
                "comment TextureFile atlas.png\n"
                "element vertex 3\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                "property uchar red\n"
                "property uchar green\n"
                "property uchar blue\n"
                "property float u\n"
                "property float v\n"
                "element face 1\n"
                "property list uchar int vertex_indices\n"
                "end_header\n"
                "0 0 0 255 0 0 0 0\n"
                "1 0 0 0 255 0 1 0\n"
                "0 1 0 0 0 255 0 1\n"
                "3 0 1 2\n",
                encoding="ascii",
            )
            mesh = load_mesh(path)
            self.assertEqual("PLY", mesh.format_name)
            self.assertEqual("ascii", mesh.encoding)
            self.assertTrue(mesh.has_vertex_colors)
            self.assertTrue(mesh.has_texture_mapping)
            self.assertEqual((255, 0, 0, 255), mesh.vertex_colors[0])
            self.assertEqual(1, len(mesh.texture_paths))

    def _write_binary_ply(self, path: Path, endian_name: str, endian: str) -> None:
        header = (
            "ply\n"
            f"format {endian_name} 1.0\n"
            "element vertex 3\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "element face 1\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
        ).encode("ascii")
        body = b"".join(
            struct.pack(endian + "fff", *vertex)
            for vertex in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        )
        body += struct.pack(endian + "Biii", 3, 0, 1, 2)
        path.write_bytes(header + body)

    def test_binary_little_endian_ply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "little.ply"
            self._write_binary_ply(path, "binary_little_endian", "<")
            mesh = load_mesh(path)
            self.assertEqual("binary_little_endian", mesh.encoding)
            self.assertEqual(3, len(mesh.vertices))
            self.assertEqual(1, len(mesh.faces))

    def test_binary_big_endian_ply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "big.ply"
            self._write_binary_ply(path, "binary_big_endian", ">")
            mesh = load_mesh(path)
            self.assertEqual("binary_big_endian", mesh.encoding)
            self.assertEqual((0, 1, 2), mesh.faces[0].vertex_indices)

    def test_binary_stl_is_geometry_only_and_reports_nonstandard_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "triangle.stl"
            header = b"binary".ljust(80, b"\0")
            triangle = struct.pack(
                "<12fH",
                0.0, 0.0, 1.0,
                0.0, 0.0, 0.0,
                1.0, 0.0, 0.0,
                0.0, 1.0, 0.0,
                7,
            )
            path.write_bytes(header + struct.pack("<I", 1) + triangle)
            mesh = load_mesh(path)
            self.assertEqual("STL", mesh.format_name)
            self.assertEqual("binary_little_endian", mesh.encoding)
            self.assertEqual(1, len(mesh.faces))
            self.assertFalse(mesh.has_texture_mapping)
            self.assertTrue(any("nonstandard" in warning for warning in mesh.warnings))


if __name__ == "__main__":
    unittest.main()
