from __future__ import annotations

import ast
import unittest
from pathlib import Path


class GuiSafetyTests(unittest.TestCase):
    def test_views_do_not_import_mutating_or_process_modules(self) -> None:
        forbidden_imports = {
            "subprocess",
            "ourd.egcf.adapters.eon",
            "ourd.transactions",
            "ourd.agent",
        }
        root = Path(__file__).resolve().parents[2] / "ourd_gui" / "views"
        violations: list[str] = []
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(name == item or name.startswith(item + ".") for item in forbidden_imports):
                        violations.append(f"{path.name}: {name}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()

