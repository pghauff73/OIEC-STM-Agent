from __future__ import annotations

import unittest

from pathlib import Path

from tools.validate import REPO_ROOT, source_hashes, xvfb_server_argv


class ValidationCoverageTests(unittest.TestCase):
    def test_validation_hashes_gui_source_docs_and_build_backend(self) -> None:
        hashes = source_hashes(REPO_ROOT)
        for path in (
            "ourd_gui/app.py",
            "ourd_gui/controller.py",
            "ourd_gui/views/selection.py",
            "docs/OURD_AGENT_GUI.md",
            "docs/GUI_SAFETY.md",
            "OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md",
            "tools/build_backend.py",
        ):
            self.assertIn(path, hashes)

    def test_xvfb_transport_avoids_sandbox_unix_socket(self) -> None:
        argv = xvfb_server_argv("/usr/bin/Xvfb", 123, Path("/tmp/auth"))
        self.assertEqual(argv[1], ":123")
        self.assertIn("-auth", argv)
        self.assertIn("-nolisten", argv)
        self.assertEqual(argv[argv.index("-nolisten") + 1], "unix")
        self.assertEqual(argv[argv.index("-listen") + 1], "tcp")


if __name__ == "__main__":
    unittest.main()
