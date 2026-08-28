from __future__ import annotations

import unittest

from ourd_gui.mesh_formats import MeshData, MeshFace, MeshMaterial
from ourd_gui.opengl.mesh_compile import compile_mesh, triangulate_polygon


class OpenGLMeshCompileTests(unittest.TestCase):
    def test_concave_polygon_ear_clips_to_n_minus_two_triangles(self) -> None:
        points = (
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (2.0, 2.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 2.0, 0.0),
        )
        result = triangulate_polygon(points)
        self.assertEqual(3, len(result.triangles))
        self.assertFalse(result.fallback_used)

    def test_uv_seam_expands_shared_position(self) -> None:
        mesh = MeshData(
            name="seam",
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)),
            edges=(),
            faces=(
                MeshFace((0, 1, 2), (0, 1, 2), "A"),
                MeshFace((0, 3, 1), (3, 4, 1), "A"),
            ),
            texcoords=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.5, 0.5), (1.0, 1.0)),
            materials=(MeshMaterial("A", (255, 255, 255, 255), ""),),
        )
        compiled = compile_mesh(mesh)
        positions_at_origin = [vertex for vertex in compiled.vertices if vertex.position == (0.0, 0.0, 0.0)]
        self.assertEqual(2, len(positions_at_origin))
        self.assertEqual({(0.0, 0.0), (0.5, 0.5)}, {vertex.uv for vertex in positions_at_origin})

    def test_material_faces_become_separate_draw_batches(self) -> None:
        mesh = MeshData(
            name="materials",
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)),
            edges=(),
            faces=(
                MeshFace((0, 1, 2), (), "red"),
                MeshFace((1, 3, 2), (), "blue"),
            ),
            materials=(
                MeshMaterial("red", (255, 0, 0, 255), ""),
                MeshMaterial("blue", (0, 0, 255, 255), ""),
            ),
        )
        compiled = compile_mesh(mesh)
        self.assertEqual(2, compiled.triangle_count)
        self.assertEqual(2, len(compiled.batches))
        material_names = {compiled.materials[batch.material_index].name for batch in compiled.batches}
        self.assertEqual({"red", "blue"}, material_names)

    def test_generated_normals_are_unit_length(self) -> None:
        mesh = MeshData(
            name="triangle",
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            edges=(),
            faces=(MeshFace((0, 1, 2)),),
        )
        compiled = compile_mesh(mesh)
        for vertex in compiled.vertices:
            x, y, z = vertex.normal
            self.assertAlmostEqual(1.0, (x * x + y * y + z * z) ** 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
