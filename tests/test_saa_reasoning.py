from __future__ import annotations

import unittest

from ourd.egcf.reasoning import (
    ReasoningAlgorithmSpec,
    ReasoningEdgeSpec,
    ReasoningNodeSpec,
    ReasoningStateDependency,
    ReasoningStateDimension,
    ReasoningStateModel,
    ReasoningTerminationSpec,
    assess_reasoning_state_semantics,
    canonicalize_reasoning_algorithm,
    compare_reasoning_algorithms,
    propagate_reasoning_semantic_issues,
)


def base_spec(*, renamed=False, output_meaning="qualified conclusion", description="first"):
    ids = ("observe", "test", "verify") if not renamed else ("n3", "n1", "n2")
    nodes = (
        ReasoningNodeSpec(
            node_id=ids[0],
            operator="OBSERVE",
            semantic_inputs=("problem evidence",),
            semantic_outputs=("candidate evidence",),
            evidence_requirements=("source snapshot",),
            description=description,
        ),
        ReasoningNodeSpec(
            node_id=ids[1],
            operator="FALSIFY",
            semantic_inputs=("candidate evidence",),
            semantic_outputs=("surviving claim",),
            falsifiers=("counterexample exists",),
        ),
        ReasoningNodeSpec(
            node_id=ids[2],
            operator="VERIFY",
            semantic_inputs=("surviving claim",),
            semantic_outputs=(output_meaning,),
            evidence_requirements=("independent verification",),
        ),
    )
    if renamed:
        nodes = tuple(reversed(nodes))
    return ReasoningAlgorithmSpec(
        name="falsification-first",
        inputs=("problem evidence",),
        outputs=(output_meaning,),
        nodes=nodes,
        edges=(
            ReasoningEdgeSpec(ids[0], ids[1], "NEXT"),
            ReasoningEdgeSpec(ids[1], ids[2], "NEXT"),
        ),
        invariants=("unverified claims do not become facts without evidence",),
        termination=ReasoningTerminationSpec(
            kind="bounded evidence decision",
            predicate="claim verified or falsified or budget exhausted",
            max_steps=8,
        ),
        applicability=("evidence-backed factual reasoning",),
    )


class SAA8CanonicalReasoningTests(unittest.TestCase):
    def test_node_renaming_reordering_and_description_do_not_change_exact_identity(self) -> None:
        left = canonicalize_reasoning_algorithm(base_spec(description="visible description one"))
        right = canonicalize_reasoning_algorithm(
            base_spec(renamed=True, description="completely different display prose")
        )
        self.assertEqual("EXACT_BOUNDED_GRAPH_CANONICALIZATION", left.canonicalization_strength)
        self.assertEqual(left.canonical_reasoning_signature, right.canonical_reasoning_signature)
        self.assertEqual(left.topology_signature, right.topology_signature)
        self.assertTrue(left.public_artifact_only)

    def test_reasoning_semantics_are_identity_bearing(self) -> None:
        left = canonicalize_reasoning_algorithm(base_spec(output_meaning="qualified conclusion"))
        right = canonicalize_reasoning_algorithm(base_spec(output_meaning="marketing recommendation"))
        self.assertEqual(left.topology_signature, right.topology_signature)
        self.assertNotEqual(left.semantic_signature, right.semantic_signature)
        self.assertNotEqual(left.canonical_reasoning_signature, right.canonical_reasoning_signature)

    def test_large_symmetric_reasoning_graph_downgrades_conservatively(self) -> None:
        nodes = tuple(
            ReasoningNodeSpec(node_id=f"n{index}", operator="OBSERVE")
            for index in range(8)
        )
        spec = ReasoningAlgorithmSpec(
            name="symmetric",
            inputs=("evidence",),
            outputs=("observations",),
            nodes=nodes,
            edges=(),
            invariants=(),
            termination=ReasoningTerminationSpec("bounded", "all observations collected", 8),
        )
        canonical = canonicalize_reasoning_algorithm(spec)
        self.assertEqual("CONSERVATIVE_RENAMING_BOUND", canonical.canonicalization_strength)
        self.assertTrue(canonical.warnings)


class SAA81ReasoningEquivalenceTests(unittest.TestCase):
    def test_exact_reasoning_equivalence_is_reusable(self) -> None:
        left = canonicalize_reasoning_algorithm(base_spec())
        right = canonicalize_reasoning_algorithm(base_spec(renamed=True))
        assessment = compare_reasoning_algorithms(left, right)
        self.assertEqual("EXACT_REASONING_ALGORITHM_EQUIVALENCE", assessment.status)
        self.assertTrue(assessment.exact_equivalence)
        self.assertTrue(assessment.canonical_reuse_eligible)
        self.assertIn("EQUIVALENT_TO", assessment.relation_candidates)

    def test_same_operator_topology_with_different_meaning_is_near_variant_not_equivalent(self) -> None:
        left = canonicalize_reasoning_algorithm(base_spec(output_meaning="qualified conclusion"))
        right = canonicalize_reasoning_algorithm(base_spec(output_meaning="marketing recommendation"))
        assessment = compare_reasoning_algorithms(left, right)
        self.assertEqual("OPERATOR_TOPOLOGY_MATCH_SEMANTIC_DIFFERENCE", assessment.status)
        self.assertFalse(assessment.canonical_reuse_eligible)
        self.assertIn("NEAR_VARIANT_OF", assessment.relation_candidates)

    def test_topology_change_survives_canonicalization(self) -> None:
        ordinary = canonicalize_reasoning_algorithm(base_spec())
        spec = base_spec()
        changed = ReasoningAlgorithmSpec(
            name=spec.name,
            inputs=spec.inputs,
            outputs=spec.outputs,
            nodes=spec.nodes,
            edges=(
                ReasoningEdgeSpec("observe", "verify", "NEXT"),
                ReasoningEdgeSpec("verify", "test", "NEXT"),
            ),
            invariants=spec.invariants,
            termination=spec.termination,
            applicability=spec.applicability,
        )
        alternative = canonicalize_reasoning_algorithm(changed)
        self.assertNotEqual(ordinary.topology_signature, alternative.topology_signature)


