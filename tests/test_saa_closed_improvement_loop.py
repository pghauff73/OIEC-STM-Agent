from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from ourd.egcf.adaptation import (
    AdaptationLineageStore,
    ExperimentMetricSpec,
    ImprovementLoopStore,
    aggregate_repeated_experiments,
    assess_multistep_evolution,
    build_controlled_adaptation_plan,
    create_adapted_candidate,
    make_ab_experiment_design,
    make_adaptation_promotion,
    make_multistep_evolution_plan,
    make_variant_observation,
    qualify_ab_experiment,
    qualify_evolution_step,
)
from ourd.egcf.algebra.retrieval_explanation import CounterfactualFitChange, RetrievalExplanation
from ourd.egcf.errors import EGCFError
from ourd.egcf.ids import sha256_json
from ourd.egcf.intelligence import evaluate_intelligence_improvement_loop
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.store import EGCFStore
from ourd.retrieve_first import RETRIEVE_FIRST_VERSION, RetrieveFirstReceipt


BASE_REF = "canonical-algorithm:sha256:" + "1" * 64
PROMOTED_REF = "canonical-algorithm:sha256:" + "9" * 64
DECISION_SIG = "2" * 64
CONTEXT_SIG = "3" * 64


def evidence(requirements, group: str, *, label: str) -> EvidenceArtifact:
    material = {"requirements": list(requirements), "group": group, "label": label}
    return EvidenceArtifact(
        subject_id=f"closed-loop:{label}",
        claim_ids=[],
        requirement_ids=list(requirements),
        category="benchmark",
        producer="deterministic-closed-loop-test",
        method="bounded-qualification",
        source_snapshot_hash=sha256_json(material),
        target=label,
        oracle="exact-fixture-oracle",
        environment={"suite": "saa-11.3-12"},
        command_id="experiment.compare@1",
        algorithm_id="closed-loop-fixture",
        created_at="2026-08-30T00:00:00Z",
        sha256=sha256_json(material),
        success=True,
        limitations=[],
        independence_group=group,
        simulated=False,
    )


def retrieval_explanation() -> RetrievalExplanation:
    changes = (
        CounterfactualFitChange(
            component="MATHEMATICAL_ALGORITHM",
            dimension="DYNAMICS_CONTRACT",
            current="source dynamics",
            required_change="match target dynamics",
            would_remove_blocker=True,
        ),
        CounterfactualFitChange(
            component="MATHEMATICAL_ALGORITHM",
            dimension="BOUNDARY_CONTRACT",
            current="source bounds",
            required_change="match target bounds",
            would_remove_blocker=True,
        ),
    )
    payload = {
        "decision_signature": DECISION_SIG,
        "changes": [item.to_dict() for item in changes],
    }
    return RetrievalExplanation(
        schema_version=1,
        explanation_version="fixture",
        decision_signature=DECISION_SIG,
        status="EXPLAINED_PARTIAL_FIT_WITH_DELTA",
        selected_reasons=("existing canonical algorithm is the best known partial fit",),
        rejected_reasons=("dynamics and bounds differ",),
        counterfactual_changes=changes,
        fit_gap_dimensions=("BOUNDARY_CONTRACT", "DYNAMICS_CONTRACT"),
        explanation_signature=sha256_json(payload),
    )


def initial_receipt(explanation: RetrievalExplanation) -> RetrieveFirstReceipt:
    payload = {"status": "ADAPT_OR_FILL_CONFIRMED_GAP", "explanation": explanation.explanation_signature}
    return RetrieveFirstReceipt(
        schema_version=1,
        policy_version=RETRIEVE_FIRST_VERSION,
        status="ADAPT_OR_FILL_CONFIRMED_GAP",
        retrieval_attempted=True,
        required_search_completed=True,
        new_algorithm_generation_allowed=True,
        adaptation_allowed=True,
        generation_scope=("MATHEMATICAL_ALGORITHM",),
        selected_mathematical_algorithm_id=BASE_REF,
        selected_reasoning_id=None,
        retrieval_decision_signature=DECISION_SIG,
        explanation_signature=explanation.explanation_signature,
        fit_gap_dimensions=explanation.fit_gap_dimensions,
        guidance=("adapt only the verified fit delta",),
        receipt_signature=sha256_json(payload),
    )


