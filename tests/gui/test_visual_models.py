from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd_gui.visual_models import (
    BezierCurve3D,
    BezierScene,
    cubic_bezier_point,
    load_mesh,
    sample_bezier,
)


class VisualModelTests(unittest.TestCase):
    def test_cubic_bezier_preserves_endpoints_and_roundtrips(self) -> None:
        curve = BezierCurve3D.default("test")
        self.assertEqual(curve.control_points[0], cubic_bezier_point(curve, 0.0))
        self.assertEqual(curve.control_points[3], cubic_bezier_point(curve, 1.0))
        self.assertEqual(17, len(sample_bezier(curve, 17)))

        scene = BezierScene(curves=[curve], revision=3)
        restored = BezierScene.from_json(scene.to_json())
        self.assertEqual(3, restored.revision)
        self.assertEqual(scene.curves, restored.curves)

    def test_obj_loader_extracts_wireframe_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "triangle.obj"
            path.write_text(
                "v 0 0 0\n"
                "v 1 0 0\n"
                "v 0 1 0\n"
                "f 1 2 3\n",
                encoding="utf-8",
            )
            mesh = load_mesh(path)
            self.assertEqual(3, len(mesh.vertices))
            self.assertEqual({(0, 1), (0, 2), (1, 2)}, set(mesh.edges))

    def test_ascii_stl_loader_extracts_triangle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "triangle.stl"
            path.write_text(
                "solid t\n"
                " facet normal 0 0 1\n"
                "  outer loop\n"
                "   vertex 0 0 0\n"
                "   vertex 1 0 0\n"
                "   vertex 0 1 0\n"
                "  endloop\n"
                " endfacet\n"
                "endsolid\n",
                encoding="utf-8",
            )
            mesh = load_mesh(path)
            self.assertEqual(3, len(mesh.vertices))
            self.assertEqual(3, len(mesh.edges))


if __name__ == "__main__":
    unittest.main()
