from __future__ import annotations

import unittest

from ourd_gui.activity_projection import (
    MAX_ACTIVITY_DETAIL_CHARACTERS,
    project_agent_activity,
)
from ourd_gui.events import AgentEvent, AgentEventType


def activity_event(trace_type: str, trace_payload: object) -> AgentEvent:
    return AgentEvent(
        event_id="event-1",
        sequence=1,
        event_type=AgentEventType.CHAT_ACTIVITY,
        timestamp="2026-08-30T00:00:00Z",
        payload={"trace_type": trace_type, "trace_payload": trace_payload},
    )


class ActivityProjectionTests(unittest.TestCase):
    def test_omits_internal_model_belief_trace(self) -> None:
        event = activity_event(
            "model_belief",
            {"output_text": "large internal response", "semantic_step_signature": "a" * 64},
        )
        self.assertIsNone(project_agent_activity(event))

    def test_model_request_keeps_only_useful_step_details(self) -> None:
        event = activity_event(
            "model_request",
            {
                "step": 3,
                "model": "qwen3.8-27b-direct",
                "input_item_count": 12,
                "context_reduction_count": 2,
                "context_budget_report_signature": "a" * 64,
            },
        )
        self.assertEqual(
            (
                "Thinking",
                "Step 3 · qwen3.8-27b-direct · 12 input items · 2 context reductions",
            ),
            project_agent_activity(event),
        )

    def test_tool_call_uses_selected_bounded_arguments(self) -> None:
        event = activity_event(
            "tool_call",
            {
                "name": "read_file",
                "args": {
                    "path": "ourd_gui/views/conversation.py",
                    "start_line": 1,
                    "end_line": 400,
                    "api_key": "must-not-appear",
                    "content": "x" * 1_000,
                },
            },
        )
        projection = project_agent_activity(event)
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual("Tool", projection[0])
        self.assertIn("read_file", projection[1])
        self.assertIn("path=ourd_gui/views/conversation.py", projection[1])
        self.assertNotIn("must-not-appear", projection[1])
        self.assertNotIn("x" * 20, projection[1])

    def test_tool_failure_shows_error_without_raw_result(self) -> None:
        event = activity_event(
            "tool_result",
            {
                "name": "run_command",
                "result": {
                    "ok": False,
                    "error": "command failed " + "because " * 80,
                    "stdout": "very large output" * 200,
                },
            },
        )
        projection = project_agent_activity(event)
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual("Result", projection[0])
        self.assertIn("run_command · Failed", projection[1])
        self.assertNotIn("stdout", projection[1])
        self.assertLessEqual(len(projection[1]), MAX_ACTIVITY_DETAIL_CHARACTERS)

    def test_final_trace_does_not_duplicate_response_text(self) -> None:
        event = activity_event("final", {"text": "full answer " * 200})
        self.assertEqual(("Finished", "Response ready"), project_agent_activity(event))

    def test_redacted_persisted_context_counts_do_not_break_rendering(self) -> None:
        event = activity_event(
            "context_budget_recovery",
            {
                "verdict": "FIT",
                "overage_tokens": "<redacted>",
                "removed_history_item_count": "<redacted>",
                "compacted_tool_output_count": "<redacted>",
                "dropped_tool_exchange_count": 1,
            },
        )
        self.assertEqual(
            ("Context", "dropped 1 tool exchanges"),
            project_agent_activity(event),
        )


if __name__ == "__main__":
    unittest.main()
