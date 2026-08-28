from __future__ import annotations

import unittest

from ourd_gui.widgets.diff_view import diff_line_kind


class DiffViewTests(unittest.TestCase):
    def test_classifies_unified_diff_lines_without_rendering(self) -> None:
        self.assertEqual("header", diff_line_kind("--- a/file\n"))
        self.assertEqual("hunk", diff_line_kind("@@ -1 +1 @@\n"))
        self.assertEqual("added", diff_line_kind("+new\n"))
        self.assertEqual("removed", diff_line_kind("-old\n"))
        self.assertEqual("context", diff_line_kind(" unchanged\n"))


if __name__ == "__main__":
    unittest.main()
