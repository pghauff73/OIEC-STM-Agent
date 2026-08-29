from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from ourd.egcf.algebra.jet import TaylorJetSpec, TaylorJetTerm, canonicalize_taylor_jet
from ourd.egcf.algebra.nonlinear_control import (
    assess_representative_observability_controllability,
    make_local_dynamic_linearization,
)
from ourd.egcf.algebra.nonlinear_evidence import (
    BoundedDerivativeEstimate,
    ExactDerivativeTerm,
    ExactPolynomialSystem,
    ExactPolynomialTerm,
    acquire_bounded_estimated_derivatives,
    acquire_exact_derivative_jet,
    acquire_exact_polynomial_jet,
)
from ourd.egcf.algebra.nonlinear_geometry import assess_nonlinear_geometry
from ourd.egcf.algebra.nonlinear_search import (
    canonicalize_nonlinear_representative,
    search_nonlinear_representative_coordinates,
)
from ourd.egcf.algebra.nonlinear_stability import (
    NonlinearRegionalObservation,
    assess_semantic_stability,
    make_regional_observation,
)
from ourd.egcf.algebra.nonlinear_transforms import (
    PolynomialShearTerm,
    apply_polynomial_shear,
    canonicalize_polynomial_representative,
    make_polynomial_shear,
    search_polynomial_automorphisms,
)
from ourd.egcf.algebra.semantic import (
    SemanticFalsifierResult,
    evaluate_semantic_candidate,
    make_semantic_candidate,
)
from ourd.egcf.errors import EGCFError
from ourd.egcf.nonlinear_store_api import NonlinearCanonicalStore
from tests.test_saa_canonical_representative import build_form, ctf


def parent_form():
    form, _, _, _ = build_form(
        ((ctf(1), ctf(0)), (ctf(0), ctf(1))),
        meanings={0: "temperature command", 1: "pressure command"},
    )
    return form


def self_nonlinear_system():
    return ExactPolynomialSystem(
        input_count=2,
        output_count=2,
        terms=(
            ExactPolynomialTerm(0, (2, 0), Fraction(1)),
            ExactPolynomialTerm(1, (0, 1), Fraction(1)),
        ),
    )


def local_evidence(center=(Fraction(1, 2), Fraction(1, 2)), radius=(Fraction(1, 4), Fraction(1, 4))):
    form = parent_form()
    evidence = acquire_exact_polynomial_jet(
        form,
        self_nonlinear_system(),
        center=center,
        validity_radius=radius,
        order=2,
    )
    assert evidence.jet is not None
    search = search_nonlinear_representative_coordinates(form, evidence.jet)
    local = canonicalize_nonlinear_representative(form, search)
    return form, evidence, search, local


def direct_jet(terms, *, order=3):
    form = parent_form()
    jet = canonicalize_taylor_jet(
        form,
        TaylorJetSpec(
            input_count=2,
            output_count=2,
            order=order,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=(Fraction(1, 4), Fraction(1, 4)),
            terms=tuple(terms),
        ),
    )
    return form, jet


