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
    def projection(
        self,
        signature: str,
        *,
        evidence=(),
        collisions=(),
        control=(),
        hypothesis_definitions=(),
        hypothesis_evidence=(),
    ) -> VerifiedProjection:
        return VerifiedProjection(
            workspace_snapshot_hash="snapshot",
            evidence_atoms=tuple(evidence),
            collision_atoms=tuple(collisions),
            control_atoms=tuple(control),
            hypothesis_definition_atoms=tuple(hypothesis_definitions),
            hypothesis_evidence_atoms=tuple(hypothesis_evidence),
            boundary_uncertainty_bp=0,
            signature=signature,
        )

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
        projection = self.projection("same")
        assessment = LoopProgressController().assess(
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
        before = self.projection("before")
        after = self.projection("after", evidence=("evidence:new",))
        assessment = LoopProgressController().assess(
            before=before,
            after=after,
            step_signature="read-new-evidence",
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.certificate.accepted)
        self.assertEqual(1, assessment.new_evidence_count)
        self.assertIn("novel_evidence", assessment.certificate.reasons)

    def test_hypothesis_definition_is_control_only(self) -> None:
        before = self.projection("before")
        after = self.projection("after", hypothesis_definitions=("h:def",))
        assessment = LoopProgressController(max_control_only_progress=2).assess(
            before=before,
            after=after,
            step_signature="propose-hypothesis",
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.control_only)
        self.assertEqual(1, assessment.control_only_streak)
        self.assertIn("bounded_control_progress", assessment.certificate.reasons)
        self.assertEqual(0, assessment.certificate.hypothesis_resolution_bp)

    def test_grounded_hypothesis_link_is_bookkeeping_not_independent_epistemic_progress(self) -> None:
        before = self.projection("before", hypothesis_definitions=("h:def",))
        after = self.projection(
            "after",
            hypothesis_definitions=("h:def",),
            hypothesis_evidence=("h:evidence",),
        )
        assessment = LoopProgressController(
            max_control_only_progress=2,
            initial_control_only_streak=1,
        ).assess(
            before=before,
            after=after,
            step_signature="link-grounded-evidence",
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.control_only)
        self.assertEqual(2, assessment.control_only_streak)
        self.assertGreater(assessment.certificate.hypothesis_resolution_bp, 0)
        self.assertIn("hypothesis_bookkeeping", assessment.certificate.reasons)
        self.assertIn("bounded_control_progress", assessment.certificate.reasons)
        self.assertNotIn("novel_evidence", assessment.certificate.reasons)

    def test_hypothesis_link_cannot_reset_exhausted_control_budget_without_new_evidence(self) -> None:
        before = self.projection("before", hypothesis_definitions=("h:def",))
        after = self.projection(
            "after",
            hypothesis_definitions=("h:def",),
            hypothesis_evidence=("h:evidence",),
        )
        assessment = LoopProgressController(
            max_control_only_progress=2,
            initial_control_only_streak=2,
        ).assess(
            before=before,
            after=after,
            step_signature="link-existing-evidence",
        )
        self.assertFalse(assessment.allowed)
        self.assertEqual(3, assessment.control_only_streak)
        self.assertFalse(assessment.certificate.accepted)
        self.assertEqual("CONTROL_ONLY_BUDGET_EXHAUSTED", assessment.cycle_kind)

    def test_control_only_progress_is_bounded_to_two_consecutive_transitions(self) -> None:
        controller = LoopProgressController(max_control_only_progress=2)
        s0 = self.projection("s0")
        s1 = self.projection("s1", control=("control:a",))
        s2 = self.projection("s2", control=("control:a", "control:b"))
        s3 = self.projection("s3", control=("control:a", "control:b", "control:c"))
        first = controller.assess(before=s0, after=s1, step_signature="control-A")
        second = controller.assess(before=s1, after=s2, step_signature="control-B")
        third = controller.assess(before=s2, after=s3, step_signature="control-C")
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(third.allowed)
        self.assertEqual(3, third.control_only_streak)
        self.assertFalse(third.certificate.accepted)
        self.assertEqual("CONTROL_ONLY_BUDGET_EXHAUSTED", third.cycle_kind)

    def test_epistemic_evidence_resets_persistent_control_streak(self) -> None:
        controller = LoopProgressController(max_control_only_progress=2)
        s0 = self.projection("s0")
        s1 = self.projection("s1", control=("control:a",))
        s2 = self.projection("s2", control=("control:a",), evidence=("e:new",))
        s3 = self.projection("s3", control=("control:a", "control:b"), evidence=("e:new",))
        first = controller.assess(before=s0, after=s1, step_signature="control-A")
        evidence = controller.assess(before=s1, after=s2, step_signature="read-E")
        next_control = controller.assess(before=s2, after=s3, step_signature="control-B")
        self.assertEqual(1, first.control_only_streak)
        self.assertEqual(0, evidence.control_only_streak)
        self.assertEqual(1, next_control.control_only_streak)
        self.assertTrue(next_control.allowed)

    def test_new_evidence_and_hypothesis_link_same_transition_resets_streak(self) -> None:
        before = self.projection("before", hypothesis_definitions=("h:def",))
        after = self.projection(
            "after",
            evidence=("e:new",),
            hypothesis_definitions=("h:def",),
            hypothesis_evidence=("h:evidence",),
        )
        assessment = LoopProgressController(
            max_control_only_progress=2,
            initial_control_only_streak=2,
        ).assess(
            before=before,
            after=after,
            step_signature="read-and-link",
        )
        self.assertTrue(assessment.allowed)
        self.assertFalse(assessment.control_only)
        self.assertEqual(0, assessment.control_only_streak)
        self.assertIn("novel_evidence", assessment.certificate.reasons)
        self.assertIn("hypothesis_bookkeeping", assessment.certificate.reasons)

    def test_repeated_control_only_semantic_step_is_cycle(self) -> None:
        controller = LoopProgressController(max_period=2, max_control_only_progress=2)
        start = self.projection("s0")
        middle = self.projection("s1", control=("control:a",))
        end = self.projection("s2", control=("control:a", "control:b"))
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

    def test_bounded_for_style_iterations_accept_distinct_verified_pages(self) -> None:
        controller = LoopProgressController(max_period=2)
        before = self.projection("page-0")
        for index in range(1, 7):
            after = self.projection(
                f"page-{index}",
                evidence=tuple(f"page:{page}" for page in range(1, index + 1)),
            )
            assessment = controller.assess(
                before=before,
                after=after,
                step_signature=f"list-files-offset-{(index - 1) * 100}",
            )
            self.assertTrue(assessment.allowed)
            self.assertEqual(1, assessment.new_evidence_count)
            before = after

    def test_terminal_response_always_gets_certificate_but_not_fact_status(self) -> None:
        projection = self.projection("same")
        assessment = LoopProgressController(initial_control_only_streak=2).assess(
            before=projection,
            after=projection,
            step_signature="final",
            terminal=True,
        )
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.certificate.terminal)
        self.assertIn("terminal", assessment.certificate.reasons)
        self.assertEqual(0, assessment.control_only_streak)


if __name__ == "__main__":
    unittest.main()
