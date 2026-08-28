from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd_gui.visual_assets import VisualAssetRegistry


class MeshBundleIdentityTests(unittest.TestCase):
    def test_texture_change_changes_mesh_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "material.mtl").write_text(
                "newmtl m\nmap_Kd texture.png\n",
                encoding="utf-8",
            )
            (source / "model.obj").write_text(
                "mtllib material.mtl\n"
                "v 0 0 0\n"
                "v 1 0 0\n"
                "v 0 1 0\n"
                "vt 0 0\n"
                "vt 1 0\n"
                "vt 0 1\n"
                "usemtl m\n"
                "f 1/1 2/2 3/3\n",
                encoding="utf-8",
            )
            texture = source / "texture.png"
            texture.write_bytes(b"\x89PNG\r\n\x1a\nfirst")
            workspace = root / "workspace"
            workspace.mkdir()
            registry = VisualAssetRegistry(workspace)
            first = registry.register_file(source / "model.obj", kind="mesh")
            texture.write_bytes(b"\x89PNG\r\n\x1a\nsecond")
            second = registry.register_file(source / "model.obj", kind="mesh")
            self.assertNotEqual(first.reference, second.reference)
            self.assertNotEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
