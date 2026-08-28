from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd_gui.views.repository import visible_repository_paths


class RepositoryViewTests(unittest.TestCase):
    def test_internal_state_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            internal = root / ".ourd-agent" / "gui" / "events.jsonl"
            internal.parent.mkdir(parents=True)
            internal.write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                ("README.md",),
                visible_repository_paths(root, show_internal_state=False),
            )
            self.assertEqual(
                (".ourd-agent/gui/events.jsonl", "README.md"),
                visible_repository_paths(root, show_internal_state=True),
            )


if __name__ == "__main__":
    unittest.main()
