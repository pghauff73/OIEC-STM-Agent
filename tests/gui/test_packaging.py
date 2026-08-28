from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_backend import build_wheel


class GuiPackagingTests(unittest.TestCase):
    def test_wheel_contains_gui_package_and_console_entry_point(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            filename = build_wheel(directory)
            wheel_path = Path(directory) / filename
            with zipfile.ZipFile(wheel_path) as archive:
                names = set(archive.namelist())
                self.assertIn("ourd_gui/app.py", names)
                self.assertIn("ourd_gui/views/shell.py", names)
                entry_points_name = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                entry_points = archive.read(entry_points_name).decode("utf-8")
        self.assertIn("ourd-gui = ourd_gui.app:main", entry_points)


if __name__ == "__main__":
    unittest.main()
