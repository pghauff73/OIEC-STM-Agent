from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import (
    InteractionConfirmation,
    InteractionConfirmationReceipt,
    InteractionSessionSnapshot,
    PinnedContextSet,
    build_context_envelope,
    build_interaction_confirmation,
    build_interaction_confirmation_receipt,
    build_pinned_context_envelope,
    dispatch_interaction,
    interaction_confirmation_receipt_audit_metadata,
    require_interaction_confirmation_receipt,
    route_interaction,
)
from ourd.workspace import Workspace


class InteractionSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.workspace = Workspace(self.root)
        self.snapshot = InteractionSessionSnapshot(
            repository_root=str(self.root),
            source_snapshot="a" * 64,
            provider="llama_cpp_process",
            model="qwen3.8-27b-direct",
            authority_task_id="task-1",
            mode="read-only",
            context_message_count=4,
            pinned_context_count=2,
            pinned_context_signature="pinned-signature",
            pinned_context_envelope_id="context-envelope:test",
            pinned_context_source_snapshot="a" * 64,
            pinned_context_freshness="FRESH",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def dispatch(self, text: str):
        return dispatch_interaction(
            route_interaction(text, self.workspace),
            self.snapshot,
        )

    def test_natural_language_runs_through_governed_agent(self) -> None:
        directive = self.dispatch("inspect @README.md")
        self.assertEqual("RUN_AGENT", directive.action)
        self.assertEqual("INSPECT", dict(directive.payload)["mode"])
        self.assertFalse(directive.authoritative)

    def test_status_is_local_and_deterministic(self) -> None:
        first = self.dispatch("/status")
        second = self.dispatch("/status")
        self.assertEqual("LOCAL_REPLY", first.action)
        self.assertIn("qwen3.8-27b-direct", first.message)
        self.assertIn("Context messages: 4", first.message)
        self.assertIn("Pinned context paths: 2", first.message)
        self.assertIn("Pinned context freshness: FRESH", first.message)
        self.assertEqual(first.signature, second.signature)

    def test_model_change_requires_restart_and_confirmation(self) -> None:
        directive = self.dispatch("/model another-model")
        self.assertEqual("RESTART_REQUIRED", directive.action)
        self.assertTrue(directive.requires_confirmation)

    def test_route_only_confirmation_receipt_remains_context_free(self) -> None:
        directive = self.dispatch("/model another-model")
        confirmation = build_interaction_confirmation(directive)
        receipt = build_interaction_confirmation_receipt(
            confirmation,
            accepted=True,
        )
        self.assertEqual("ROUTE", confirmation.binding_kind)
        self.assertEqual("", confirmation.context_envelope_id)
        self.assertEqual("", receipt.model_input_sha256)
        require_interaction_confirmation_receipt(
            confirmation,
            receipt,
            current_source_snapshot_hash=self.workspace.snapshot_hash(),
        )

    def test_route_only_receipt_rejects_stray_context_binding(self) -> None:
        directive = self.dispatch("/model another-model")
        confirmation = build_interaction_confirmation(directive)
        receipt = build_interaction_confirmation_receipt(
            confirmation,
            accepted=True,
        )
        with self.assertRaisesRegex(ValueError, "cannot carry context bindings"):
            InteractionConfirmationReceipt.from_dict(
                {
                    **receipt.__dict__,
                    "source_snapshot_hash": "a" * 64,
                    "receipt_id": "",
                    "signature": "",
                }
            )

    def test_approval_is_not_executed_by_dispatcher(self) -> None:
        directive = self.dispatch("/approve plan-1")
        self.assertEqual("GOVERNANCE_REQUIRED", directive.action)
        self.assertTrue(directive.requires_confirmation)
        self.assertIn("EON approval surface", directive.message)

    def test_projection_command_never_invokes_model(self) -> None:
        directive = self.dispatch("/topology")
        self.assertEqual("SHOW_PROJECTION", directive.action)
        self.assertEqual("projection.topology", dict(directive.payload)["target"])

    def test_attach_builds_draft_context_without_invoking_model(self) -> None:
        directive = self.dispatch('/attach "README.md"')
        self.assertEqual("ATTACH_CONTEXT", directive.action)
        self.assertIn("read-only draft context envelope", directive.message)
        self.assertFalse(directive.authoritative)

    def test_detach_updates_context_without_invoking_model(self) -> None:
        directive = self.dispatch('/detach "README.md"')
        self.assertEqual("DETACH_CONTEXT", directive.action)
        self.assertIn("removed from future", directive.message)
        self.assertFalse(directive.authoritative)

    def test_context_refresh_rebuilds_without_invoking_model(self) -> None:
        directive = self.dispatch("/context --refresh")
        self.assertEqual("REFRESH_CONTEXT", directive.action)
        self.assertIn("exact current workspace snapshot", directive.message)
        self.assertFalse(directive.authoritative)

    def test_confirmation_is_deterministic_and_non_authoritative(self) -> None:
        directive = self.dispatch("fix @README.md")
        route = directive.route
        assert route is not None
        envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        first = build_interaction_confirmation(
            directive,
            context_envelope=envelope,
        )
        second = build_interaction_confirmation(
            directive,
            context_envelope=envelope,
        )
        self.assertEqual(first.confirmation_id, second.confirmation_id)
        self.assertEqual(first.signature, second.signature)
        self.assertFalse(first.authoritative)
        self.assertEqual(envelope.envelope_id, first.context_envelope_id)
        self.assertEqual(envelope.source_snapshot_hash, first.source_snapshot_hash)
        self.assertIn("Mode: WRITE", first.render_text())
        self.assertIn("Context envelope:", first.render_text())
        self.assertIn("does not grant authority", first.render_text())
        restored = InteractionConfirmation.from_dict(first.__dict__)
        self.assertEqual(first.signature, restored.signature)

    def test_confirmation_identity_changes_with_exact_envelope(self) -> None:
        directive = self.dispatch("fix @README.md")
        route = directive.route
        assert route is not None
        first_envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        first = build_interaction_confirmation(
            directive,
            context_envelope=first_envelope,
        )
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        second_envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        second = build_interaction_confirmation(
            directive,
            context_envelope=second_envelope,
        )
        self.assertNotEqual(first.confirmation_id, second.confirmation_id)
        self.assertNotEqual(first.model_input_sha256, second.model_input_sha256)

    def test_confirmation_binds_fresh_pinned_draft(self) -> None:
        pins = PinnedContextSet().add(self.workspace, ("README.md",))
        routed_text = pins.apply_to("fix parser", self.workspace)
        route = route_interaction(routed_text, self.workspace)
        directive = dispatch_interaction(route, self.snapshot)
        snapshot = self.workspace.snapshot_hash()
        envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=snapshot,
        )
        pinned_envelope = build_pinned_context_envelope(
            pins,
            self.workspace,
            source_snapshot_hash=snapshot,
        )
        assert pinned_envelope is not None
        confirmation = build_interaction_confirmation(
            directive,
            context_envelope=envelope,
            pinned_context=pins,
            pinned_context_envelope=pinned_envelope,
        )
        self.assertEqual(pins.context_id, confirmation.pinned_context_id)
        self.assertEqual(pinned_envelope.envelope_id, confirmation.pinned_context_envelope_id)
        self.assertEqual("FRESH", confirmation.pinned_context_freshness)

    def test_accepted_receipt_is_exact_and_stale_snapshot_is_blocked(self) -> None:
        directive = self.dispatch("fix @README.md")
        route = directive.route
        assert route is not None
        snapshot = self.workspace.snapshot_hash()
        envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=snapshot,
        )
        confirmation = build_interaction_confirmation(
            directive,
            context_envelope=envelope,
        )
        accepted = build_interaction_confirmation_receipt(
            confirmation,
            accepted=True,
        )
        restored = InteractionConfirmationReceipt.from_dict(accepted.__dict__)
        self.assertEqual(accepted.signature, restored.signature)
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            InteractionConfirmationReceipt.from_dict(
                {**accepted.__dict__, "signature": "tampered"}
            )
        with self.assertRaisesRegex(ValueError, "cannot bind context"):
            InteractionConfirmationReceipt.from_dict(
                {
                    **accepted.__dict__,
                    "pinned_context_id": "pinned-context:stray",
                    "receipt_id": "",
                    "signature": "",
                }
            )
        metadata = interaction_confirmation_receipt_audit_metadata(accepted)
        self.assertFalse(metadata["confirmation_prompt_body_persisted"])
        self.assertFalse(metadata["confirmation_model_input_body_persisted"])
        self.assertNotIn("fixture", str(metadata))
        require_interaction_confirmation_receipt(
            confirmation,
            accepted,
            current_source_snapshot_hash=snapshot,
            context_envelope=envelope,
        )
        rejected = build_interaction_confirmation_receipt(
            confirmation,
            accepted=False,
        )
        with self.assertRaisesRegex(PolicyError, "was not accepted"):
            require_interaction_confirmation_receipt(
                confirmation,
                rejected,
                current_source_snapshot_hash=snapshot,
                context_envelope=envelope,
            )
        (self.root / "README.md").write_text("drifted\n", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "source snapshot is stale"):
            require_interaction_confirmation_receipt(
                confirmation,
                accepted,
                current_source_snapshot_hash=self.workspace.snapshot_hash(),
                context_envelope=envelope,
            )

    def test_confirmation_rejects_non_confirming_directive(self) -> None:
        directive = self.dispatch("inspect @README.md")
        with self.assertRaisesRegex(ValueError, "does not require confirmation"):
            build_interaction_confirmation(directive)

    def test_confirmation_rejects_missing_context_envelope(self) -> None:
        directive = self.dispatch("fix @README.md")
        with self.assertRaisesRegex(ValueError, "requires an exact context envelope"):
            build_interaction_confirmation(directive)


if __name__ == "__main__":
    unittest.main()
