from __future__ import annotations

import unittest

from ourd.errors import PolicyError
from ourd.reasoning import (
    ReasoningBudget,
    ReasoningTopology,
    inference_identity,
    make_reasoning_edge,
    make_reasoning_node,
    validate_reasoning_topology,
)
from ourd.reasoning.models import stable_hash
from ourd.reasoning.topology import reasoning_topology_payload


class ReasoningTopologyV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = ReasoningBudget(
            maximum_candidates=4,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
        )

    def test_positive_reasoning_cycle_rejected(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node("a", "claim", "A"),
                make_reasoning_node("b", "claim", "B"),
            ),
            edges=(
                make_reasoning_edge("a", "b", "supports", "deductive"),
                make_reasoning_edge("b", "a", "entails", "deductive"),
            ),
        )
        with self.assertRaisesRegex(PolicyError, "contains a cycle"):
            validate_reasoning_topology(
                topology,
                budget=self.budget,
                declared_evidence_ids=(),
            )

    def test_unknown_evidence_reference_rejected(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node(
                    "evidence:e2",
                    "evidence",
                    "Unknown evidence",
                    evidence_ids=("e2",),
                ),
                make_reasoning_node("hypothesis:h1", "hypothesis", "H1"),
            ),
            edges=(
                make_reasoning_edge(
                    "evidence:e2",
                    "hypothesis:h1",
                    "supports",
                    "inductive",
                ),
            ),
        )
        with self.assertRaisesRegex(PolicyError, "undeclared evidence"):
            validate_reasoning_topology(
                topology,
                budget=self.budget,
                declared_evidence_ids=("e1",),
            )

    def test_conclusion_traces_to_grounding(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node(
                    "premise:p",
                    "premise",
                    "Validated input",
                    validated=True,
                ),
                make_reasoning_node(
                    "conclusion:p",
                    "conclusion",
                    "Grounded result",
                    material=True,
                ),
            ),
            edges=(
                make_reasoning_edge(
                    "premise:p",
                    "conclusion:p",
                    "entails",
                    "deductive",
                ),
            ),
        )
        validate_reasoning_topology(
            topology,
            budget=self.budget,
            declared_evidence_ids=(),
        )

    def test_assumption_only_conclusion_remains_hypothetical(self) -> None:
        nodes = (
            make_reasoning_node("assumption:a", "assumption", "Assume A"),
            make_reasoning_node(
                "conclusion:p",
                "conclusion",
                "A-dependent result",
                material=True,
            ),
        )
        edges = (
            make_reasoning_edge(
                "assumption:a",
                "conclusion:p",
                "requires",
                "constraint",
            ),
        )
        with self.assertRaisesRegex(PolicyError, "must remain hypothetical"):
            validate_reasoning_topology(
                ReasoningTopology(nodes=nodes, edges=edges),
                budget=self.budget,
                declared_evidence_ids=(),
            )
        validate_reasoning_topology(
            ReasoningTopology(
                nodes=(
                    nodes[0],
                    make_reasoning_node(
                        "conclusion:p",
                        "conclusion",
                        "A-dependent result",
                        hypothetical=True,
                        material=True,
                    ),
                ),
                edges=edges,
            ),
            budget=self.budget,
            declared_evidence_ids=(),
        )

    def test_counterexample_falsifies_hypothesis(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node("hypothesis:h1", "hypothesis", "H1"),
                make_reasoning_node("counterexample:c1", "counterexample", "Not H1"),
            ),
            edges=(
                make_reasoning_edge(
                    "counterexample:c1",
                    "hypothesis:h1",
                    "falsifies",
                    "defeasible",
                ),
            ),
        )
        validate_reasoning_topology(
            topology,
            budget=self.budget,
            declared_evidence_ids=(),
        )

    def test_attack_edges_do_not_create_support(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node(
                    "evidence:e1",
                    "evidence",
                    "Observed conflict",
                    evidence_ids=("e1",),
                ),
                make_reasoning_node(
                    "conclusion:p",
                    "conclusion",
                    "Unsupported result",
                    material=True,
                ),
            ),
            edges=(
                make_reasoning_edge(
                    "evidence:e1",
                    "conclusion:p",
                    "contradicts",
                    "defeasible",
                ),
            ),
        )
        with self.assertRaisesRegex(PolicyError, "lacks a grounding trace"):
            validate_reasoning_topology(
                topology,
                budget=self.budget,
                declared_evidence_ids=("e1",),
            )

    def test_unconnected_reasoning_branch_rejected(self) -> None:
        topology = ReasoningTopology(
            nodes=(
                make_reasoning_node(
                    "premise:p",
                    "premise",
                    "Validated input",
                    validated=True,
                ),
                make_reasoning_node(
                    "conclusion:p",
                    "conclusion",
                    "Grounded result",
                    material=True,
                ),
                make_reasoning_node("claim:orphan", "claim", "Disconnected claim"),
            ),
            edges=(
                make_reasoning_edge(
                    "premise:p",
                    "conclusion:p",
                    "entails",
                    "deductive",
                ),
            ),
        )
        with self.assertRaisesRegex(PolicyError, "unconnected branch"):
            validate_reasoning_topology(
                topology,
                budget=self.budget,
                declared_evidence_ids=(),
            )

    def test_topology_signature_is_order_independent(self) -> None:
        nodes = (
            make_reasoning_node("premise:p", "premise", "P", validated=True),
            make_reasoning_node(
                "conclusion:p",
                "conclusion",
                "C",
                material=True,
            ),
        )
        edges = (
            make_reasoning_edge(
                "premise:p",
                "conclusion:p",
                "entails",
                "deductive",
            ),
        )
        first = ReasoningTopology(problem_id="p", nodes=nodes, edges=edges)
        second = ReasoningTopology(
            problem_id="p",
            nodes=tuple(reversed(nodes)),
            edges=tuple(reversed(edges)),
        )
        self.assertEqual(
            stable_hash(reasoning_topology_payload(first)),
            stable_hash(reasoning_topology_payload(second)),
        )

    def test_inference_ids_are_content_addressed(self) -> None:
        edge = make_reasoning_edge("a", "b", "supports", "inductive")
        self.assertEqual(
            inference_identity("a", "b", "supports", "inductive"),
            edge.inference_id,
        )
        forged = ReasoningTopology(
            nodes=(
                make_reasoning_node("a", "claim", "A"),
                make_reasoning_node("b", "hypothesis", "B"),
            ),
            edges=(
                edge.__class__(
                    edge_id=edge.edge_id,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    relation=edge.relation,
                    inference_id="inference:forged",
                    inference_mode=edge.inference_mode,
                    signature=edge.signature,
                ),
            ),
        )
        with self.assertRaisesRegex(PolicyError, "identity mismatch"):
            validate_reasoning_topology(
                forged,
                budget=self.budget,
                declared_evidence_ids=(),
            )


if __name__ == "__main__":
    unittest.main()
