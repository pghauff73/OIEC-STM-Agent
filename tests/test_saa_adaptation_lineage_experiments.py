from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from ourd.egcf.adaptation import (
    AdaptationLineageStore,
    AdaptationStep,
    ExperimentMetricSpec,
    adapted_candidate_ref,
    create_adapted_candidate,
    make_ab_experiment_design,
    make_adaptation_promotion,
    make_variant_observation,
    qualify_ab_experiment,
)
from ourd.egcf.errors import EGCFError
from ourd.egcf.ids import sha256_json
from ourd.egcf.models import EvidenceArtifact
from ourd.egcf.store import EGCFStore


BASE_REF = "canonical-algorithm:sha256:" + "a" * 64
EXPLANATION_SIG = "b" * 64
CONTEXT_SIG = "c" * 64
QUALIFICATION_SIG = "d" * 64


def adaptation_step(index: int, dimension: str = "DYNAMICS_CONTRACT") -> AdaptationStep:
    material = {
        "index": index,
        "component": "MATHEMATICAL_ALGORITHM",
        "dimension": dimension,
        "base_algorithm_id": BASE_REF,
    }
    return AdaptationStep(
        index=index,
        component="MATHEMATICAL_ALGORITHM",
        dimension=dimension,
        base_algorithm_id=BASE_REF,
        current_contract="source contract",
        target_contract="target contract",
        proposed_change={"dimension": dimension},
        step_signature=sha256_json(material),
    )


def evidence(requirements, group: str, *, success: bool = True, simulated: bool = False):
    payload = {"requirements": list(requirements), "group": group, "success": success}
    return EvidenceArtifact(
        subject_id="saa-11.2-experiment",
        claim_ids=[],
        requirement_ids=list(requirements),
        category="benchmark",
        producer="deterministic-saa-11-test",
        method="controlled-ab-experiment",
        source_snapshot_hash=sha256_json(payload),
        target="algorithm comparison",
        oracle="exact-metric-oracle",
        environment={"suite": "saa-11.1-11.2"},
        command_id="experiment.compare@1",
        algorithm_id="saa-11-fixture",
        created_at="2026-08-30T00:00:00Z",
        sha256=sha256_json(payload),
        success=success,
        limitations=[],
        independence_group=group,
        simulated=simulated,
    )


