from __future__ import annotations

import struct
import unittest
from pathlib import Path

from ourd_gui.artifact_models import compare_geometry, inspect_artifact, inspect_obj, inspect_stl


class ArtifactModelTests(unittest.TestCase):
    def test_obj_metadata_includes_counts_and_bbox(self) -> None:
        inspection = inspect_obj(
            b"v 0 0 0\nv 2 3 4\nvt 0 0\nvn 0 0 1\nf 1/1/1 2/1/1 1/1/1\n"
        )
        self.assertEqual(2, inspection.geometry["vertices"])
        self.assertEqual(1, inspection.geometry["faces"])
        self.assertEqual([2.0, 3.0, 4.0], inspection.geometry["bounding_box"]["maximum"])

    def test_binary_stl_metadata_is_bounded(self) -> None:
        header = b"binary".ljust(80, b"\0") + struct.pack("<I", 1)
        triangle = struct.pack(
            "<12fH",
            0,
            0,
            1,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            1,
            0,
            0,
        )
        inspection = inspect_stl(header + triangle)
        self.assertEqual("binary", inspection.geometry["encoding"])
        self.assertEqual(1, inspection.geometry["triangles"])

    def test_svg_is_passive_text_not_active_image(self) -> None:
        inspection = inspect_artifact(
            "image/svg+xml",
            Path("diagram.svg"),
            b"<svg><script>alert(1)</script></svg>",
        )
        self.assertEqual("text", inspection.preview_mode)

    def test_geometry_comparison_reports_numeric_deltas(self) -> None:
        before = inspect_obj(b"v 0 0 0\nf 1 1 1\n")
        after = inspect_obj(b"v 0 0 0\nv 1 1 1\nf 1 2 1\n")
        comparison = compare_geometry(before, after)
        self.assertEqual(1, comparison["differences"]["vertices"]["delta"])


if __name__ == "__main__":
    unittest.main()
