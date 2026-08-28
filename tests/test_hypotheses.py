from __future__ import annotations

import unittest

from ourd.errors import PolicyError
from ourd.hypotheses import (
    bounded_hypothesis_set,
    link_hypothesis_evidence,
    make_hypothesis,
)
from ourd.models import EvidenceArtifact, HypothesisSet


class HypothesisStateTests(unittest.TestCase):
    def proposal(self, proposition: str, *, prior: int = 5_000) -> dict:
        return {
            "proposition": proposition,
            "model_prior_bp": prior,
            "assumptions": ["same boundary"],
            "predictions": ["observable consequence"],
            "falsifiers": ["counterexample"],
        }

    def evidence(self, artifact_id: str, digest: str, quality: int = 7_000) -> EvidenceArtifact:
        return EvidenceArtifact(
            artifact_id=artifact_id,
            kind="test",
            description="grounded observation",
            sha256=digest,
            source_snapshot_hash="snapshot",
            success=True,
            quality_bp=quality,
        )

    def test_hypothesis_identity_is_content_addressed_and_prior_churn_is_not_novelty(self) -> None:
        first = make_hypothesis(**self.proposal("Parser precedence is wrong", prior=3_000))
        whitespace = make_hypothesis(**self.proposal("Parser   precedence is   wrong", prior=3_000))
        confidence_churn = make_hypothesis(**self.proposal("Parser precedence is wrong", prior=9_000))
        self.assertEqual(first.hypothesis_id, whitespace.hypothesis_id)
        self.assertEqual(first.hypothesis_id, confidence_churn.hypothesis_id)
        self.assertNotEqual(first.model_prior_bp, confidence_churn.model_prior_bp)
        self.assertEqual("UNVERIFIED_PROPOSITION", first.verification_status)

    def test_duplicate_hypothesis_does_not_expand_pool(self) -> None:
        state, added = bounded_hypothesis_set(
            None,
            [self.proposal("A", prior=2_000), self.proposal("A", prior=8_000)],
            max_hypotheses=2,
        )
        self.assertEqual(1, len(state.hypotheses))
        self.assertEqual(1, len(added))
        self.assertEqual(2_000, state.hypotheses[0].model_prior_bp)

    def test_hypothesis_bound_fails_closed(self) -> None:
        with self.assertRaises(PolicyError):
            bounded_hypothesis_set(
                None,
                [self.proposal("A"), self.proposal("B"), self.proposal("C")],
                max_hypotheses=2,
            )

    def test_grounded_support_changes_bookkeeping_not_truth_status(self) -> None:
        state, _ = bounded_hypothesis_set(None, [self.proposal("A")], max_hypotheses=2)
        hypothesis_id = state.hypotheses[0].hypothesis_id
        registry = {"e1": self.evidence("e1", "a" * 64)}
        updated, changed = link_hypothesis_evidence(
            state,
            registry,
            hypothesis_id=hypothesis_id,
            evidence_id="e1",
            relation="supports",
        )
        self.assertTrue(changed)
        hypothesis = updated.hypotheses[0]
        self.assertEqual("SUPPORTED_BY_LINKED_EVIDENCE", hypothesis.status)
        self.assertEqual("UNVERIFIED_PROPOSITION", hypothesis.verification_status)
        self.assertGreater(hypothesis.evidence_support_bp, 0)

    def test_material_falsifier_marks_linked_evidence_status(self) -> None:
        state, _ = bounded_hypothesis_set(None, [self.proposal("A")], max_hypotheses=2)
        hypothesis_id = state.hypotheses[0].hypothesis_id
        registry = {"e1": self.evidence("e1", "b" * 64, quality=8_000)}
        updated, _ = link_hypothesis_evidence(
            state,
            registry,
            hypothesis_id=hypothesis_id,
            evidence_id="e1",
            relation="falsifies",
        )
        self.assertEqual(
            "FALSIFIED_BY_LINKED_EVIDENCE",
            updated.hypotheses[0].status,
        )
        self.assertEqual("UNVERIFIED_PROPOSITION", updated.hypotheses[0].verification_status)

    def test_duplicate_grounded_evidence_content_cannot_be_recycled_under_new_relation(self) -> None:
        state, _ = bounded_hypothesis_set(None, [self.proposal("A")], max_hypotheses=2)
        hypothesis_id = state.hypotheses[0].hypothesis_id
        registry = {
            "e1": self.evidence("e1", "c" * 64),
            "e2": self.evidence("e2", "c" * 64),
        }
        first, changed = link_hypothesis_evidence(
            state,
            registry,
            hypothesis_id=hypothesis_id,
            evidence_id="e1",
            relation="supports",
        )
        self.assertTrue(changed)
        duplicate, changed_again = link_hypothesis_evidence(
            first,
            registry,
            hypothesis_id=hypothesis_id,
            evidence_id="e2",
            relation="supports",
        )
        self.assertFalse(changed_again)
        self.assertEqual(first.signature, duplicate.signature)
        relabelled, relabel_changed = link_hypothesis_evidence(
            first,
            registry,
            hypothesis_id=hypothesis_id,
            evidence_id="e2",
            relation="falsifies",
        )
        self.assertFalse(relabel_changed)
        self.assertEqual(first.signature, relabelled.signature)

    def test_unknown_evidence_cannot_be_linked(self) -> None:
        hypothesis = make_hypothesis(**self.proposal("A"))
        state = HypothesisSet(max_hypotheses=2, hypotheses=(hypothesis,), signature="state")
        with self.assertRaises(PolicyError):
            link_hypothesis_evidence(
                state,
                {},
                hypothesis_id=hypothesis.hypothesis_id,
                evidence_id="missing",
                relation="supports",
            )


if __name__ == "__main__":
    unittest.main()
