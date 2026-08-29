from __future__ import annotations

import unittest

from ourd.egcf.adaptation import build_controlled_adaptation_plan, create_adapted_candidate
from ourd.egcf.algebra.reasoning_fit import ReasoningFitAssessment, ReasoningRetrievalResult
from ourd.egcf.ids import sha256_json
from ourd.egcf.retrieval import (
    AlgorithmDomainContract,
    MathematicalFitAssessment,
    UnifiedProblemRequirements,
    UnifiedRetrievalDecision,
    assess_algorithm_transfer,
    explain_algorithm_transfer,
    explain_unified_retrieval,
)
from ourd.egcf.semantics import LENGTH, TIME, make_semantic_concept
from ourd.egcf.errors import EGCFError


def concept(name: str, meaning: str, quantity: str = "speed"):
    return make_semantic_concept(
        name=name,
        meaning=meaning,
        domain="transport",
        quantity_kind=quantity,
        physical_dimension=LENGTH / TIME,
        canonical_unit=None,
        evidence_ids=(f"evidence:{name}",),
    )


def contract(domain: str, c, *, dynamics="1", boundary="2", invariants=("bounded",), evidence=("source snapshot",)):
    return AlgorithmDomainContract(
        domain=domain,
        input_concepts=(c,),
        invariants=tuple(invariants),
        boundary_signatures=(boundary * 64,),
        dynamics_signature=dynamics * 64,
        evidence_requirements=tuple(evidence),
    )


class SAA102TransferTests(unittest.TestCase):
    def test_exact_contract_transfer_can_reuse_without_requalification(self):
        speed = concept("speed", "translational speed")
        assessment = assess_algorithm_transfer(
            "canonical-algorithm:fixture",
            contract("road", speed),
            contract("rail", speed),
        )
        self.assertEqual("EXACT_TRANSFER_CONTRACT_MATCH", assessment.status)
        self.assertTrue(assessment.transfer_without_requalification)
        self.assertFalse(assessment.adaptation_required)

    def test_same_meaning_but_changed_dynamics_requires_requalification(self):
        speed = concept("speed", "translational speed")
        assessment = assess_algorithm_transfer(
            "canonical-algorithm:fixture",
            contract("road", speed, dynamics="1"),
            contract("air", speed, dynamics="3"),
        )
        self.assertEqual("TRANSFER_REQUIRES_DOMAIN_REQUALIFICATION", assessment.status)
        self.assertIn("DYNAMICS_CONTRACT", assessment.adaptation_gaps)
        self.assertFalse(assessment.transfer_without_requalification)

    def test_semantic_mismatch_blocks_transfer_even_when_dimensions_match(self):
        speed = concept("speed", "translational speed", "speed")
        flow = concept("flow", "volumetric transport proxy", "flow proxy")
        assessment = assess_algorithm_transfer(
            "canonical-algorithm:fixture",
            contract("road", speed),
            contract("process", flow),
        )
        self.assertEqual("TRANSFER_BLOCKED_SEMANTIC_MISMATCH", assessment.status)
        self.assertTrue(assessment.blocking_gaps)


def unified_decision(*, math_selected=False, reasoning_selected=False, math_gap="", reasoning_gap=""):
    c = concept("speed", "translational speed")
    requirements = UnifiedProblemRequirements(
        problem_id="transfer-explain",
        input_concepts=(c,),
        desired_mathematical_output_count=1,
        mathematical_domain="continuous",
        reasoning_desired_outputs=("qualified conclusion",),
        require_mathematical_algorithm=True,
        require_reasoning_algorithm=True,
    ).canonical()
    math = MathematicalFitAssessment(
        canonical_algorithm_id="math:one",
        status="GOOD_MATHEMATICAL_FIT" if math_selected else "INELIGIBLE_MATHEMATICAL_FIT",
        fit_score_bp=10000 if math_selected else 6000,
        semantic_input_fit_bp=10000,
        output_shape_fit_bp=10000,
        domain_fit_bp=10000 if not math_gap else 0,
        matched_input_meanings=("translational speed",),
        unmatched_input_meanings=(),
        blocking_gaps=(() if not math_gap else (math_gap,)),
        fit_signature=sha256_json({"math": math_selected, "gap": math_gap}),
    )
    reason = ReasoningFitAssessment(
        reasoning_id="reason:one",
        canonical_reasoning_signature="a" * 64,
        status="GOOD_REASONING_FIT" if reasoning_selected else "INELIGIBLE_REASONING_FIT",
        fit_score_bp=10000 if reasoning_selected else 5000,
        input_fit_bp=10000,
        output_fit_bp=10000,
        applicability_fit_bp=10000,
        invariant_fit_bp=10000,
        evidence_fit_bp=10000 if not reasoning_gap else 0,
        termination_fit_bp=10000,
        blocking_gaps=(() if not reasoning_gap else (reasoning_gap,)),
        adaptation_gaps=(),
        fit_signature=sha256_json({"reason": reasoning_selected, "gap": reasoning_gap}),
    )
    rr = ReasoningRetrievalResult(
        schema_version=1,
        fit_version="fixture",
        requirements_signature="b" * 64,
        candidates=(reason,),
        selected_reasoning_id="reason:one" if reasoning_selected else None,
        selected_fit_score_bp=10000 if reasoning_selected else 0,
        search_scope="fixture",
        result_signature="c" * 64,
    )
    missing = tuple(
        name for name, yes in (
            ("MATHEMATICAL_ALGORITHM", math_selected),
            ("REASONING_ALGORITHM", reasoning_selected),
        ) if not yes
    )
    decision = UnifiedRetrievalDecision(
        schema_version=1,
        retrieval_version="fixture",
        problem_signature="d" * 64,
        mathematical_candidates=(math,),
        selected_mathematical_algorithm_id="math:one" if math_selected else None,
        reasoning_result=rr,
        selected_reasoning_id="reason:one" if reasoning_selected else None,
        required_components_satisfied=not missing,
        missing_components=missing,
        status="fixture",
        decision_signature="e" * 64,
    )
    return requirements, decision