def post_promotion_receipt() -> RetrieveFirstReceipt:
    decision = "4" * 64
    explanation = "5" * 64
    payload = {"status": "REUSE_QUALIFIED_KNOWN_SOLUTION", "selected": PROMOTED_REF}
    return RetrieveFirstReceipt(
        schema_version=1,
        policy_version=RETRIEVE_FIRST_VERSION,
        status="REUSE_QUALIFIED_KNOWN_SOLUTION",
        retrieval_attempted=True,
        required_search_completed=True,
        new_algorithm_generation_allowed=False,
        adaptation_allowed=False,
        generation_scope=(),
        selected_mathematical_algorithm_id=PROMOTED_REF,
        selected_reasoning_id=None,
        retrieval_decision_signature=decision,
        explanation_signature=explanation,
        fit_gap_dimensions=(),
        guidance=("reuse promoted knowledge",),
        receipt_signature=sha256_json(payload),
    )


def setup_two_step_lineage(egcf: EGCFStore, lineage: AdaptationLineageStore):
    explanation = retrieval_explanation()
    plan = build_controlled_adaptation_plan(
        explanation,
        selected_mathematical_algorithm_id=BASE_REF,
    )
    step1, step2 = plan.steps
    candidate1 = create_adapted_candidate(
        step1,
        change_material={"dimension": step1.dimension, "target": "dynamics-v2"},
    )
    ref1, _ = lineage.register_candidate(
        candidate1,
        step1,
        source_explanation_signature=explanation.explanation_signature,
    )
    candidate2 = create_adapted_candidate(
        step2,
        change_material={"dimension": step2.dimension, "target": "bounds-v2"},
        parent_candidate_signature=candidate1.candidate_signature,
    )
    ref2, _ = lineage.register_candidate(
        candidate2,
        step2,
        source_explanation_signature=explanation.explanation_signature,
    )
    return explanation, plan, ref1, ref2


