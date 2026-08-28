from __future__ import annotations

import unittest

from ourd.loop_control import (
    LoopProgressController,
    VerifiedProjection,
    model_belief_record,
    semantic_step_signature,
    verified_projection,
)
from ourd.models import EvidenceArtifact, RuntimeState


class LoopControlTests(unittest.TestCase):
    def test_model_belief_does_not_mutate_verified_projection(self) -> None:
        state = RuntimeState()
        before = verified_projection(state, "snapshot")
        record = model_belief_record(
            step=1,
            output_text="I strongly believe this is correct.",
            calls=[],
        )
        after = verified_projection(state, "snapshot")
        self.assertEqual("UNVERIFIED_MODEL_BELIEF", record["epistemic_status"])
        self.assertEqual(before.signature, after.signature)

    def test_semantic_signature_ignores_runtime_identity_churn(self) -> None:
        first = semantic_step_signature(
            [
                (
                    "read_file",
                    {
                        "path": "README.md",
                        "start_line": 1,
                        "end_line": 20,
                        "artifact_id": "evidence:first",
                        "call_id": "call:first",
                    },
                )
            ]
        )
        second = semantic_step_signature(
            [
                (
                    "read_file",
                    {
                        "path": "README.md",
                        "start_line": 1,
                        "end_line": 20,
                        "artifact_id": "evidence:second",
                        "call_id": "call:second",
                    },
                )
            ]
        )
        self.assertEqual(first, second)

    def test_duplicate_evidence_ids_do_not_create_verified_progress(self) -> None:
        state = RuntimeState()
        state.evidence_registry["e1"] = EvidenceArtifact(
            artifact_id="e1",
            kind="read",
            description="README.md",
            sha256="a" * 64,
            source_snapshot_hash="snapshot",
            path="README.md",
            success=True,
        )
        first = verified_projection(state, "snapshot")
        state.evidence_registry["e2"] = EvidenceArtifact(
            artifact_id="e2",
            kind="read",
            description="README.md",
            sha256="a" * 64,
            source_snapshot_hash="snapshot",
            path="README.md",
            success=True,
        )
        second = verified_projection(state, "snapshot")
        self.assertEqual(first.evidence_atoms, second.evidence_atoms)
        self.assertEqual(first.signature, second.signature)

    def test_nonterminal_no_verified_change_is_blocked(self) -> None:
        projection = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=(),
            boundary_uncertainty_bp=0,
            signature="same",
        )
        controller = LoopProgressController()
        assessment = controller.assess(
            before=projection,
            after=projection,
            step_signature="step",
            terminal=False,
        )
        self.assertFalse(assessment.allowed)
        self.assertFalse(assessment.certificate.accepted)
        self.assertEqual("NO_VERIFIED_PROGRESS", assessment.cycle_kind)
        self.assertEqual("CYCLE_STOP", assessment.terminal_state)

    def test_novel_verified_evidence_accepts_progress(self) -> None:
        before = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=(),
            boundary_uncertainty_bp=0,
            signature="before",
        )
        after = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=("evidence:new",),
            collision_atoms=(),
            control_atoms=(),
            boundary_uncertainty_bp=0,
            signature="after",
        )
        assessment = LoopProgressController().assess(
            before=before,
            after=after,
            step_signature="read-new-evidence",
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.certificate.accepted)
        self.assertEqual(1, assessment.new_evidence_count)
        self.assertIn("novel_evidence", assessment.certificate.reasons)

    def test_repeated_control_only_semantic_step_is_cycle(self) -> None:
        controller = LoopProgressController(max_period=2)
        start = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=(),
            boundary_uncertainty_bp=0,
            signature="s0",
        )
        middle = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=("control:a",),
            boundary_uncertainty_bp=0,
            signature="s1",
        )
        end = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=("control:a", "control:b"),
            boundary_uncertainty_bp=0,
            signature="s2",
        )
        first = controller.assess(
            before=start,
            after=middle,
            step_signature="semantic-A",
        )
        second = controller.assess(
            before=middle,
            after=end,
            step_signature="semantic-A",
        )
        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual("SEMANTIC_PERIODIC_CYCLE", second.cycle_kind)
        self.assertEqual(1, second.period)

    def test_terminal_response_always_gets_certificate_but_not_fact_status(self) -> None:
        projection = VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=(),
            collision_atoms=(),
            control_atoms=(),
            boundary_uncertainty_bp=0,
            signature="same",
        )
        assessment = LoopProgressController().assess(
            before=projection,
            after=projection,
            step_signature="final",
            terminal=True,
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.certificate.terminal)
        self.assertIn("terminal", assessment.certificate.reasons)


if __name__ == "__main__":
    unittest.main()