class SAA111LineageTests(unittest.TestCase):
    def test_lineage_records_exact_parent_child_and_rebuilds(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                step1 = adaptation_step(0)
                candidate1 = create_adapted_candidate(
                    step1,
                    change_material={"dimension": "DYNAMICS_CONTRACT", "target": "dynamics-v2"},
                )
                ref1, _ = store.register_candidate(
                    candidate1,
                    step1,
                    source_explanation_signature=EXPLANATION_SIG,
                )
                self.assertEqual(adapted_candidate_ref(candidate1.candidate_signature), ref1)
                self.assertEqual((BASE_REF,), store.ancestors(ref1))

                step2 = adaptation_step(1, "BOUNDARY_CONTRACT")
                candidate2 = create_adapted_candidate(
                    step2,
                    change_material={"dimension": "BOUNDARY_CONTRACT", "target": "bounds-v2"},
                    parent_candidate_signature=candidate1.candidate_signature,
                )
                ref2, _ = store.register_candidate(
                    candidate2,
                    step2,
                    source_explanation_signature=EXPLANATION_SIG,
                )
                self.assertEqual((ref1, BASE_REF), store.ancestors(ref2))
                self.assertEqual((ref2,), store.children(ref1))

                store.rebuild_projection()
                self.assertEqual((ref1, BASE_REF), store.ancestors(ref2))
                self.assertEqual(2, len(store.candidates()))
                self.assertEqual(2, len(store.edges()))

    def test_unknown_parent_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                step = adaptation_step(1)
                candidate = create_adapted_candidate(
                    step,
                    change_material={"dimension": "DYNAMICS_CONTRACT", "target": "v3"},
                    parent_candidate_signature="e" * 64,
                )
                with self.assertRaises(EGCFError):
                    store.register_candidate(candidate, step, source_explanation_signature=EXPLANATION_SIG)

    def test_promotion_requires_grounded_evidence_and_preserves_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                step = adaptation_step(0)
                candidate = create_adapted_candidate(
                    step,
                    change_material={"dimension": "DYNAMICS_CONTRACT", "target": "qualified-v2"},
                )
                candidate_ref, _ = store.register_candidate(
                    candidate,
                    step,
                    source_explanation_signature=EXPLANATION_SIG,
                )
                evidence_id = egcf.register(evidence(("qualification",), "promotion"))
                promotion = make_adaptation_promotion(
                    candidate_ref=candidate_ref,
                    canonical_algorithm_ref="canonical-algorithm:sha256:" + "f" * 64,
                    qualification_signature=QUALIFICATION_SIG,
                    evidence_ids=(evidence_id,),
                )
                store.register_promotion(promotion)
                self.assertEqual(1, len(store.promotions(candidate_ref)))
                self.assertEqual((BASE_REF,), store.ancestors(candidate_ref))


class SAA112ExperimentTests(unittest.TestCase):
    def _registered_candidate(self, egcf, store):
        step = adaptation_step(0)
        candidate = create_adapted_candidate(
            step,
            change_material={"dimension": "DYNAMICS_CONTRACT", "target": "candidate-v2"},
        )
        candidate_ref, _ = store.register_candidate(
            candidate,
            step,
            source_explanation_signature=EXPLANATION_SIG,
        )
        return candidate_ref

    def _design(self, candidate_ref):
        return make_ab_experiment_design(
            baseline_ref=BASE_REF,
            candidate_ref=candidate_ref,
            context_signature=CONTEXT_SIG,
            metrics=(
                ExperimentMetricSpec("error", "LOWER_IS_BETTER", Fraction(1, 100)),
                ExperimentMetricSpec("throughput", "HIGHER_IS_BETTER", Fraction(1)),
            ),
            required_invariants=("bounded",),
            evidence_requirements=("benchmark",),
            minimum_trials=10,
        )

    def test_grounded_ab_experiment_can_qualify_candidate_improvement(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                candidate_ref = self._registered_candidate(egcf, store)
                design = self._design(candidate_ref)
                store.register_experiment_design(design)
                baseline_evidence = egcf.register(evidence(("benchmark",), "baseline"))
                candidate_evidence = egcf.register(evidence(("benchmark",), "candidate"))
                baseline = make_variant_observation(
                    design,
                    variant_ref=BASE_REF,
                    metric_values={"error": Fraction(10, 100), "throughput": 100},
                    evidence_ids=(baseline_evidence,),
                    invariant_results={"bounded": True},
                    trial_count=20,
                    execution_success=True,
                )
                candidate = make_variant_observation(
                    design,
                    variant_ref=candidate_ref,
                    metric_values={"error": Fraction(5, 100), "throughput": 103},
                    evidence_ids=(candidate_evidence,),
                    invariant_results={"bounded": True},
                    trial_count=20,
                    execution_success=True,
                )
                result = qualify_ab_experiment(
                    egcf,
                    design,
                    baseline,
                    candidate,
                    independent_review=True,
                )
                self.assertEqual("CANDIDATE_IMPROVEMENT_QUALIFIED", result.status)
                self.assertTrue(result.candidate_improvement_qualified)
                self.assertTrue(result.qualification_required_before_canonical_reuse)
                store.register_experiment_result(result)
                self.assertEqual(1, len(store.experiment_results(design.design_signature)))

                store.rebuild_projection()
                self.assertEqual(1, len(store.experiments()))
                self.assertEqual(1, len(store.experiment_results(design.design_signature)))

    def test_tradeoff_is_not_certified_as_better(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                candidate_ref = self._registered_candidate(egcf, store)
                design = self._design(candidate_ref)
                a_id = egcf.register(evidence(("benchmark",), "a"))
                b_id = egcf.register(evidence(("benchmark",), "b"))
                baseline = make_variant_observation(
                    design,
                    variant_ref=BASE_REF,
                    metric_values={"error": Fraction(10, 100), "throughput": 100},
                    evidence_ids=(a_id,),
                    invariant_results={"bounded": True},
                    trial_count=10,
                    execution_success=True,
                )
                candidate = make_variant_observation(
                    design,
                    variant_ref=candidate_ref,
                    metric_values={"error": Fraction(5, 100), "throughput": 95},
                    evidence_ids=(b_id,),
                    invariant_results={"bounded": True},
                    trial_count=10,
                    execution_success=True,
                )
                result = qualify_ab_experiment(egcf, design, baseline, candidate, independent_review=True)
                self.assertEqual("EXPERIMENT_TRADEOFF_UNRESOLVED", result.status)
                self.assertFalse(result.candidate_improvement_qualified)

    def test_ungrounded_experiment_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                candidate_ref = self._registered_candidate(egcf, store)
                design = self._design(candidate_ref)
                good_id = egcf.register(evidence(("benchmark",), "good"))
                baseline = make_variant_observation(
                    design,
                    variant_ref=BASE_REF,
                    metric_values={"error": Fraction(10, 100), "throughput": 100},
                    evidence_ids=(good_id,),
                    invariant_results={"bounded": True},
                    trial_count=10,
                    execution_success=True,
                )
                candidate = make_variant_observation(
                    design,
                    variant_ref=candidate_ref,
                    metric_values={"error": Fraction(5, 100), "throughput": 102},
                    evidence_ids=("missing-evidence",),
                    invariant_results={"bounded": True},
                    trial_count=10,
                    execution_success=True,
                )
                with self.assertRaises(EGCFError):
                    qualify_ab_experiment(egcf, design, baseline, candidate, independent_review=True)

    def test_experiment_store_rejects_candidate_outside_baseline_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            with EGCFStore(Path(temporary)) as egcf:
                store = AdaptationLineageStore(egcf)
                candidate_ref = self._registered_candidate(egcf, store)
                design = make_ab_experiment_design(
                    baseline_ref="canonical-algorithm:sha256:" + "9" * 64,
                    candidate_ref=candidate_ref,
                    context_signature=CONTEXT_SIG,
                    metrics=(ExperimentMetricSpec("error", "LOWER_IS_BETTER"),),
                )
                with self.assertRaises(EGCFError):
                    store.register_experiment_design(design)


if __name__ == "__main__":
    unittest.main()
