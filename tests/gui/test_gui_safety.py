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

    def test_formal_writing_gui_has_no_approval_apply_or_saa_qualification_calls(self) -> None:
        root = Path(__file__).resolve().parents[2]
        paths = (
            root / "ourd_gui" / "formal_writing_gui.py",
            root / "ourd_gui" / "formal_writing_controller.py",
            root / "ourd_gui" / "views" / "formal_writing.py",
        )
        prohibited = {
            "approve",
            "approve_plan",
            "apply",
            "apply_transaction",
            "qualify_algorithm",
            "register_algorithm",
        }
        calls: list[str] = []
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
                else:
                    continue
                if name in prohibited:
                    calls.append(f"{path.name}: {name}")
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
