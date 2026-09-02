from __future__ import annotations

import shutil
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

from ourd.formal_writing import FormalWritingService, compile_formal_writing_request
from ourd_gui.formal_writing_gui import FormalWritingApplication
from ourd_gui.formal_writing_projection import FormalWritingProjectionStore
from ourd_gui.views.formal_writing import FormalWritingView


class FormalWritingPerformanceTests(unittest.TestCase):
    def test_projection_refresh_for_one_hundred_results_meets_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("# Source\n\nGrounded evidence.\n", encoding="utf-8")
            FormalWritingService(root).execute(
                compile_formal_writing_request(
                    operation="draft",
                    objective="Grounded evidence",
                    source_paths=("source.md",),
                )
            )
            result_directory = root / ".ourd-agent" / "writing" / "results"
            original = next(result_directory.glob("*.json"))
            for index in range(99):
                shutil.copyfile(original, result_directory / f"copy-{index:03d}.json")
            store = FormalWritingProjectionStore(root)
            store.snapshot()
            started = time.perf_counter()
            snapshot = store.snapshot()
            elapsed = time.perf_counter() - started
        self.assertEqual(100, len(snapshot.results))
        self.assertLess(elapsed, 0.5)

    def test_loaded_run_selection_meets_target(self) -> None:
        try:
            root_window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        root_window.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "source.md").write_text(
                    "# Source\n\nGrounded evidence.\n",
                    encoding="utf-8",
                )
                FormalWritingService(root).execute(
                    compile_formal_writing_request(
                        operation="draft",
                        objective="Grounded evidence",
                        source_paths=("source.md",),
                    )
                )
                view = FormalWritingView(root_window, root)
                view.run_list.selection_clear(0, "end")
                view.run_list.selection_set(0)
                started = time.perf_counter()
                view._select_run()
                elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.1)
        finally:
            root_window.destroy()

    def test_standalone_startup_and_idle_close_meet_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started = time.perf_counter()
            try:
                application = FormalWritingApplication(root)
            except tk.TclError as exc:
                self.skipTest(f"Tk display unavailable: {exc}")
            application.update_idletasks()
            startup_elapsed = time.perf_counter() - started
            close_started = time.perf_counter()
            application._close()
            close_elapsed = time.perf_counter() - close_started
        self.assertLess(startup_elapsed, 2.0)
        self.assertLess(close_elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
