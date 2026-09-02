from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ourd.persistence import atomic_write_text
from ourd_gui.supervisor import read_supervisor_status
from ourd_gui.supervisor_lifecycle import AppLifecycleRecorder
from tools.icpi_supervisor_fault_fixture import create_fixture_workspace, run_fault


ROOT = Path(__file__).resolve().parents[2]


class SupervisorFaultTests(unittest.TestCase):
    def test_all_sixteen_faults_have_exact_passing_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            observed = []
            for number in range(1, 17):
                fault_id = f"F{number:02d}"
                workspace, _ = create_fixture_workspace(root / fault_id.lower())
                result = run_fault(fault_id, workspace, time_scale=0.01)
                observed.append(result.fault_id)
                self.assertEqual("PASS", result.verdict, result.to_dict())
                self.assertTrue(result.observed_effect["passed"])
            self.assertEqual([f"F{number:02d}" for number in range(1, 17)], observed)

    def test_app_lifecycle_records_readiness_heartbeat_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recorder = AppLifecycleRecorder(root, supervisor_session_id="supervisor-1")
            recorder.startup_begin()
            recorder.startup_ready(
                gui_session_id="gui-1",
                source_snapshot="a" * 64,
                event_head="b" * 64,
            )
            recorder.heartbeat(chat_status="idle", pending_operations=0)
            recorder.shutdown_requested(chat_status="idle")
            recorder.checkpoint(state_digest="c" * 64, event_head="d" * 64)
            recorder.shutdown_complete()
            events = [
                json.loads(line)
                for line in recorder.events_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [
                    "STARTUP_BEGIN",
                    "STARTUP_READY",
                    "HEARTBEAT",
                    "SHUTDOWN_REQUESTED",
                    "CHECKPOINT_SAVED",
                    "SHUTDOWN_COMPLETE",
                ],
                [event["event_type"] for event in events],
            )
            current = json.loads(recorder.current_path.read_text(encoding="utf-8"))
            self.assertEqual("STOPPED", current["state"])
            self.assertEqual("supervisor-1", current["supervisor_session_id"])
            self.assertEqual("gui-1", current["gui_session_id"])

    def test_status_reader_and_cli_fail_closed_for_stale_pid_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status_path = root / ".ourd-agent" / "supervisor" / "current.json"
            timestamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat().replace(
                "+00:00", "Z"
            )
            atomic_write_text(
                status_path,
                json.dumps(
                    {
                        "schema_version": 1,
                        "updated_at": timestamp,
                        "heartbeat_at": timestamp,
                        "session_id": "stale-session",
                        "state": "RUNNING",
                        "supervisor_pid": 999_999_991,
                        "child_pid": 999_999_992,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            observed = read_supervisor_status(root, heartbeat_stale_seconds=5.0)
            self.assertEqual("STALE", observed["state"])
            self.assertIn("heartbeat stale", observed["status_reasons"])
            self.assertIn("supervisor PID identity mismatch", observed["status_reasons"])
            self.assertIn("child PID identity mismatch", observed["status_reasons"])
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "oiec_stm_sr_agenticpi.py"),
                    "--supervisor-status",
                    "--supervisor-heartbeat-stale-seconds",
                    "5",
                    "--repo",
                    str(root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            cli_status = json.loads(completed.stdout)
            self.assertEqual("STALE", cli_status["state"])
            self.assertEqual(observed["status_reasons"], cli_status["status_reasons"])

    def test_supervised_smoke_correlates_supervisor_and_gui_sessions(self) -> None:
        xvfb_run = shutil.which("xvfb-run")
        if xvfb_run is None:
            self.skipTest("xvfb-run is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [
                    xvfb_run,
                    "-a",
                    sys.executable,
                    str(ROOT / "oiec_stm_sr_agenticpi.py"),
                    "--supervisor-mode",
                    "--supervisor-max-restarts",
                    "0",
                    "--supervisor-poll-seconds",
                    "0.02",
                    "--repo",
                    str(root),
                    "--no-auto-qwen",
                    "--smoke-test",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            status = json.loads(
                (root / ".ourd-agent" / "supervisor" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            app_events = [
                json.loads(line)
                for line in (
                    root / ".ourd-agent" / "supervisor" / "app-events.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]
            event_types = [event["event_type"] for event in app_events]
            self.assertIn("STARTUP_READY", event_types)
            self.assertIn("CHECKPOINT_SAVED", event_types)
            self.assertIn("SHUTDOWN_COMPLETE", event_types)
            self.assertTrue(
                all(
                    event["supervisor_session_id"] == status["session_id"]
                    for event in app_events
                )
            )
            ready = next(event for event in app_events if event["event_type"] == "STARTUP_READY")
            self.assertTrue(ready["gui_session_id"])


if __name__ == "__main__":
    unittest.main()
