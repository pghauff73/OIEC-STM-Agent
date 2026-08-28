from __future__ import annotations

import unittest

from ourd_gui.events import AgentEventBus, AgentEventType
from ourd_gui.state import MAX_PROJECTED_CHAT_MESSAGES, GuiState, reduce_event


class GuiStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = AgentEventBus()

    def event(self, event_type: AgentEventType, **kwargs):
        return self.bus.make_event(event_type, **kwargs)

    def test_session_task_and_objects_reduce_deterministically(self) -> None:
        events = [
            self.event(
                AgentEventType.SESSION_OPENED,
                session_id="session",
                payload={"repository_root": "/repo", "source_snapshot": "snapshot"},
            ),
            self.event(
                AgentEventType.TASK_STARTED,
                session_id="session",
                task_id="task",
                payload={"title": "Inspect parser"},
            ),
            self.event(
                AgentEventType.TASK_OBJECTS_ATTACHED,
                session_id="session",
                task_id="task",
                payload={
                    "typed_ids": {
                        "intent": ["intent:sha256:1"],
                        "selection-decision": ["selection-decision:sha256:2"],
                    }
                },
            ),
        ]
        left = GuiState()
        right = GuiState()
        for event in events:
            left = reduce_event(left, event)
            right = reduce_event(right, event)
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(("task",), left.sessions["session"].task_ids)
        self.assertEqual(("intent:sha256:1",), left.tasks["task"].intent_ids)
        self.assertEqual(
            ("selection-decision:sha256:2",), left.tasks["task"].selection_ids
        )

    def test_navigation_back_and_forward(self) -> None:
        state = GuiState()
        for object_id in ("one", "two", "three"):
            state = reduce_event(
                state,
                self.event(
                    AgentEventType.OBJECT_SELECTED,
                    payload={"object_id": object_id},
                ),
            )
        state = reduce_event(state, self.event(AgentEventType.NAVIGATE_BACK))
        self.assertEqual("two", state.selected_object_id)
        state = reduce_event(state, self.event(AgentEventType.NAVIGATE_FORWARD))
        self.assertEqual("three", state.selected_object_id)

    def test_chat_turn_state_and_context_boundary(self) -> None:
        state = GuiState()
        state = reduce_event(
            state,
            self.event(
                AgentEventType.CHAT_MESSAGE_ADDED,
                task_id="task",
                payload={
                    "message_id": "message-1",
                    "turn_id": "turn-1",
                    "role": "user",
                    "content": "Inspect the parser",
                },
            ),
        )
        state = reduce_event(
            state,
            self.event(
                AgentEventType.CHAT_TURN_STARTED,
                task_id="task",
                payload={"turn_id": "turn-1"},
            ),
        )
        self.assertEqual("running", state.chat_status)
        self.assertEqual("turn-1", state.active_chat_turn_id)
        state = reduce_event(
            state,
            self.event(AgentEventType.CHAT_TURN_STOP_REQUESTED, task_id="task"),
        )
        self.assertEqual("stopping", state.chat_status)
        state = reduce_event(
            state,
            self.event(AgentEventType.CHAT_TURN_FINISHED, task_id="task"),
        )
        self.assertEqual("idle", state.chat_status)
        self.assertEqual("", state.active_chat_turn_id)
        state = reduce_event(state, self.event(AgentEventType.CHAT_CONTEXT_CLEARED))
        self.assertEqual(1, state.chat_context_start)

    def test_chat_projection_is_bounded(self) -> None:
        state = GuiState()
        for index in range(MAX_PROJECTED_CHAT_MESSAGES + 3):
            state = reduce_event(
                state,
                self.event(
                    AgentEventType.CHAT_MESSAGE_ADDED,
                    payload={
                        "message_id": f"message-{index}",
                        "turn_id": f"turn-{index}",
                        "role": "user",
                        "content": str(index),
                    },
                ),
            )
        self.assertEqual(MAX_PROJECTED_CHAT_MESSAGES, len(state.chat_messages))
        self.assertEqual("message-3", state.chat_messages[0].message_id)


if __name__ == "__main__":
    unittest.main()
