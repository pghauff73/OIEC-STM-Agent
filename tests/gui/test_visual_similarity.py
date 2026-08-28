from __future__ import annotations

import unittest

from ourd_gui.visual_models import MeshData
from ourd_gui.visual_similarity import (
    METHODS,
    classify_images_to_three_views,
    compare_images,
    render_mesh_three_views,
)

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = ImageDraw = None


@unittest.skipIf(Image is None, "Pillow visual extra not installed")
class VisualSimilarityTests(unittest.TestCase):
    def _shape(self, *, shift: int = 0):
        image = Image.new("L", (160, 120), 255)
        draw = ImageDraw.Draw(image)
        draw.rectangle((25 + shift, 20, 115 + shift, 92), outline=0, width=4)
        draw.line((35 + shift, 80, 102 + shift, 35), fill=0, width=3)
        return image

    def test_identical_image_scores_are_perfect(self) -> None:
        image = self._shape()
        report = compare_images(image, image, method="all", profile="balanced")
        self.assertEqual(10_000, report.composite_bp)
        self.assertEqual(set(METHODS), {metric.method for metric in report.metrics})
        self.assertTrue(all(metric.score_bp == 10_000 for metric in report.metrics))

    def test_shifted_shape_loses_edge_similarity(self) -> None:
        left = self._shape()
        right = self._shape(shift=22)
        identical = compare_images(left, left, method="edge-dice", profile="shape")
        shifted = compare_images(left, right, method="edge-dice", profile="shape")
        self.assertEqual(10_000, identical.composite_bp)
        self.assertLess(shifted.composite_bp, identical.composite_bp)

    def test_asymmetric_mesh_three_views_classify_back_to_canonical_views(self) -> None:
        mesh = MeshData(
            name="asymmetric",
            vertices=(
                (-2.0, -0.8, -0.2),
                (1.8, -0.8, -0.2),
                (1.2, 1.6, -0.2),
                (-1.4, 0.7, -0.2),
                (-1.2, -0.4, 1.7),
                (0.7, 0.2, 0.9),
            ),
            edges=(
                (0, 1), (1, 2), (2, 3), (3, 0),
                (0, 4), (1, 5), (2, 5), (3, 4), (4, 5),
            ),
        )
        views = render_mesh_three_views(mesh, size=256)
        candidates = {
            "front-ref": views["front"],
            "top-ref": views["top"],
            "side-ref": views["side"],
        }
        report = classify_images_to_three_views(
            mesh,
            candidates,
            mesh_name="@mesh:test",
            profile="shape",
            preprocess="fit",
            size=256,
        )
        self.assertEqual("front-ref", report.assignment["front"])
        self.assertEqual("top-ref", report.assignment["top"])
        self.assertEqual("side-ref", report.assignment["side"])
        self.assertEqual(10_000, report.aggregate_bp)
        self.assertEqual((), report.unassigned)

    def test_camera_orientation_changes_projected_views(self) -> None:
        mesh = MeshData(
            name="wedge",
            vertices=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 2.0)),
            edges=((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)),
        )
        world = render_mesh_three_views(mesh, size=192)
        camera = render_mesh_three_views(mesh, size=192, yaw=0.65, pitch=-0.35)
        report = compare_images(
            world["front"],
            camera["front"],
            method="edge-chamfer",
            profile="shape",
            preprocess="fit",
            size=192,
        )
        self.assertLess(report.composite_bp, 9_950)


if __name__ == "__main__":
    unittest.main()
