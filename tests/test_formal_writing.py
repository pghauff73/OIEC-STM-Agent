import unittest

from ourd.errors import PolicyError
from ourd.formal_writing import (
    ArgumentEdge,
    ArgumentNode,
    ArgumentTopology,
    profile_dimensions,
    research_backed_profile,
)


class FormalWritingTests(unittest.TestCase):
    def test_scientific_profile_contains_evidence_and_uncertainty_rules(self) -> None:
        prompt = research_backed_profile("scientific-essay")
        self.assertIn("SCIENTIFIC ESSAY PROFILE", prompt)
        self.assertIn("Compare methods and evidential quality", prompt)
        self.assertIn("correlation", prompt.lower())
        self.assertIn("reproducibility", prompt.lower())
        dimensions = profile_dimensions("scientific-essay")
        self.assertIn("scientific claim calibration", dimensions)
        self.assertIn("causal inference", dimensions)

    def test_argumentative_profile_contains_logic_topology_rules(self) -> None:
        prompt = research_backed_profile("argumentative-essay")
        self.assertIn("ARGUMENTATIVE ESSAY + LOGIC TOPOLOGY PROFILE", prompt)
        self.assertIn("positive support graph acyclic", prompt)
        self.assertIn("implicit premises", prompt)
        self.assertIn("inference_id", prompt)
        dimensions = profile_dimensions("argumentative-essay")
        self.assertIn("argument topology", dimensions)
        self.assertIn("defeaters", dimensions)

    def test_valid_argument_topology_reaches_thesis_and_answers_counterclaim(self) -> None:
        topology = ArgumentTopology(
            nodes=(
                ArgumentNode("t", "thesis", "The policy should be adopted."),
                ArgumentNode("c", "claim", "The policy reduces risk."),
                ArgumentNode("e", "evidence", "Controlled studies report lower risk.", ("doi:example",)),
                ArgumentNode("w", "warrant", "Comparable lower measured risk supports lower expected risk."),
                ArgumentNode("x", "counterclaim", "The policy is too costly."),
                ArgumentNode("xe", "evidence", "Initial capital cost is higher.", ("study:cost",)),
                ArgumentNode("r", "rebuttal", "Lifecycle savings offset the initial cost."),
            ),
            edges=(
                ArgumentEdge("e", "c", "supports", "risk-inference", "inductive"),
                ArgumentEdge("w", "c", "warrants", "risk-inference", "inductive"),
                ArgumentEdge("c", "t", "supports"),
                ArgumentEdge("xe", "x", "supports", "cost-inference", "inductive"),
                ArgumentEdge("x", "t", "attacks"),
                ArgumentEdge("r", "x", "rebuts"),
                ArgumentEdge("r", "t", "supports"),
            ),
        )
        topology.validate()
        groups = topology.linked_inference_groups()
        self.assertEqual(2, len(groups["risk-inference"]))
        self.assertEqual("inductive", groups["cost-inference"][0].inference_mode)

    def test_positive_support_cycle_is_rejected(self) -> None:
        topology = ArgumentTopology(
            nodes=(
                ArgumentNode("t", "thesis", "Thesis"),
                ArgumentNode("a", "claim", "Claim A"),
                ArgumentNode("b", "claim", "Claim B"),
            ),
            edges=(
                ArgumentEdge("a", "b", "supports"),
                ArgumentEdge("b", "a", "supports"),
                ArgumentEdge("a", "t", "supports"),
            ),
        )
        with self.assertRaises(PolicyError):
            topology.validate()

    def test_evidence_requires_source_reference(self) -> None:
        topology = ArgumentTopology(
            nodes=(
                ArgumentNode("t", "thesis", "Thesis"),
                ArgumentNode("e", "evidence", "Unsupported empirical statement"),
            ),
            edges=(ArgumentEdge("e", "t", "supports"),),
        )
        with self.assertRaises(PolicyError):
            topology.validate()

    def test_counterclaim_requires_response(self) -> None:
        topology = ArgumentTopology(
            nodes=(
                ArgumentNode("t", "thesis", "Thesis"),
                ArgumentNode("x", "counterclaim", "Opposing claim"),
            ),
            edges=(ArgumentEdge("x", "t", "attacks"),),
        )
        with self.assertRaises(PolicyError):
            topology.validate()

    def test_disconnected_argument_node_is_rejected(self) -> None:
        topology = ArgumentTopology(
            nodes=(
                ArgumentNode("t", "thesis", "Thesis"),
                ArgumentNode("c", "claim", "Unconnected claim"),
            ),
            edges=(),
        )
        with self.assertRaises(PolicyError):
            topology.validate(require_counterargument_response=False)

    def test_invalid_inference_mode_is_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            ArgumentEdge("a", "b", "supports", inference_mode="magic")


if __name__ == "__main__":
    unittest.main()
