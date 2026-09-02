from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from ourd_gui.visual_assets import VisualAssetRegistry


class VisualAssetTests(unittest.TestCase):
    def test_content_addressed_image_reference_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\nvisual-test")
            registry = VisualAssetRegistry(root)
            first = registry.register_file(source, kind="image")
            second = registry.register_file(source, kind="image")
            self.assertEqual(first.reference, second.reference)
            self.assertTrue(first.reference.startswith("@img:"))
            self.assertEqual((first.reference,), registry.image_references_in(first.reference))
            self.assertTrue(registry.path_for(first.reference).is_file())

    def test_match_reports_receive_stable_match_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = VisualAssetRegistry(root)
            content = b'{"type":"image_match","score_bp":9876}\n'
            first = registry.register_bytes(
                content,
                filename="match.json",
                kind="report",
                media_type="application/json",
            )
            second = registry.register_bytes(
                content,
                filename="match.json",
                kind="report",
                media_type="application/json",
            )
            self.assertEqual(first.reference, second.reference)
            self.assertTrue(first.reference.startswith("@match:"))
            self.assertEqual("report", first.kind)

    def test_registry_builds_multimodal_user_item_for_explicit_image_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.png"
            payload = b"\x89PNG\r\n\x1a\nvisual-test"
            source.write_bytes(payload)
            registry = VisualAssetRegistry(root)
            asset = registry.register_file(source, kind="image")
            earlier = registry.multimodal_user_item(f"Earlier {asset.reference}")
            expanded = registry.multimodal_user_item(
                f"Inspect this image {asset.reference}"
            )
            self.assertIsInstance(expanded["content"], list)
            image_item = expanded["content"][1]
            self.assertEqual("input_image", image_item["type"])
            encoded = image_item["image_url"].split(",", 1)[1]
            self.assertEqual(payload, base64.b64decode(encoded))
            self.assertIsInstance(earlier["content"], list)


if __name__ == "__main__":
    unittest.main()