class SAA82ReasoningSemanticTests(unittest.TestCase):
    def test_atomic_confidence_that_mixes_distinct_meanings_is_blocked(self) -> None:
        state = ReasoningStateModel(
            dimensions=(
                ReasoningStateDimension("evidence", "evidence", "evidence strength"),
                ReasoningStateDimension("consistency", "consistency", "cross-source consistency"),
                ReasoningStateDimension("confidence", "confidence", "confidence", declared_independent=True),
            ),
            dependencies=(
                ReasoningStateDependency("evidence", "confidence"),
                ReasoningStateDependency("consistency", "confidence"),
            ),
        )
        assessment = assess_reasoning_state_semantics(state)
        kinds = {item.issue_kind for item in assessment.issues}
        self.assertIn("ATOMIC_DIMENSION_COUPLES_MULTIPLE_MEANINGS", kinds)
        self.assertIn("DECLARED_INDEPENDENCE_CONTRADICTED_BY_DEPENDENCY", kinds)
        self.assertFalse(assessment.canonical_reasoning_state_eligible)

    def test_evidence_grounded_resolved_composite_can_be_admitted(self) -> None:
        state = ReasoningStateModel(
            dimensions=(
                ReasoningStateDimension("evidence", "evidence", "evidence strength"),
                ReasoningStateDimension("consistency", "consistency", "cross-source consistency"),
                ReasoningStateDimension(
                    "support_quality",
                    "support quality",
                    "joint evidence support quality",
                    representation_kind="COMPOSITE",
                    epistemic_status="SEMANTICALLY_RESOLVED",
                    evidence_ids=("evidence:semantic-resolution",),
                    declared_independent=False,
                ),
            ),
            dependencies=(
                ReasoningStateDependency("evidence", "support_quality"),
                ReasoningStateDependency("consistency", "support_quality"),
            ),
        )
        assessment = assess_reasoning_state_semantics(state)
        self.assertEqual("REASONING_STATE_SEMANTICALLY_COHERENT", assessment.status)
        self.assertTrue(assessment.canonical_reasoning_state_eligible)

    def test_same_label_with_different_meaning_is_semantic_collision(self) -> None:
        state = ReasoningStateModel(
            dimensions=(
                ReasoningStateDimension("risk_a", "risk", "probability of failure"),
                ReasoningStateDimension("risk_b", "risk", "financial exposure"),
            ),
            dependencies=(),
        )
        assessment = assess_reasoning_state_semantics(state)
        self.assertIn("SEMANTIC_LABEL_COLLISION", {item.issue_kind for item in assessment.issues})
        self.assertFalse(assessment.canonical_reasoning_state_eligible)

    def test_verified_fact_without_evidence_is_not_grounded(self) -> None:
        state = ReasoningStateModel(
            dimensions=(
                ReasoningStateDimension(
                    "fact",
                    "fact",
                    "supplier is approved",
                    epistemic_status="VERIFIED_FACT",
                ),
            ),
            dependencies=(),
        )
        assessment = assess_reasoning_state_semantics(state)
        self.assertIn("UNGROUNDED_REASONING_STATE", {item.issue_kind for item in assessment.issues})
        self.assertFalse(assessment.canonical_reasoning_state_eligible)

    def test_reasoning_semantic_issues_propagate_across_governance(self) -> None:
        state = ReasoningStateModel(
            dimensions=(
                ReasoningStateDimension("a", "a", "evidence strength"),
                ReasoningStateDimension("b", "b", "consistency"),
                ReasoningStateDimension("x", "confidence", "confidence"),
            ),
            dependencies=(
                ReasoningStateDependency("a", "x"),
                ReasoningStateDependency("b", "x"),
            ),
        )
        assessment = assess_reasoning_state_semantics(state)
        directives = propagate_reasoning_semantic_issues(assessment.issues)
        self.assertEqual(7 * len(assessment.issues), len(directives))
        blocking_store = [
            item for item in directives
            if item.subsystem == "ALGORITHM_STORE" and item.blocking
        ]
        blocking_iurm = [
            item for item in directives
            if item.subsystem == "IURM" and item.blocking
        ]
        self.assertTrue(blocking_store)
        self.assertTrue(blocking_iurm)


if __name__ == "__main__":
    unittest.main()
