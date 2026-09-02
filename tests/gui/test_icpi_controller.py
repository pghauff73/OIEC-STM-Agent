from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import (
    PinnedContextSet,
    build_context_envelope,
    build_interaction_confirmation,
    build_interaction_confirmation_receipt,
    build_pinned_context_envelope,
    compare_context_envelopes,
    route_interaction,
)
from ourd.interaction import InteractionSessionSnapshot, dispatch_interaction
from ourd.workspace import Workspace
from ourd_gui.controller import GuiController
from ourd_gui.events import AgentEventType
from ourd_gui.qwen_bootstrap import QwenBootstrapResult


class ICPIControllerTests(unittest.TestCase):
    @staticmethod
    def wait_for_idle(controller: GuiController, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, failures = controller.drain_events()
            if failures:
                raise failures[0]
            if not controller._active_chat_operation_id and not controller._pending:
                controller.drain_events()
                return
            time.sleep(0.01)
        raise AssertionError("controller did not become idle")

    def test_local_command_is_journaled_with_route_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            try:
                route = route_interaction("/status", Workspace(root))
                controller.record_icpi_exchange(
                    "/status",
                    "status fixture",
                    route=route,
                    action="LOCAL_REPLY",
                )
                events, failures = controller.drain_events()
                self.assertEqual([], failures)
                self.assertEqual("/status", controller.state.chat_messages[-2].content)
                self.assertEqual("status fixture", controller.state.chat_messages[-1].content)
                activity = [
                    event
                    for event in events
                    if event.event_type == AgentEventType.CHAT_ACTIVITY
                    and event.payload.get("trace_type") == "icpi_local_command"
                ]
                self.assertEqual(1, len(activity))
                self.assertEqual(route.route_id, activity[0].payload["route_id"])
            finally:
                controller.close()
                controller.drain_events()

    def test_qwen_bootstrap_is_journaled_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            try:
                result = QwenBootstrapResult(
                    requested_model="qwen3.8:27B-Fast",
                    resolved_model="qwen3.8-27b-fast:latest",
                    model_digest="07cb98f8840c",
                    model_size=13,
                    ollama_version="0.32.14",
                    service_started=True,
                    warmed=True,
                    resident=True,
                    size_vram=12,
                    log_path="/tmp/ollama.log",
                )
                controller.record_qwen_bootstrap(result)
                events, failures = controller.drain_events()
                self.assertEqual([], failures)
                event = next(
                    item
                    for item in events
                    if item.payload.get("trace_type") == "icpi_qwen_bootstrap"
                )
                self.assertEqual(result.model_digest, event.payload["model_digest"])
                self.assertFalse(event.payload["api_key_persisted"])
                serialized = json.dumps(event.payload, sort_keys=True)
                self.assertNotIn("api_key", serialized.replace("api_key_persisted", ""))
            finally:
                controller.close()
                controller.drain_events()

    def test_provider_preflight_runs_as_chat_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            controller = GuiController(root)
            controller.gateway.provider_preflight = lambda: {
                "ok": True,
                "model": "qwen3.8-27b-direct",
            }
            try:
                route = route_interaction("/preflight", Workspace(root))
                controller.submit_provider_preflight(route=route)
                self.wait_for_idle(controller)
                response = controller.state.chat_messages[-1]
                self.assertEqual("assistant", response.role)
                self.assertEqual(
                    {"model": "qwen3.8-27b-direct", "ok": True},
                    json.loads(response.content),
                )
            finally:
                controller.close()
                controller.drain_events()

    def test_context_envelope_is_model_input_while_transcript_keeps_user_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            requests = []

            def chat_turn(message, history, *, event_callback, cancel_check):
                del history, event_callback, cancel_check
                requests.append(message)
                return "done"

            controller.gateway.chat_turn = chat_turn
            try:
                route = route_interaction("inspect @file[README.md]", workspace)
                pinned_context = PinnedContextSet().add(workspace, ("README.md",))
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                pinned_envelope = build_pinned_context_envelope(
                    pinned_context,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                assert pinned_envelope is not None
                controller.submit_chat_message(
                    "inspect @file[README.md]",
                    route=route,
                    model_input=envelope.model_input,
                    context_envelope=envelope,
                    pinned_context=pinned_context,
                    pinned_context_envelope=pinned_envelope,
                )
                self.wait_for_idle(controller)
                self.assertEqual([envelope.model_input], requests)
                self.assertEqual(
                    "inspect @file[README.md]",
                    controller.state.chat_messages[-2].content,
                )
                route_events = [
                    event
                    for event in controller.journal.events()
                    if event.event_type == AgentEventType.CHAT_ACTIVITY
                    and event.payload.get("trace_type") == "icpi_route"
                ]
                self.assertEqual(envelope.envelope_id, route_events[-1].payload["context_envelope_id"])
                self.assertEqual(1, route_events[-1].payload["context_file_count"])
                serialized_payload = json.dumps(route_events[-1].payload, sort_keys=True)
                self.assertNotIn("fixture", serialized_payload)
                self.assertFalse(
                    route_events[-1].payload["context_preview_bodies_persisted"]
                )
                self.assertEqual(
                    pinned_context.signature,
                    route_events[-1].payload["pinned_context_signature"],
                )
                self.assertEqual(1, route_events[-1].payload["pinned_context_count"])
                self.assertEqual(
                    pinned_envelope.envelope_id,
                    route_events[-1].payload["pinned_context_envelope_id"],
                )
            finally:
                controller.close()
                controller.drain_events()

    def test_stale_pinned_draft_is_rejected_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("before\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            try:
                pinned_context = PinnedContextSet().add(workspace, ("README.md",))
                pinned_envelope = build_pinned_context_envelope(
                    pinned_context,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                assert pinned_envelope is not None
                (root / "README.md").write_text("after\n", encoding="utf-8")
                route = route_interaction("inspect @path[README.md]", workspace)
                current_envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                with self.assertRaisesRegex(PolicyError, "pinned context is stale"):
                    controller.submit_chat_message(
                        "inspect README",
                        route=route,
                        model_input=current_envelope.model_input,
                        context_envelope=current_envelope,
                        pinned_context=pinned_context,
                        pinned_context_envelope=pinned_envelope,
                    )
            finally:
                controller.close()
                controller.drain_events()

    def test_confirmation_required_route_rejects_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            try:
                route = route_interaction("fix @file[README.md]", workspace)
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                with self.assertRaisesRegex(ValueError, "needs an accepted exact receipt"):
                    controller.submit_chat_message(
                        "fix README",
                        route=route,
                        model_input=envelope.model_input,
                        context_envelope=envelope,
                    )
            finally:
                controller.close()
                controller.drain_events()

    def test_accepted_exact_receipt_is_dispatched_and_journaled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            requests = []

            def chat_turn(message, history, *, event_callback, cancel_check):
                del history, event_callback, cancel_check
                requests.append(message)
                return "done"

            controller.gateway.chat_turn = chat_turn
            try:
                route = route_interaction("fix @file[README.md]", workspace)
                directive = dispatch_interaction(
                    route,
                    InteractionSessionSnapshot(
                        repository_root=str(root),
                        source_snapshot=workspace.snapshot_hash(),
                    ),
                )
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                confirmation = build_interaction_confirmation(
                    directive,
                    context_envelope=envelope,
                )
                receipt = build_interaction_confirmation_receipt(
                    confirmation,
                    accepted=True,
                )
                controller.record_confirmation_receipt(receipt)
                controller.submit_chat_message(
                    "fix README",
                    route=route,
                    model_input=envelope.model_input,
                    context_envelope=envelope,
                    confirmation=confirmation,
                    confirmation_receipt=receipt,
                )
                self.wait_for_idle(controller)
                self.assertEqual([envelope.model_input], requests)
                receipt_event = next(
                    item
                    for item in reversed(controller.journal.events())
                    if item.payload.get("trace_type") == "icpi_confirmation_receipt"
                )
                self.assertEqual(
                    receipt.receipt_id,
                    receipt_event.payload["confirmation_receipt_id"],
                )
                route_event = next(
                    item
                    for item in reversed(controller.journal.events())
                    if item.payload.get("trace_type") == "icpi_route"
                )
                self.assertEqual(
                    receipt.signature,
                    route_event.payload["confirmation_receipt_signature"],
                )
                serialized = json.dumps(receipt_event.payload, sort_keys=True)
                self.assertNotIn("fixture", serialized)
                self.assertFalse(
                    receipt_event.payload["confirmation_model_input_body_persisted"]
                )
            finally:
                controller.close()
                controller.drain_events()

    def test_accepted_receipt_is_rechecked_at_worker_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            requests = []
            try:
                route = route_interaction("fix @file[README.md]", workspace)
                snapshot = workspace.snapshot_hash()
                directive = dispatch_interaction(
                    route,
                    InteractionSessionSnapshot(
                        repository_root=str(root),
                        source_snapshot=snapshot,
                    ),
                )
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=snapshot,
                )
                confirmation = build_interaction_confirmation(
                    directive,
                    context_envelope=envelope,
                )
                receipt = build_interaction_confirmation_receipt(
                    confirmation,
                    accepted=True,
                )
                snapshot_calls = 0

                def snapshot_after_dispatch() -> str:
                    nonlocal snapshot_calls
                    snapshot_calls += 1
                    return snapshot if snapshot_calls == 1 else "b" * 64

                def chat_turn(message, history, *, event_callback, cancel_check):
                    del history, event_callback, cancel_check
                    requests.append(message)
                    return "unexpected"

                controller.gateway.snapshot = snapshot_after_dispatch
                controller.gateway.chat_turn = chat_turn
                controller.submit_chat_message(
                    "fix README",
                    route=route,
                    model_input=envelope.model_input,
                    context_envelope=envelope,
                    confirmation=confirmation,
                    confirmation_receipt=receipt,
                )
                self.wait_for_idle(controller)
                self.assertEqual([], requests)
                self.assertIn(
                    "context envelope is stale before model invocation",
                    controller.state.chat_messages[-1].content,
                )
            finally:
                controller.close()
                controller.drain_events()

    def test_rejected_or_stale_receipt_cannot_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            try:
                route = route_interaction("fix @file[README.md]", workspace)
                directive = dispatch_interaction(
                    route,
                    InteractionSessionSnapshot(
                        repository_root=str(root),
                        source_snapshot=workspace.snapshot_hash(),
                    ),
                )
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                confirmation = build_interaction_confirmation(
                    directive,
                    context_envelope=envelope,
                )
                rejected = build_interaction_confirmation_receipt(
                    confirmation,
                    accepted=False,
                )
                with self.assertRaisesRegex(PolicyError, "was not accepted"):
                    controller.submit_chat_message(
                        "fix README",
                        route=route,
                        model_input=envelope.model_input,
                        context_envelope=envelope,
                        confirmation=confirmation,
                        confirmation_receipt=rejected,
                    )
                accepted = build_interaction_confirmation_receipt(
                    confirmation,
                    accepted=True,
                )
                (root / "README.md").write_text("drifted\n", encoding="utf-8")
                with self.assertRaisesRegex(PolicyError, "source snapshot is stale"):
                    controller.submit_chat_message(
                        "fix README",
                        route=route,
                        model_input=envelope.model_input,
                        context_envelope=envelope,
                        confirmation=confirmation,
                        confirmation_receipt=accepted,
                    )
            finally:
                controller.close()
                controller.drain_events()

    def test_pinned_context_must_be_present_in_submitted_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            try:
                route = route_interaction("inspect repository", workspace)
                envelope = build_context_envelope(
                    route,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                pinned_context = PinnedContextSet().add(workspace, ("README.md",))
                with self.assertRaisesRegex(ValueError, "missing from context envelope"):
                    controller.submit_chat_message(
                        "inspect repository",
                        route=route,
                        model_input=envelope.model_input,
                        context_envelope=envelope,
                        pinned_context=pinned_context,
                    )
            finally:
                controller.close()
                controller.drain_events()

    def test_pinned_context_transition_is_journaled_without_preview_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("SENSITIVE-PREVIEW\n", encoding="utf-8")
            workspace = Workspace(root)
            controller = GuiController(root)
            try:
                route = route_interaction('/attach "README.md"', workspace)
                pinned_context = PinnedContextSet().add(workspace, ("README.md",))
                envelope = build_pinned_context_envelope(
                    pinned_context,
                    workspace,
                    source_snapshot_hash=workspace.snapshot_hash(),
                )
                assert envelope is not None
                delta = compare_context_envelopes(envelope, envelope)
                controller.record_pinned_context_transition(
                    route=route,
                    action="ATTACH_CONTEXT",
                    pinned_context=pinned_context,
                    context_envelope=envelope,
                    context_delta=delta,
                )
                controller.drain_events()
                event = next(
                    item
                    for item in reversed(controller.journal.events())
                    if item.payload.get("trace_type") == "icpi_pinned_context"
                )
                self.assertEqual(pinned_context.signature, event.payload["pinned_context_signature"])
                self.assertNotIn("SENSITIVE-PREVIEW", json.dumps(event.payload))
                self.assertFalse(event.payload["preview_bodies_persisted"])
                self.assertEqual("FRESH", event.payload["context_freshness"])
                self.assertEqual(delta.signature, event.payload["context_delta_signature"])
                controller.record_pinned_context_transition(
                    route=None,
                    action="NEW_CONTEXT",
                    pinned_context=pinned_context.clear(),
                )
                controller.drain_events()
                cleared = next(
                    item
                    for item in reversed(controller.journal.events())
                    if item.payload.get("trace_type") == "icpi_pinned_context"
                )
                self.assertEqual("NEW_CONTEXT", cleared.payload["action"])
                self.assertEqual("", cleared.payload["route_id"])
                self.assertEqual(0, cleared.payload["pinned_context_count"])
            finally:
                controller.close()
                controller.drain_events()


if __name__ == "__main__":
    unittest.main()
