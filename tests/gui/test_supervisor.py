from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ourd_gui.supervisor import supervise_command


class SupervisorTests(unittest.TestCase):
    def test_failed_child_is_restarted_once_then_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "child.py"
            script.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "counter = Path(sys.argv[1])\n"
                "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(count))\n"
                "raise SystemExit(7 if count == 1 else 0)\n",
                encoding="utf-8",
            )
            exit_code = supervise_command(
                [sys.executable, str(script), str(root / "count.txt")],
                repository_root=root,
                max_restarts=1,
                poll_seconds=0.01,
            )
            self.assertEqual(0, exit_code)
            status = json.loads(
                (root / ".ourd-agent" / "supervisor" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("STOPPED", status["state"])
            self.assertEqual(1, status["restart_count"])
            incidents = list(
                (root / ".ourd-agent" / "supervisor" / "incidents").glob("*.json")
            )
            self.assertEqual(1, len(incidents))

    def test_restart_circuit_opens_after_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "child.py"
            script.write_text("raise SystemExit(5)\n", encoding="utf-8")
            exit_code = supervise_command(
                [sys.executable, str(script)],
                repository_root=root,
                max_restarts=0,
                poll_seconds=0.01,
            )
            self.assertEqual(5, exit_code)
            status = json.loads(
                (root / ".ourd-agent" / "supervisor" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("FAILED", status["state"])
            self.assertEqual("restart circuit open", status["message"])

    def test_api_key_is_redacted_from_supervisor_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "child.py"
            script.write_text("raise SystemExit(0)\n", encoding="utf-8")
            supervise_command(
                [sys.executable, str(script), "--api-key", "secret-value"],
                repository_root=root,
                max_restarts=0,
                poll_seconds=0.01,
            )
            events = (
                root / ".ourd-agent" / "supervisor" / "events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertNotIn("secret-value", events)
            self.assertIn("<redacted>", events)

    def test_debug_stdout_mirrors_supervisor_events_and_child_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "child.py"
            script.write_text(
                "import sys\n"
                "print('child stdout ready api_key=secret-value')\n"
                "print('child stderr ready', file=sys.stderr)\n"
                "raise SystemExit(0)\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = supervise_command(
                    [sys.executable, str(script)],
                    repository_root=root,
                    max_restarts=0,
                    poll_seconds=0.01,
                    debug_stdout=True,
                )
            self.assertEqual(0, exit_code)
            records = [
                json.loads(line)
                for line in stdout.getvalue().splitlines()
                if line.strip()
            ]
            streams = {record["debug_stream"] for record in records}
            self.assertIn("supervisor_event", streams)
            self.assertIn("child_output", streams)
            rendered = json.dumps(records, sort_keys=True)
            self.assertIn("child stdout ready api_key=<redacted>", rendered)
            self.assertIn("child stderr ready", rendered)
            self.assertNotIn("secret-value", rendered)


if __name__ == "__main__":
    unittest.main()
