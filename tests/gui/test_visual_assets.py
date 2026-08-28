from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from ourd.providers import OpenAIResponsesProvider, ProviderConfig
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

    def test_provider_expands_latest_img_reference_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.png"
            payload = b"\x89PNG\r\n\x1a\nvisual-test"
            source.write_bytes(payload)
            registry = VisualAssetRegistry(root)
            asset = registry.register_file(source, kind="image")
            provider = OpenAIResponsesProvider(
                ProviderConfig(
                    model="local-test",
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",
                    visual_asset_root=str(registry.root),
                )
            )
            expanded = provider._expand_latest_image_references(
                [
                    {"role": "user", "content": f"Earlier {asset.reference}"},
                    {"role": "assistant", "content": "ack"},
                    {"role": "user", "content": f"Inspect this image {asset.reference}"},
                ]
            )
            self.assertIsInstance(expanded[-1]["content"], list)
            image_item = expanded[-1]["content"][1]
            self.assertEqual("input_image", image_item["type"])
            encoded = image_item["image_url"].split(",", 1)[1]
            self.assertEqual(payload, base64.b64decode(encoded))
            self.assertIsInstance(expanded[0]["content"], str)


if __name__ == "__main__":
    unittest.main()
