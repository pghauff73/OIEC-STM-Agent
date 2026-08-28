from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ourd.persistence import EventStore
from ourd_gui.events import AgentEventBus, AgentEventType
from ourd_gui.persistence import (
    CoreEventTailer,
    GuiEventJournal,
    GuiExportStore,
    GuiPreferences,
    GuiPreferencesStore,
    GuiProjectionStore,
    read_complete_json_lines,
)


class GuiPersistenceTests(unittest.TestCase):
    def test_preferences_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = GuiPreferencesStore(root)
            preferences = GuiPreferences(
                window_geometry="900x700",
                recent_repositories=("/one", "/two"),
                reduced_motion=True,
            )
            store.save(preferences)
            self.assertEqual(preferences, store.load())

    def test_assurance_export_is_bounded_to_gui_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = GuiExportStore(root).save_assurance(
                "assurance-case:sha256:" + "a" * 64,
                "markdown",
                "# record\n",
            )
            self.assertEqual(
                root / ".ourd-agent" / "gui" / "exports" / f"assurance-{'a' * 64}.md",
                path,
            )
            self.assertEqual("# record\n", path.read_text(encoding="utf-8"))

    def test_gui_event_journal_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bus = AgentEventBus()
            event = bus.make_event(
                AgentEventType.TASK_STARTED,
                session_id="session",
                task_id="task",
                payload={"title": "Task"},
            )
            journal = GuiEventJournal(root)
            journal.append(event)
            self.assertEqual([event], journal.events())

    def test_core_tailer_ignores_partial_final_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / ".ourd-agent" / "egcf" / "events.jsonl"
            store = EventStore(path)
            first = store.append("first", {"ok": True})
            with path.open("ab") as handle:
                handle.write(b'{"partial":')
            parsed = read_complete_json_lines(path)
            self.assertEqual([first], parsed)
            tailer = CoreEventTailer(root)
            self.assertEqual([first], tailer.poll())

    def test_projection_rebuild_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bus = AgentEventBus()
            events = [
                bus.make_event(
                    AgentEventType.SESSION_OPENED,
                    session_id="session",
                    payload={"repository_root": str(root), "source_snapshot": "snapshot"},
                ),
                bus.make_event(
                    AgentEventType.TASK_STARTED,
                    session_id="session",
                    task_id="task",
                    payload={"title": "Task"},
                ),
            ]
            projection = GuiProjectionStore(root)
            state = projection.rebuild(events)
            self.assertEqual(state, projection.load(expected_event_count=2))
            connection = projection._connect()
            try:
                with connection:
                    connection.execute(
                        "UPDATE metadata SET value = 'invalid' WHERE key = 'state_digest'"
                    )
            finally:
                connection.close()
            self.assertIsNone(projection.load(expected_event_count=2))

    def test_chat_projection_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bus = AgentEventBus()
            events = [
                bus.make_event(
                    AgentEventType.CHAT_MESSAGE_ADDED,
                    task_id="task",
                    payload={
                        "message_id": "message",
                        "turn_id": "turn",
                        "role": "user",
                        "content": "hello",
                    },
                ),
                bus.make_event(
                    AgentEventType.CHAT_TURN_STARTED,
                    task_id="task",
                    payload={"turn_id": "turn"},
                ),
            ]
            projection = GuiProjectionStore(root)
            state = projection.rebuild(events)
            loaded = projection.load(expected_event_count=len(events))
            self.assertEqual(state, loaded)
            self.assertEqual("hello", loaded.chat_messages[0].content)
            self.assertEqual("running", loaded.chat_status)


if __name__ == "__main__":
    unittest.main()
