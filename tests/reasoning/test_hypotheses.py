from __future__ import annotations

import unittest

from ourd import HypothesisUpdateRecord, SCORE_SCALE
from ourd.errors import PolicyError
from ourd.reasoning import (
    Hypothesis,
    HypothesisSet,
    build_hypothesis_set,
    update_hypothesis_state,
)


class HypothesisStateTests(unittest.TestCase):
    def test_hypothesis_count_is_bounded(self) -> None:
        with self.assertRaises(PolicyError):
            build_hypothesis_set(
                [
                    {"hypothesis_id": "a", "proposition": "A"},
                    {"hypothesis_id": "b", "proposition": "B"},
                ],
                problem_id="problem",
                max_hypotheses=1,
            )

    def test_mutually_exclusive_probabilities_normalize(self) -> None:
        state = build_hypothesis_set(
            [
                {"hypothesis_id": "b", "proposition": "B", "prior_bp": 4_000, "posterior_bp": 4_000},
                {"hypothesis_id": "a", "proposition": "A", "prior_bp": 4_000, "posterior_bp": 4_000},
            ],
            problem_id="problem",
            max_hypotheses=2,
            mutually_exclusive=True,
        )
        self.assertEqual(("a", "b"), tuple(item.hypothesis_id for item in state.hypotheses))
        self.assertEqual(SCORE_SCALE, sum(item.prior_bp for item in state.hypotheses))
        self.assertEqual(SCORE_SCALE, sum(item.posterior_bp for item in state.hypotheses))
        self.assertEqual((5_000, 5_000), tuple(item.posterior_bp for item in state.hypotheses))

    def test_independent_hypotheses_are_not_force_normalized(self) -> None:
        state = build_hypothesis_set(
            [
                {"hypothesis_id": "a", "proposition": "A", "posterior_bp": 4_000},
                {"hypothesis_id": "b", "proposition": "B", "posterior_bp": 4_000},
            ],
            problem_id="problem",
            max_hypotheses=2,
            mutually_exclusive=False,
        )
        self.assertEqual(8_000, sum(item.posterior_bp for item in state.hypotheses))

    def test_hypothesis_signature_is_order_independent(self) -> None:
        proposals = [
            {"hypothesis_id": "a", "proposition": "A", "posterior_bp": 6_000},
            {"hypothesis_id": "b", "proposition": "B", "posterior_bp": 4_000},
        ]
        forward = build_hypothesis_set(
            proposals,
            problem_id="problem",
            max_hypotheses=2,
            mutually_exclusive=True,
        )
        reverse = build_hypothesis_set(
            list(reversed(proposals)),
            problem_id="problem",
            max_hypotheses=2,
            mutually_exclusive=True,
        )
        self.assertEqual(forward.signature, reverse.signature)

    def test_fixed_point_update_preserves_previous_posterior(self) -> None:
        state = build_hypothesis_set(
            [Hypothesis("a", "A", prior_bp=5_000, posterior_bp=5_000)],
            problem_id="problem",
            max_hypotheses=1,
        )
        updated, records = update_hypothesis_state(
            state,
            likelihoods={"a": (8_000, 2_000)},
            evidence_ids=("e1",),
        )
        self.assertEqual(8_000, updated.hypotheses[0].posterior_bp)
        self.assertEqual(1, len(records))
        self.assertEqual(5_000, records[0].previous_posterior_bp)
        self.assertEqual(8_000, records[0].updated_posterior_bp)
        self.assertIn(records[0].update_id, updated.update_ids)

    def test_evidence_binding_is_monotonic(self) -> None:
        state = build_hypothesis_set(
            [Hypothesis("a", "A", prior_bp=5_000, posterior_bp=5_000)],
            problem_id="problem",
            max_hypotheses=1,
        )
        first, first_records = update_hypothesis_state(
            state,
            likelihoods={"a": (8_000, 2_000)},
            evidence_ids=("e1",),
        )
        second, second_records = update_hypothesis_state(
            first,
            likelihoods={"a": (7_000, 3_000)},
            evidence_ids=("e2",),
        )
        self.assertEqual(("e1", "e2"), second.hypotheses[0].supporting_evidence)
        self.assertEqual(
            {first_records[0].update_id, second_records[0].update_id},
            set(second.update_ids),
        )

    def test_falsified_hypothesis_requires_new_evidence_to_recover(self) -> None:
        state = build_hypothesis_set(
            [
                Hypothesis(
                    "a",
                    "A",
                    prior_bp=5_000,
                    posterior_bp=0,
                    conflicting_evidence=("e1",),
                    status="FALSIFIED",
                )
            ],
            problem_id="problem",
            max_hypotheses=1,
        )
        unchanged, records = update_hypothesis_state(
            state,
            likelihoods={"a": (10_000, 0)},
            evidence_ids=("e1",),
        )
        self.assertEqual(state.signature, unchanged.signature)
        self.assertEqual((), records)
        recovered, recovery_records = update_hypothesis_state(
            state,
            likelihoods={"a": (10_000, 0)},
            evidence_ids=("e2",),
        )
        self.assertGreater(recovered.hypotheses[0].posterior_bp, 0)
        self.assertEqual("WEAKENED", recovered.hypotheses[0].status)
        self.assertEqual(1, len(recovery_records))

    def test_conflicting_evidence_does_not_delete_support(self) -> None:
        state = build_hypothesis_set(
            [
                Hypothesis(
                    "a",
                    "A",
                    prior_bp=5_000,
                    posterior_bp=8_000,
                    supporting_evidence=("support",),
                )
            ],
            problem_id="problem",
            max_hypotheses=1,
        )
        updated, _ = update_hypothesis_state(
            state,
            likelihoods={"a": (2_000, 8_000)},
            evidence_ids=("counterexample",),
        )
        self.assertEqual(("support",), updated.hypotheses[0].supporting_evidence)
        self.assertEqual(("counterexample",), updated.hypotheses[0].conflicting_evidence)

    def test_identical_updates_have_identical_records_and_state(self) -> None:
        state = build_hypothesis_set(
            [Hypothesis("a", "A", prior_bp=5_000, posterior_bp=5_000)],
            problem_id="problem",
            max_hypotheses=1,
        )
        first_state, first_records = update_hypothesis_state(
            state,
            likelihoods={"a": (8_000, 2_000)},
            evidence_ids=("e1",),
        )
        second_state, second_records = update_hypothesis_state(
            state,
            likelihoods={"a": (8_000, 2_000)},
            evidence_ids=("e1",),
        )
        self.assertEqual(first_state.signature, second_state.signature)
        self.assertEqual(first_records[0].signature, second_records[0].signature)

    def test_models_are_public_and_immutable(self) -> None:
        self.assertTrue(HypothesisSet.__dataclass_params__.frozen)
        self.assertTrue(HypothesisUpdateRecord.__dataclass_params__.frozen)


if __name__ == "__main__":
    unittest.main()
