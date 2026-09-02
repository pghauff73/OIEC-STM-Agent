from __future__ import annotations

import json
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class IcpiHeavyCampaignTests(unittest.TestCase):
    def test_full_deterministic_campaign_produces_all_required_artifacts(self) -> None:
        if importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
            self.skipTest("full page-accuracy campaign requires PyMuPDF")
        if importlib.util.find_spec("pytesseract") is None:
            self.skipTest("full page-accuracy campaign requires pytesseract")
        xvfb_run = shutil.which("xvfb-run")
        if xvfb_run is None:
            self.skipTest("xvfb-run is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            report_root = Path(temporary) / "reports"
            completed = subprocess.run(
                [
                    xvfb_run,
                    "-a",
                    sys.executable,
                    str(ROOT / "tools" / "icpi_chat_scenario_runner.py"),
                    "--report-root",
                    str(report_root),
                    "--run-id",
                    "full-deterministic",
                    "--time-scale",
                    "0.01",
                    "--continue-on-failure",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=240,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            run_root = report_root / "full-deterministic"
            required = {
                "app-events.jsonl",
                "manifest.json",
                "scenarios.jsonl",
                "results.jsonl",
                "metrics.json",
                "supervisor-events.jsonl",
                "gui-events.jsonl",
                "core-events.jsonl",
                "source-manifest.json",
                "workspace-baselines.json",
                "fixture-manifest.json",
                "final-audit.md",
                "requirement-audit.json",
                "gate-results.json",
                "git-status.txt",
                "human-review.json",
                "secret-scan.json",
            }
            self.assertTrue(required <= {path.name for path in run_root.iterdir()})
            results = [
                json.loads(line)
                for line in (run_root / "results.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(120, len(results))
            counts = Counter(result["verdict"] for result in results)
            self.assertEqual(120, counts["PASS"] + counts["BLOCKED_EXPECTED"])
            self.assertEqual(16, counts["BLOCKED_EXPECTED"])
            manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(120, manifest["completed_scenario_count"])
            self.assertEqual(0, manifest["secret_scan_finding_count"])
            self.assertTrue(manifest["git"]["available"])
            self.assertIn("distributions", manifest["dependencies"])
            self.assertTrue(manifest["python_executable"])
            self.assertEqual(64, len(manifest["workspace_baselines_sha256"]))
            baselines = json.loads(
                (run_root / "workspace-baselines.json").read_text(encoding="utf-8")
            )
            self.assertEqual(11, len(baselines))
            self.assertTrue(
                all(record["runtime"]["read_only_authority_hash"] for record in baselines.values())
            )
            gates = json.loads((run_root / "gate-results.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {"G01", "G02", "G03", "G04", "G05", "G06", "G09"},
                {
                    gate_id
                    for gate_id, record in gates["gates"].items()
                    if record["status"] == "PASS"
                },
            )
            self.assertEqual("NOT_RUN", gates["gates"]["G07"]["status"])
            self.assertEqual("NOT_RUN", gates["gates"]["G08"]["status"])
            human_review = json.loads(
                (run_root / "human-review.json").read_text(encoding="utf-8")
            )
            self.assertEqual("PENDING_HUMAN_APPROVAL", human_review["visual"]["status"])
            self.assertEqual(15, len(human_review["visual"]["screenshots"]))
            self.assertEqual("NOT_RUN", human_review["live_responses"]["status"])
            self.assertEqual(15, len(tuple((run_root / "category-artifacts" / "visual_formatting" / "screenshots").rglob("*.png"))))

    def test_short_soak_covers_restart_cancel_theme_and_context_schedules(self) -> None:
        xvfb_run = shutil.which("xvfb-run")
        if xvfb_run is None:
            self.skipTest("xvfb-run is unavailable")
        from tools.icpi_chat_scenario_generator import build_scenarios, render_jsonl

        scenario = next(item for item in build_scenarios() if item.scenario_id == "CTL-008")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_path = root / "scenario.jsonl"
            scenario_path.write_text(render_jsonl((scenario,)), encoding="utf-8")
            report_root = root / "reports"
            completed = subprocess.run(
                [
                    xvfb_run,
                    "-a",
                    sys.executable,
                    str(ROOT / "tools" / "icpi_chat_scenario_runner.py"),
                    "--scenarios",
                    str(scenario_path),
                    "--report-root",
                    str(report_root),
                    "--run-id",
                    "short-soak",
                    "--time-scale",
                    "0.01",
                    "--soak-turns",
                    "100",
                    "--soak-min-seconds",
                    "0",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertNotIn("invalid command name", completed.stderr)
            run_root = report_root / "short-soak"
            soak = json.loads((run_root / "soak-result.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", soak["verdict"])
            self.assertEqual(100, soak["completed_turns"])
            self.assertEqual(1, soak["restart_count"])
            self.assertEqual(4, soak["cancellation_count"])
            self.assertEqual(5, soak["theme_switch_count"])
            self.assertEqual(2, soak["context_clear_count"])
            self.assertGreater(soak["canonical_turn_corpus_count"], 100)
            self.assertEqual(64, len(soak["canonical_turn_order_sha256"]))
            self.assertEqual(0, soak["idle_violation_count"])
            self.assertEqual(0, soak["pending_operation_violation_count"])
            self.assertLessEqual(
                soak["max_event_loop_lag_seconds"],
                soak["thresholds"]["max_event_loop_lag_seconds"],
            )
            self.assertFalse(soak["canonical_gate_complete"])
            self.assertEqual(100, len(soak["samples"]))
            self.assertTrue(all(sample["source_scenario_id"] for sample in soak["samples"]))
            self.assertGreater(soak["samples"][-1]["state_save_latency_seconds"], 0)

    def test_soak_wall_clock_wait_does_not_add_extra_turns(self) -> None:
        xvfb_run = shutil.which("xvfb-run")
        if xvfb_run is None:
            self.skipTest("xvfb-run is unavailable")
        from tools.icpi_chat_scenario_generator import build_scenarios, render_jsonl

        scenario = next(item for item in build_scenarios() if item.scenario_id == "CTL-008")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scenario_path = root / "scenario.jsonl"
            scenario_path.write_text(render_jsonl((scenario,)), encoding="utf-8")
            report_root = root / "reports"
            completed = subprocess.run(
                [
                    xvfb_run,
                    "-a",
                    sys.executable,
                    str(ROOT / "tools" / "icpi_chat_scenario_runner.py"),
                    "--scenarios",
                    str(scenario_path),
                    "--report-root",
                    str(report_root),
                    "--run-id",
                    "idle-soak",
                    "--time-scale",
                    "0.01",
                    "--soak-turns",
                    "3",
                    "--soak-min-seconds",
                    "1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            soak = json.loads((report_root / "idle-soak" / "soak-result.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", soak["verdict"])
            self.assertEqual(3, soak["completed_turns"])
            self.assertEqual(3, len(soak["samples"]))
            self.assertGreater(soak["idle_pump_count"], 0)
            self.assertGreaterEqual(soak["duration_seconds"], 1)
            self.assertFalse(soak["canonical_gate_complete"])


if __name__ == "__main__":
    unittest.main()
