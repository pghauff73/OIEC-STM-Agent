from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.egcf.engine import EGCFEngine
from ourd_gui.read_models import ReadOnlyEGCFRepository
from ourd_gui.semantic_terminal import parse_semantic_command


class SemanticTerminalTests(unittest.TestCase):
    def test_parses_registered_command_with_json_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root):
                pass
            parsed = parse_semantic_command(
                ReadOnlyEGCFRepository(root),
                'hrt interpret {"text": "inspect parser"}',
            )
            self.assertEqual("hrt.interpret@1", parsed.command_id)
            self.assertEqual({"text": "inspect parser"}, parsed.inputs)
            self.assertTrue(parsed.read_only)
            self.assertFalse(parsed.request().modifiers["dry_run"])

    def test_rejects_shell_metacharacters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            with EGCFEngine(root):
                pass
            repository = ReadOnlyEGCFRepository(root)
            with self.assertRaisesRegex(ValueError, "metacharacters"):
                parse_semantic_command(repository, "hrt interpret {} | sh")


if __name__ == "__main__":
    unittest.main()
