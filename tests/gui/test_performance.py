from __future__ import annotations

import unittest

from ourd_gui.performance import PerformanceMonitor


class PerformanceMonitorTests(unittest.TestCase):
    def test_monitor_is_bounded_and_aggregates_samples(self) -> None:
        monitor = PerformanceMonitor(max_samples=2)
        monitor.record_ms("render", 10)
        monitor.record_ms("render", 20)
        monitor.record_ms("render", 30)
        snapshot = monitor.snapshot()
        self.assertEqual(2, snapshot["sample_count"])
        self.assertEqual(25.0, snapshot["metrics"]["render"]["average_ms"])
        self.assertEqual(30.0, snapshot["metrics"]["render"]["latest_ms"])


if __name__ == "__main__":
    unittest.main()