class SAA103ExplanationTests(unittest.TestCase):
    def test_explanation_identifies_exact_fit_gap_dimensions(self):
        requirements, decision = unified_decision(
            math_selected=False,
            reasoning_selected=False,
            math_gap="mathematical domain discrete != required continuous",
            reasoning_gap="evidence capability unavailable: independent verification",
        )
        explanation = explain_unified_retrieval(decision, requirements)
        self.assertEqual("EXPLAINED_CONFIRMED_RETRIEVAL_GAP", explanation.status)
        self.assertIn("MATHEMATICAL_DOMAIN", explanation.fit_gap_dimensions)
        self.assertIn("REASONING_EVIDENCE_CAPABILITY", explanation.fit_gap_dimensions)
        self.assertIn("MISSING_MATHEMATICAL_ALGORITHM", explanation.fit_gap_dimensions)
        self.assertIn("MISSING_REASONING_ALGORITHM", explanation.fit_gap_dimensions)

    def test_complete_solution_explains_selection_without_adaptation_gap(self):
        requirements, decision = unified_decision(math_selected=True, reasoning_selected=True)
        explanation = explain_unified_retrieval(decision, requirements)
        self.assertEqual("EXPLAINED_COMPLETE_KNOWN_SOLUTION", explanation.status)
        self.assertTrue(explanation.selected_reasons)
        self.assertFalse(explanation.fit_gap_dimensions)

    def test_transfer_explanation_isolates_changed_dynamics(self):
        speed = concept("speed", "translational speed")
        assessment = assess_algorithm_transfer(
            "canonical-algorithm:fixture",
            contract("road", speed, dynamics="1"),
            contract("air", speed, dynamics="3"),
        )
        explanation = explain_algorithm_transfer(assessment)
        self.assertEqual("EXPLAINED_TRANSFER_REQUALIFICATION_DELTA", explanation.status)
        self.assertEqual(("DYNAMICS_CONTRACT",), explanation.fit_gap_dimensions)


class SAA11AdaptationTests(unittest.TestCase):
    def test_fit_delta_becomes_one_dimension_at_a_time_plan(self):
        requirements, decision = unified_decision(
            math_selected=False,
            reasoning_selected=False,
            math_gap="mathematical domain discrete != required continuous",
            reasoning_gap="evidence capability unavailable: independent verification",
        )
        explanation = explain_unified_retrieval(decision, requirements)
        plan = build_controlled_adaptation_plan(explanation)
        self.assertTrue(plan.one_dimension_per_step)
        self.assertTrue(plan.qualification_required)
        self.assertFalse(plan.canonical_reuse_eligible)
        self.assertEqual(len(plan.steps), len(explanation.counterfactual_changes))
        self.assertTrue(all(step.dimension for step in plan.steps))

    def test_transfer_delta_flows_directly_into_adaptation_plan(self):
        speed = concept("speed", "translational speed")
        assessment = assess_algorithm_transfer(
            "canonical-algorithm:fixture",
            contract("road", speed, dynamics="1"),
            contract("air", speed, dynamics="3"),
        )
        explanation = explain_algorithm_transfer(assessment)
        plan = build_controlled_adaptation_plan(
            explanation,
            selected_mathematical_algorithm_id="canonical-algorithm:fixture",
        )
        self.assertEqual(1, len(plan.steps))
        self.assertEqual("DYNAMICS_CONTRACT", plan.steps[0].dimension)
        self.assertEqual("canonical-algorithm:fixture", plan.steps[0].base_algorithm_id)

    def test_adapted_candidate_is_new_unqualified_identity(self):
        requirements, decision = unified_decision(
            math_selected=False,
            reasoning_selected=True,
            math_gap="mathematical domain discrete != required continuous",
        )
        explanation = explain_unified_retrieval(decision, requirements)
        plan = build_controlled_adaptation_plan(explanation)
        step = next(item for item in plan.steps if item.dimension == "MATHEMATICAL_DOMAIN")
        candidate = create_adapted_candidate(
            step,
            change_material={"dimension": "MATHEMATICAL_DOMAIN", "target_domain": "continuous"},
        )
        self.assertEqual("UNQUALIFIED_ADAPTED_ALGORITHM_CANDIDATE", candidate.epistemic_status)
        self.assertTrue(candidate.qualification_required)
        self.assertFalse(candidate.canonical_reuse_eligible)

    def test_multi_dimension_change_is_rejected(self):
        requirements, decision = unified_decision(
            math_selected=False,
            reasoning_selected=True,
            math_gap="mathematical domain discrete != required continuous",
        )
        explanation = explain_unified_retrieval(decision, requirements)
        plan = build_controlled_adaptation_plan(explanation)
        step = next(item for item in plan.steps if item.dimension == "MATHEMATICAL_DOMAIN")
        with self.assertRaises(EGCFError):
            create_adapted_candidate(
                step,
                change_material={
                    "dimension": "MATHEMATICAL_DOMAIN",
                    "target_domain": "continuous",
                    "also_changes": ["MATHEMATICAL_OUTPUT_SHAPE"],
                },
            )


if __name__ == "__main__":
    unittest.main()