class SAA72EvidenceTests(unittest.TestCase):
    def test_exact_symbolic_polynomial_expands_at_operating_point(self) -> None:
        form, evidence, _, _ = local_evidence()
        self.assertTrue(evidence.exact)
        self.assertTrue(evidence.canonical_local_eligible)
        self.assertEqual("EXACT_SYMBOLIC_POLYNOMIAL", evidence.evidence_kind)
        assert evidence.jet is not None
        self.assertEqual(
            (Fraction(9, 16), Fraction(1, 2)),
            evidence.jet.evaluate((Fraction(3, 4), Fraction(1, 2))),
        )
        self.assertEqual(form.representative_behavior_signature, evidence.parent_representative_behavior_signature)

    def test_exact_derivative_table_divides_by_multi_factorial(self) -> None:
        form = parent_form()
        evidence = acquire_exact_derivative_jet(
            form,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=(Fraction(1, 4), Fraction(1, 4)),
            order=2,
            derivatives=(
                ExactDerivativeTerm(0, (1, 0), Fraction(1)),
                ExactDerivativeTerm(0, (2, 0), Fraction(2)),
                ExactDerivativeTerm(1, (0, 1), Fraction(1)),
            ),
            source_snapshot_hash="a" * 64,
            producer="deterministic-test-oracle",
            independent_acquisition=True,
        )
        assert evidence.jet is not None
        coefficients = {
            (term.output_index, term.powers): term.coefficient
            for term in evidence.jet.terms
        }
        self.assertEqual(Fraction(1), coefficients[(0, (2, 0))])
        self.assertTrue(evidence.canonical_local_eligible)

    def test_reported_exact_values_do_not_self_qualify(self) -> None:
        form = parent_form()
        evidence = acquire_exact_derivative_jet(
            form,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=(Fraction(1, 4), Fraction(1, 4)),
            order=1,
            derivatives=(ExactDerivativeTerm(0, (1, 0), Fraction(1)),),
            source_snapshot_hash="b" * 64,
            producer="model-output",
            method="reported",
            independent_acquisition=False,
        )
        self.assertTrue(evidence.exact)
        self.assertFalse(evidence.canonical_local_eligible)

    def test_estimated_derivatives_never_enter_exact_jet_identity(self) -> None:
        form = parent_form()
        evidence = acquire_bounded_estimated_derivatives(
            form,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=(Fraction(1, 4), Fraction(1, 4)),
            order=2,
            estimates=(
                BoundedDerivativeEstimate(
                    0,
                    (1, 0),
                    Fraction(99, 100),
                    Fraction(101, 100),
                ),
            ),
            source_snapshot_hash="c" * 64,
            producer="human-lab",
            method="bounded-measurement",
        )
        self.assertFalse(evidence.exact)
        self.assertFalse(evidence.canonical_local_eligible)
        self.assertIsNone(evidence.jet)


class SAA73StabilityTests(unittest.TestCase):
    def test_overlapping_points_with_same_meaning_and_representation_are_regionally_stable(self) -> None:
        _, evidence_a, search_a, local_a = local_evidence(
            center=(Fraction(2, 5), Fraction(1, 2)),
            radius=(Fraction(1, 5), Fraction(1, 4)),
        )
        _, evidence_b, search_b, local_b = local_evidence(
            center=(Fraction(3, 5), Fraction(1, 2)),
            radius=(Fraction(1, 5), Fraction(1, 4)),
        )
        assessment = assess_semantic_stability(
            (
                make_regional_observation(local_a, search=search_a, evidence_signature=evidence_a.evidence_signature),
                make_regional_observation(local_b, search=search_b, evidence_signature=evidence_b.evidence_signature),
            )
        )
        self.assertEqual("REGIONALLY_STABLE_SEMANTICS", assessment.status)
        self.assertTrue(assessment.connected_region)
        self.assertTrue(assessment.regional_semantic_eligible)

    def test_disconnected_local_boxes_do_not_create_regional_truth(self) -> None:
        _, evidence_a, search_a, local_a = local_evidence(
            center=(Fraction(1, 4), Fraction(1, 2)),
            radius=(Fraction(1, 10), Fraction(1, 4)),
        )
        _, evidence_b, search_b, local_b = local_evidence(
            center=(Fraction(3, 4), Fraction(1, 2)),
            radius=(Fraction(1, 10), Fraction(1, 4)),
        )
        assessment = assess_semantic_stability(
            (
                make_regional_observation(local_a, search=search_a, evidence_signature=evidence_a.evidence_signature),
                make_regional_observation(local_b, search=search_b, evidence_signature=evidence_b.evidence_signature),
            )
        )
        self.assertEqual("MULTI_REGION_SEMANTICS_UNRESOLVED", assessment.status)
        self.assertFalse(assessment.regional_semantic_eligible)

    def test_same_meaning_with_changed_transform_family_is_regime_change(self) -> None:
        _, _, _, local_a = local_evidence()
        _, _, _, local_b = local_evidence(center=(Fraction(3, 5), Fraction(1, 2)))
        observation_a = NonlinearRegionalObservation(local_a, "a" * 64)
        observation_b = NonlinearRegionalObservation(local_b, "b" * 64)
        assessment = assess_semantic_stability((observation_a, observation_b))
        self.assertEqual("REPRESENTATION_REGIME_CHANGE", assessment.status)
        self.assertFalse(assessment.regional_semantic_eligible)


