from __future__ import annotations

import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools.build_backend import build_sdist, build_wheel


class GuiPackagingTests(unittest.TestCase):
    def test_wheel_contains_product_and_compatibility_entry_points(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            filename = build_wheel(directory)
            wheel_path = Path(directory) / filename
            with zipfile.ZipFile(wheel_path) as archive:
                names = set(archive.namelist())
                self.assertIn("ourd_gui/app.py", names)
                self.assertIn("ourd_gui/views/shell.py", names)
                self.assertIn("oiec_stm_agent.py", names)
                entry_points_name = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                entry_points = archive.read(entry_points_name).decode("utf-8")
        self.assertIn("oiec-stm-agent = ourd.cli:main", entry_points)
        self.assertIn("oiec-stm-gui = ourd_gui.app:main", entry_points)
        self.assertIn("ourd-agent = ourd.cli:main", entry_points)
        self.assertIn("ourd-gui = ourd_gui.app:main", entry_points)

    def test_sdist_contains_reasoning_benchmark_harness_and_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            filename = build_sdist(directory)
            archive_path = Path(directory) / filename
            with tarfile.open(archive_path, "r:gz") as archive:
                names = {Path(name).as_posix() for name in archive.getnames()}
        self.assertTrue(any(name.endswith("/benchmarks/reasoning/schema.json") for name in names))
        self.assertTrue(any(name.endswith("/benchmarks/reasoning/baseline-v1.json") for name in names))
        self.assertTrue(any(name.endswith("/benchmarks/reasoning/baseline-v1.sha256") for name in names))
        self.assertTrue(any(name.endswith("/benchmarks/reasoning/runs/SR-0B_FAILURE_ANALYSIS.md") for name in names))
        self.assertTrue(any(name.endswith("/tools/run_reasoning_benchmark.py") for name in names))
        self.assertTrue(any(name.endswith("/tools/run_reasoning_model_benchmark.py") for name in names))
        self.assertTrue(any(name.endswith("/ourd/reasoning/model_benchmark.py") for name in names))

    def test_sdist_is_byte_reproducible_across_build_times(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory:
            with mock.patch("gzip.time.time", return_value=1_000_000_000):
                first_name = build_sdist(first_directory)
            first_bytes = (Path(first_directory) / first_name).read_bytes()
        with tempfile.TemporaryDirectory() as second_directory:
            with mock.patch("gzip.time.time", return_value=2_000_000_000):
                second_name = build_sdist(second_directory)
            second_bytes = (Path(second_directory) / second_name).read_bytes()
        self.assertEqual(first_name, second_name)
        self.assertEqual(first_bytes, second_bytes)


if __name__ == "__main__":
    unittest.main()
