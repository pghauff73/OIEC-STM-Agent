from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from ourd.errors import AgentCancelledError
from ourd_gui.commands import ObjectiveRequest
from ourd_gui.controller import GuiController
from ourd_gui.events import AgentEventType


class GuiControllerTests(unittest.TestCase):
    @staticmethod
    def wait_for_idle(controller: GuiController, timeout: float = 5.0) -> list[AgentEventType]:
        deadline = time.monotonic() + timeout
        observed: list[AgentEventType] = []
        while time.monotonic() < deadline:
            events, failures = controller.drain_events()
            if failures:
                raise failures[0]
            observed.extend(event.event_type for event in events)
            if not controller._active_chat_operation_id and not controller._pending:
                controller.drain_events()
                return observed
            time.sleep(0.01)
        raise AssertionError("controller did not become idle")

    def test_delayed_worker_submission_does_not_block_caller(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            release = threading.Event()
            try:
                started = time.perf_counter()
                controller._submit("", "delayed fixture", lambda: release.wait(2) or {})
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 0.05)
            finally:
                release.set()
                deadline = time.monotonic() + 5
                while controller._pending and time.monotonic() < deadline:
                    controller.drain_events()
                    time.sleep(0.01)
                controller.close()
                controller.drain_events()

    def test_objective_is_bound_to_canonical_objects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            try:
                task_id = controller.submit_objective(
                    ObjectiveRequest("Inspect parser")
                )
                deadline = time.monotonic() + 30
                observed_types: list[AgentEventType] = []
                while time.monotonic() < deadline:
                    events, failures = controller.drain_events()
                    self.assertEqual([], failures)
                    observed_types.extend(event.event_type for event in events)
                    task = controller.state.tasks.get(task_id)
                    if task and task.status in {"COMPLETED", "FAILED"}:
                        break
                    time.sleep(0.02)
                task = controller.state.tasks[task_id]
                self.assertNotEqual("FAILED", task.status)
                self.assertTrue(task.intent_ids)
                self.assertTrue(task.invocation_ids)
                self.assertTrue(task.selection_ids)
                self.assertTrue(task.compiled_workflow_ids)
                self.assertTrue(task.execution_plan_ids)
                self.assertIn(AgentEventType.SELECTION_UPDATED, observed_types)
                self.assertTrue(controller.state.event_head)
            finally:
                controller.close()
                controller.drain_events()

    def test_chat_turn_records_messages_trace_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            requests = []

            def chat_turn(message, history, *, event_callback, cancel_check):
                requests.append((message, list(history)))
                event_callback(
                    {
                        "event_type": "model_request",
                        "event_hash": "a" * 64,
                        "run_id": "run-1",
                        "payload": {"step": 1},
                    }
                )
                return f"answer {len(requests)}"

            controller.gateway.chat_turn = chat_turn
            try:
                controller.submit_chat_message("first")
                observed = self.wait_for_idle(controller)
                controller.submit_chat_message("second")
                observed.extend(self.wait_for_idle(controller))
                self.assertEqual(("first", []), requests[0])
                self.assertEqual(
                    (
                        "second",
                        [
                            {"role": "user", "content": "first"},
                            {"role": "assistant", "content": "answer 1"},
                        ],
                    ),
                    requests[1],
                )
                self.assertEqual(
                    ["user", "assistant", "user", "assistant"],
                    [message.role for message in controller.state.chat_messages],
                )
                self.assertEqual("idle", controller.state.chat_status)
                self.assertIn(AgentEventType.AGENT_STEP, observed)
                self.assertEqual("a" * 64, controller.state.event_head)
            finally:
                controller.close()
                controller.drain_events()

    def test_chat_stop_is_cooperative_and_preserves_audit_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)

            def chat_turn(message, history, *, event_callback, cancel_check):
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if cancel_check():
                        raise AgentCancelledError("stopped")
                    time.sleep(0.01)
                return "unexpected"

            controller.gateway.chat_turn = chat_turn
            try:
                controller.submit_chat_message("wait")
                controller.drain_events()
                self.assertTrue(controller.stop_chat())
                observed = self.wait_for_idle(controller)
                self.assertIn(AgentEventType.CHAT_TURN_STOP_REQUESTED, observed)
                self.assertEqual("idle", controller.state.chat_status)
                self.assertEqual("system", controller.state.chat_messages[-1].role)
                self.assertEqual("cancelled", controller.state.chat_messages[-1].status)
                self.assertFalse(controller.stop_chat())
            finally:
                controller.close()
                controller.drain_events()

    def test_new_chat_keeps_audit_log_but_clears_model_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            requests = []

            def chat_turn(message, history, *, event_callback, cancel_check):
                requests.append(list(history))
                return "answer"

            controller.gateway.chat_turn = chat_turn
            try:
                controller.submit_chat_message("first")
                self.wait_for_idle(controller)
                controller.new_chat_context()
                controller.drain_events()
                controller.submit_chat_message("second")
                self.wait_for_idle(controller)
                self.assertEqual([], requests[0])
                self.assertEqual([], requests[1])
                self.assertEqual(5, len(controller.state.chat_messages))
                self.assertEqual("system", controller.state.chat_messages[2].role)
                self.assertEqual(3, controller.state.chat_context_start)
            finally:
                controller.close()
                controller.drain_events()


if __name__ == "__main__":
    unittest.main()