class SAA113MultiStepEvolutionTests(unittest.TestCase):
    def test_every_intermediate_step_must_preserve_frozen_invariants(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                lineage = AdaptationLineageStore(egcf)
                _, _, _, final_ref = setup_two_step_lineage(egcf, lineage)
                evolution = make_multistep_evolution_plan(
                    lineage,
                    final_ref,
                    frozen_invariants=("bounded",),
                    allowed_dimensions=("DYNAMICS_CONTRACT", "BOUNDARY_CONTRACT"),
                )
                first_evidence = egcf.register(evidence(("invariant",), "evolution-1", label="step-1"))
                second_evidence = egcf.register(evidence(("invariant",), "evolution-2", label="step-2"))
                q1 = qualify_evolution_step(
                    egcf,
                    evolution,
                    evolution.steps[0].candidate_ref,
                    invariant_results={"bounded": True},
                    evidence_ids=(first_evidence,),
                    independent_review=True,
                )
                q2 = qualify_evolution_step(
                    egcf,
                    evolution,
                    evolution.steps[1].candidate_ref,
                    invariant_results={"bounded": True},
                    evidence_ids=(second_evidence,),
                    independent_review=True,
                )
                assessment = assess_multistep_evolution(evolution, (q1, q2))
                self.assertEqual("MULTISTEP_EVOLUTION_QUALIFIED", assessment.status)
                self.assertTrue(assessment.evolution_qualified)
                self.assertEqual(2, assessment.qualified_step_count)

                bad = qualify_evolution_step(
                    egcf,
                    evolution,
                    evolution.steps[1].candidate_ref,
                    invariant_results={"bounded": False},
                    evidence_ids=(second_evidence,),
                    independent_review=True,
                )
                blocked = assess_multistep_evolution(evolution, (q1, bad))
                self.assertFalse(blocked.evolution_qualified)
                self.assertIn("EVOLUTION_STEP_INVARIANT_VIOLATION", blocked.blocking_steps[0])

    def test_improvement_ledger_rebuilds_qualified_evolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                lineage = AdaptationLineageStore(egcf)
                _, _, _, final_ref = setup_two_step_lineage(egcf, lineage)
                ledger = ImprovementLoopStore(egcf, lineage)
                evolution = make_multistep_evolution_plan(
                    lineage,
                    final_ref,
                    frozen_invariants=("bounded",),
                )
                ledger.register_evolution_plan(evolution)
                qualifications = []
                for index, step in enumerate(evolution.steps):
                    eid = egcf.register(evidence(("invariant",), f"rebuild-{index}", label=f"evo-{index}"))
                    q = qualify_evolution_step(
                        egcf,
                        evolution,
                        step.candidate_ref,
                        invariant_results={"bounded": True},
                        evidence_ids=(eid,),
                        independent_review=True,
                    )
                    ledger.register_step_qualification(q)
                    qualifications.append(q)
                assessment = assess_multistep_evolution(evolution, qualifications)
                ledger.register_evolution_assessment(assessment)
                ledger.rebuild_projection()
                self.assertTrue(assessment.evolution_qualified)


class SAA114RepeatedEvidenceTests(unittest.TestCase):
    def _two_results(self, egcf, lineage, candidate_ref, *, groups=("run-a", "run-b")):
        design = make_ab_experiment_design(
            baseline_ref=BASE_REF,
            candidate_ref=candidate_ref,
            context_signature=CONTEXT_SIG,
            metrics=(ExperimentMetricSpec("error", "LOWER_IS_BETTER", Fraction(1, 100)),),
            required_invariants=("bounded",),
            evidence_requirements=("benchmark",),
            minimum_trials=10,
        )
        lineage.register_experiment_design(design)
        results = []
        for index, group in enumerate(groups):
            a_id = egcf.register(evidence(("benchmark",), f"{group}-baseline", label=f"baseline-{index}"))
            b_id = egcf.register(evidence(("benchmark",), f"{group}-candidate", label=f"candidate-{index}"))
            baseline = make_variant_observation(
                design,
                variant_ref=BASE_REF,
                metric_values={"error": Fraction(10, 100)},
                evidence_ids=(a_id,),
                invariant_results={"bounded": True},
                trial_count=20,
                execution_success=True,
            )
            candidate = make_variant_observation(
                design,
                variant_ref=candidate_ref,
                metric_values={"error": Fraction(5 - index, 100)},
                evidence_ids=(b_id,),
                invariant_results={"bounded": True},
                trial_count=20,
                execution_success=True,
            )
            result = qualify_ab_experiment(egcf, design, baseline, candidate, independent_review=True)
            lineage.register_experiment_result(result)
            results.append(result)
        return design, tuple(results)

    def test_independent_repetitions_qualify_sustained_improvement(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                lineage = AdaptationLineageStore(egcf)
                _, _, _, final_ref = setup_two_step_lineage(egcf, lineage)
                design, results = self._two_results(egcf, lineage, final_ref)
                aggregate = aggregate_repeated_experiments(results)
                self.assertEqual("SUSTAINED_CANDIDATE_IMPROVEMENT_QUALIFIED", aggregate.status)
                self.assertTrue(aggregate.sustained_improvement_qualified)
                ledger = ImprovementLoopStore(egcf, lineage)
                ledger.register_experiment_aggregate(aggregate)
                ledger.rebuild_projection()
                self.assertEqual(1, len(ledger.aggregates()))
                self.assertEqual(design.design_signature, ledger.aggregates()[0]["payload"]["design_signature"])

    def test_duplicate_result_cannot_manufacture_repeated_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                lineage = AdaptationLineageStore(egcf)
                _, _, _, final_ref = setup_two_step_lineage(egcf, lineage)
                _, results = self._two_results(egcf, lineage, final_ref)
                with self.assertRaises(EGCFError):
                    aggregate_repeated_experiments((results[0], results[0]))


class SAA12ClosedLoopTests(unittest.TestCase):
    def test_closed_loop_requires_retrieval_to_select_promoted_knowledge(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                lineage = AdaptationLineageStore(egcf)
                explanation, adaptation_plan, _, final_ref = setup_two_step_lineage(egcf, lineage)
                ledger = ImprovementLoopStore(egcf, lineage)
                evolution = make_multistep_evolution_plan(lineage, final_ref, frozen_invariants=("bounded",))
                ledger.register_evolution_plan(evolution)
                qualifications = []
                for index, step in enumerate(evolution.steps):
                    eid = egcf.register(evidence(("invariant",), f"loop-evo-{index}", label=f"loop-evo-{index}"))
                    q = qualify_evolution_step(
                        egcf,
                        evolution,
                        step.candidate_ref,
                        invariant_results={"bounded": True},
                        evidence_ids=(eid,),
                        independent_review=True,
                    )
                    ledger.register_step_qualification(q)
                    qualifications.append(q)
                evolution_assessment = assess_multistep_evolution(evolution, qualifications)
                ledger.register_evolution_assessment(evolution_assessment)

                design = make_ab_experiment_design(
                    baseline_ref=BASE_REF,
                    candidate_ref=final_ref,
                    context_signature=CONTEXT_SIG,
                    metrics=(ExperimentMetricSpec("error", "LOWER_IS_BETTER", Fraction(1, 100)),),
                    required_invariants=("bounded",),
                    evidence_requirements=("benchmark",),
                    minimum_trials=10,
                )
                lineage.register_experiment_design(design)
                results = []
                for index in range(2):
                    a_id = egcf.register(evidence(("benchmark",), f"loop-a-{index}", label=f"loop-a-{index}"))
                    b_id = egcf.register(evidence(("benchmark",), f"loop-b-{index}", label=f"loop-b-{index}"))
                    baseline = make_variant_observation(
                        design,
                        variant_ref=BASE_REF,
                        metric_values={"error": Fraction(10, 100)},
                        evidence_ids=(a_id,),
                        invariant_results={"bounded": True},
                        trial_count=20,
                        execution_success=True,
                    )
                    candidate = make_variant_observation(
                        design,
                        variant_ref=final_ref,
                        metric_values={"error": Fraction(5 - index, 100)},
                        evidence_ids=(b_id,),
                        invariant_results={"bounded": True},
                        trial_count=20,
                        execution_success=True,
                    )
                    result = qualify_ab_experiment(egcf, design, baseline, candidate, independent_review=True)
                    lineage.register_experiment_result(result)
                    results.append(result)
                aggregate = aggregate_repeated_experiments(results)
                ledger.register_experiment_aggregate(aggregate)

                promotion_evidence = egcf.register(evidence(("qualification",), "promotion", label="promotion"))
                promotion = make_adaptation_promotion(
                    candidate_ref=final_ref,
                    canonical_algorithm_ref=PROMOTED_REF,
                    qualification_signature="6" * 64,
                    evidence_ids=(promotion_evidence,),
                )
                promotion_ref = lineage.register_promotion(promotion)

                receipt = initial_receipt(explanation)
                closed = evaluate_intelligence_improvement_loop(
                    receipt,
                    explanation=explanation,
                    adaptation_plan=adaptation_plan,
                    evolution_assessment=evolution_assessment,
                    experiment_aggregate=aggregate,
                    candidate_ref=final_ref,
                    promotion_ref=promotion_ref,
                    promoted_canonical_algorithm_ref=PROMOTED_REF,
                    promoted_component="MATHEMATICAL_ALGORITHM",
                    post_promotion_receipt=post_promotion_receipt(),
                )
                self.assertEqual("CLOSED_LOOP_IMPROVEMENT_VERIFIED", closed.status)
                self.assertTrue(closed.terminal)
                ledger.register_loop_decision(closed)
                ledger.rebuild_projection()
                self.assertEqual("CLOSED_LOOP_IMPROVEMENT_VERIFIED", ledger.decisions()[-1]["payload"]["status"])

                wrong_post = post_promotion_receipt()
                wrong_post = RetrieveFirstReceipt(
                    **{
                        **wrong_post.__dict__,
                        "selected_mathematical_algorithm_id": "canonical-algorithm:sha256:" + "8" * 64,
                    }
                )
                not_closed = evaluate_intelligence_improvement_loop(
                    receipt,
                    explanation=explanation,
                    adaptation_plan=adaptation_plan,
                    evolution_assessment=evolution_assessment,
                    experiment_aggregate=aggregate,
                    candidate_ref=final_ref,
                    promotion_ref=promotion_ref,
                    promoted_canonical_algorithm_ref=PROMOTED_REF,
                    promoted_component="MATHEMATICAL_ALGORITHM",
                    post_promotion_receipt=wrong_post,
                )
                self.assertFalse(not_closed.terminal)
                self.assertEqual(
                    "LOOP_POST_PROMOTION_RETRIEVAL_DID_NOT_SELECT_PROMOTED_KNOWLEDGE",
                    not_closed.status,
                )


if __name__ == "__main__":
    unittest.main()
