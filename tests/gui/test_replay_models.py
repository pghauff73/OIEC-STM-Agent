from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from ourd_gui.events import AgentEventBus, AgentEventType
from ourd_gui.read_models import ReadOnlyEGCFRepository
from ourd_gui.replay_models import compare_tasks, state_at
from ourd_gui.state import GuiTask

from .fixtures_v1 import install_fixture_repository


class ReplayModelTests(unittest.TestCase):
    def test_state_at_reconstructs_only_through_cursor(self) -> None:
        bus = AgentEventBus()
        events = [
            bus.make_event(
                AgentEventType.SESSION_OPENED,
                session_id="s1",
                payload={"repository_root": "/tmp/repo", "source_snapshot": "abc"},
            ),
            bus.make_event(
                AgentEventType.TASK_STARTED,
                session_id="s1",
                task_id="t1",
                payload={"title": "first"},
            ),
            bus.make_event(
                AgentEventType.TASK_FINISHED,
                session_id="s1",
                task_id="t1",
                payload={"status": "COMPLETED"},
            ),
        ]
        middle = state_at(events, 1)
        final = state_at(events, 2)
        self.assertEqual("RUNNING", middle.tasks["t1"].status)
        self.assertEqual("COMPLETED", final.tasks["t1"].status)

    def test_comparison_distinguishes_missing_duration_and_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            repository = ReadOnlyEGCFRepository(root)
            with_execution = GuiTask(
                task_id="with",
                session_id="session",
                title="With execution",
                execution_ids=(bundle.ids["execution"],),
            )
            without_execution = GuiTask(
                task_id="without",
                session_id="session",
                title="Without execution",
            )
            comparison = compare_tasks(repository, with_execution, without_execution)
            self.assertEqual("missing_b", comparison["differences"]["duration"]["state"])
            self.assertEqual("missing_both", comparison["differences"]["cost"]["state"])


if __name__ == "__main__":
    unittest.main()