class SAA74StoreTests(unittest.TestCase):
    def test_local_store_reuses_same_knowledge_and_accumulates_provenance(self) -> None:
        _, evidence, _, local = local_evidence()
        with tempfile.TemporaryDirectory() as directory:
            with NonlinearCanonicalStore(Path(directory)) as store:
                first = store.admit_local(local, evidence)
                second = store.admit_local(local, evidence)
                self.assertEqual("ADMITTED_NEW_LOCAL_NONLINEAR_FORM", first["status"])
                self.assertEqual("REUSED_LOCAL_NONLINEAR_FORM", second["status"])
                self.assertEqual(first["generation"], second["generation"])
                self.assertEqual(1, len(store.local_signatures()))
                self.assertEqual([evidence.evidence_signature], store.evidence_for_local(local.local_representative_behavior_signature))

    def test_estimated_evidence_is_rejected_from_exact_local_store(self) -> None:
        form, _, _, local = local_evidence()
        estimated = acquire_bounded_estimated_derivatives(
            form,
            center=(Fraction(1, 2), Fraction(1, 2)),
            validity_radius=(Fraction(1, 4), Fraction(1, 4)),
            order=1,
            estimates=(BoundedDerivativeEstimate(0, (1, 0), Fraction(9, 10), Fraction(11, 10)),),
            source_snapshot_hash="d" * 64,
            producer="human-lab",
            method="bounded-measurement",
        )
        with tempfile.TemporaryDirectory() as directory:
            with NonlinearCanonicalStore(Path(directory)) as store:
                with self.assertRaises(EGCFError):
                    store.admit_local(local, estimated)

    def test_projection_rebuild_recovers_local_and_regional_indexes(self) -> None:
        _, evidence_a, search_a, local_a = local_evidence(
            center=(Fraction(2, 5), Fraction(1, 2)),
            radius=(Fraction(1, 5), Fraction(1, 4)),
        )
        _, evidence_b, search_b, local_b = local_evidence(
            center=(Fraction(3, 5), Fraction(1, 2)),
            radius=(Fraction(1, 5), Fraction(1, 4)),
        )
        stability = assess_semantic_stability(
            (
                make_regional_observation(local_a, search=search_a, evidence_signature=evidence_a.evidence_signature),
                make_regional_observation(local_b, search=search_b, evidence_signature=evidence_b.evidence_signature),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            with NonlinearCanonicalStore(Path(directory)) as store:
                store.admit_local(local_a, evidence_a)
                store.admit_local(local_b, evidence_b)
                store.admit_regional_stability(stability)
                store.rebuild_projection()
                self.assertEqual(2, len(store.local_signatures()))
                self.assertEqual(1, len(store.list_regional()))


class SAA75PolynomialTransformTests(unittest.TestCase):
    def test_multi_term_polynomial_shear_removes_two_coupled_terms_at_once(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(0, (0, 3), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=3,
        )
        transform = make_polynomial_shear(
            input_count=2,
            target_input_index=0,
            terms=(
                PolynomialShearTerm((0, 2), Fraction(1)),
                PolynomialShearTerm((0, 3), Fraction(1)),
            ),
        )
        transformed = apply_polynomial_shear(form, jet, transform)
        self.assertTrue(transformed.coupling.representative)
        self.assertEqual(
            {
                (term.output_index, term.powers, term.coefficient)
                for term in transformed.terms
            },
            {
                (0, (1, 0), Fraction(1)),
                (1, (0, 1), Fraction(1)),
            },
        )

    def test_broader_search_finds_grouped_exact_automorphism_and_requires_new_meaning(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (0, 2), Fraction(1)),
                TaylorJetTerm(0, (0, 3), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=3,
        )
        search = search_polynomial_automorphisms(form, jet)
        self.assertTrue(search.representative_found)
        self.assertEqual("POLYNOMIAL_REPRESENTATIVE_FORM_FOUND", search.status)
        self.assertEqual(1, len(search.best_candidate.transforms))
        self.assertEqual(2, len(search.best_candidate.transforms[0].terms))
        issue = search.best_candidate.semantic_issues[0]
        with self.assertRaises(EGCFError):
            canonicalize_polynomial_representative(form, search)

        falsifier = "new coordinate changes the excluded pressure output"
        semantic_candidate = make_semantic_candidate(
            issue,
            meaning="temperature command with nonlinear pressure compensation",
            expected_output_indices=issue.affected_output_indices,
            excluded_output_indices=(1,),
            falsifiers=(falsifier,),
        )
        resolution = evaluate_semantic_candidate(
            issue,
            semantic_candidate,
            evidence_ids=("evidence:poly-semantic",),
            falsifier_results=(
                SemanticFalsifierResult(falsifier, "SURVIVED", "evidence:poly-semantic"),
            ),
            independent_review=True,
        )
        local = canonicalize_polynomial_representative(
            form,
            search,
            semantic_candidates=(semantic_candidate,),
            semantic_resolutions=(resolution,),
        )
        self.assertTrue(local.local_canonical_eligible)
        self.assertFalse(local.global_equivalence_eligible)


class SAA76GeometryTests(unittest.TestCase):
    def test_full_rank_self_nonlinearity_has_local_diffeomorphism(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (2, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=2,
        )
        geometry = assess_nonlinear_geometry(form, jet)
        self.assertEqual(2, geometry.jacobian_rank)
        self.assertTrue(geometry.local_diffeomorphism)
        self.assertEqual(0, geometry.invariant_distribution_dimension)
        self.assertEqual("FULL_RANK_LOCAL_GEOMETRY", geometry.status)

    def test_constant_invariant_direction_is_detected_and_integrable(self) -> None:
        form, jet = direct_jet((TaylorJetTerm(0, (1, 0), Fraction(1)),), order=2)
        geometry = assess_nonlinear_geometry(form, jet)
        self.assertEqual(1, geometry.invariant_distribution_dimension)
        self.assertEqual((Fraction(0), Fraction(1)), geometry.invariant_distribution_basis[0])
        self.assertTrue(geometry.invariant_distribution_integrable)
        self.assertEqual("INVARIANT_REDUNDANT_DIRECTION_DETECTED", geometry.status)

    def test_cross_curvature_is_counted_exactly(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(0, (1, 1), Fraction(2)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=2,
        )
        geometry = assess_nonlinear_geometry(form, jet)
        self.assertEqual(1, geometry.cross_curvature_count)
        self.assertEqual(Fraction(2), geometry.hessian[0][0][1])


class SAA77ControlTests(unittest.TestCase):
    def test_static_map_can_be_observable_but_never_self_certifies_controllability(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=2,
        )
        assessment = assess_representative_observability_controllability(form, jet)
        self.assertTrue(assessment.representative_inputs_locally_observable)
        self.assertEqual("OBSERVABLE_CONTROLLABILITY_REQUIRES_DYNAMIC_MODEL", assessment.status)
        self.assertIsNone(assessment.dynamically_controllable)

    def test_exact_dynamic_linearization_can_qualify_local_observability_and_controllability(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=2,
        )
        dynamic = make_local_dynamic_linearization(
            form,
            a=((0, 1), (-1, 0)),
            b=((1, 0), (0, 1)),
            c=((1, 0), (0, 1)),
            state_meanings=("thermal state", "pressure state"),
        )
        assessment = assess_representative_observability_controllability(
            form,
            jet,
            dynamic_linearization=dynamic,
        )
        self.assertEqual(2, assessment.controllability_rank)
        self.assertEqual(2, assessment.observability_rank)
        self.assertEqual("LOCALLY_OBSERVABLE_AND_CONTROLLABLE", assessment.status)
        self.assertTrue(assessment.canonical_control_eligible)

    def test_uncontrollable_dynamic_state_is_blocked(self) -> None:
        form, jet = direct_jet(
            (
                TaylorJetTerm(0, (1, 0), Fraction(1)),
                TaylorJetTerm(1, (0, 1), Fraction(1)),
            ),
            order=2,
        )
        dynamic = make_local_dynamic_linearization(
            form,
            a=((0, 0), (0, 0)),
            b=((1, 0), (0, 0)),
            c=((1, 0), (0, 1)),
            state_meanings=("thermal state", "pressure state"),
        )
        assessment = assess_representative_observability_controllability(
            form,
            jet,
            dynamic_linearization=dynamic,
        )
        self.assertEqual(1, assessment.controllability_rank)
        self.assertEqual("DYNAMIC_UNCONTROLLABLE", assessment.status)
        self.assertFalse(assessment.canonical_control_eligible)


if __name__ == "__main__":
    unittest.main()
