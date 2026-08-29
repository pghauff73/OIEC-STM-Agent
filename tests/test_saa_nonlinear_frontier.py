from __future__ import annotations

import unittest
from fractions import Fraction

from ourd.egcf.nonlinear import (
    ExactPolynomialSystem,
    ExactPolynomialTerm,
    acquire_exact_polynomial_jet,
    assess_nonlinear_lie_structure,
    bound_local_behavior_difference,
    build_carleman_koopman_lift,
    certify_exact_polynomial_global_equivalence,
    certify_polynomial_remainder,
    certify_regional_global_equivalence,
    make_control_affine_polynomial_system,
    make_global_equivalence_cell,
)
from tests.test_saa_canonical_representative import build_form, ctf


def poly(input_count, output_count, rows):
    return ExactPolynomialSystem(
        input_count=input_count,
        output_count=output_count,
        terms=tuple(
            ExactPolynomialTerm(output, tuple(powers), Fraction(coefficient))
            for output, powers, coefficient in rows
        ),
    )


class SAA78LieTests(unittest.TestCase):
    def test_double_integrator_is_locally_accessible_and_observable_through_lie_structure(self) -> None:
        drift = poly(2, 2, ((0, (0, 1), 1),))
        control = poly(2, 2, ((1, (0, 0), 1),))
        outputs = poly(2, 1, ((0, (1, 0), 1),))
        system = make_control_affine_polynomial_system(
            state_dimension=2,
            drift=drift,
            control_fields=(control,),
            outputs=outputs,
            domain_center=(0, 0),
            domain_radius=(1, 1),
        )
        assessment = assess_nonlinear_lie_structure(
            system,
            operating_point=(0, 0),
            max_depth=2,
        )
        self.assertEqual(2, assessment.accessibility.rank)
        self.assertEqual(2, assessment.observability.rank)
        self.assertTrue(assessment.locally_accessible_and_observable)
        self.assertFalse(assessment.global_claim_eligible)
        self.assertFalse(assessment.accessibility.global_accessibility_eligible)
        self.assertFalse(assessment.observability.global_observability_eligible)

    def test_missing_control_direction_does_not_self_certify_accessibility(self) -> None:
        drift = poly(2, 2, ((0, (0, 1), 1),))
        outputs = poly(2, 1, ((0, (1, 0), 1),))
        system = make_control_affine_polynomial_system(
            state_dimension=2,
            drift=drift,
            control_fields=(),
            outputs=outputs,
            domain_center=(0, 0),
            domain_radius=(1, 1),
        )
        assessment = assess_nonlinear_lie_structure(system, operating_point=(0, 0))
        self.assertEqual(0, assessment.accessibility.rank)
        self.assertFalse(assessment.accessibility.full_rank)


class SAA79RemainderTests(unittest.TestCase):
    def test_exact_cubic_polynomial_gets_rigorous_local_remainder_bound(self) -> None:
        form, _, _, _ = build_form(((ctf(1),),), meanings={0: "normalized state"})
        full = poly(1, 1, ((0, (1,), 1), (0, (3,), 1)))
        evidence = acquire_exact_polynomial_jet(
            form,
            full,
            center=(Fraction(1, 2),),
            validity_radius=(Fraction(1, 4),),
            order=2,
        )
        certificate = certify_polynomial_remainder(evidence, full)
        self.assertEqual((Fraction(1, 64),), certificate.output_absolute_upper)
        self.assertTrue(certificate.exact_containment)
        self.assertFalse(certificate.global_equivalence_eligible)

    def test_local_difference_bound_is_zero_only_when_jets_and_remainders_are_exactly_zero_delta(self) -> None:
        form, _, _, _ = build_form(((ctf(1),),), meanings={0: "normalized state"})
        full = poly(1, 1, ((0, (1,), 1),))
        left = acquire_exact_polynomial_jet(
            form, full, center=(Fraction(1, 2),), validity_radius=(Fraction(1, 4),), order=2
        )
        right = acquire_exact_polynomial_jet(
            form, full, center=(Fraction(1, 2),), validity_radius=(Fraction(1, 8),), order=2
        )
        assert left.jet is not None and right.jet is not None
        left_remainder = certify_polynomial_remainder(left, full)
        right_remainder = certify_polynomial_remainder(right, full)
        delta = bound_local_behavior_difference(
            left.jet,
            right.jet,
            left_remainder=left_remainder,
            right_remainder=right_remainder,
        )
        self.assertTrue(delta.exact_zero_difference)
        self.assertTrue(delta.local_equivalence_eligible)
        self.assertFalse(delta.global_equivalence_eligible)


class SAA710GlobalTests(unittest.TestCase):
    def test_exact_polynomial_identity_plus_same_semantics_can_certify_declared_domain(self) -> None:
        left = poly(1, 1, ((0, (1,), 1), (0, (2,), 1), (0, (2,), 2)))
        right = poly(1, 1, ((0, (2,), 3), (0, (1,), 1)))
        certificate = certify_exact_polynomial_global_equivalence(
            left,
            right,
            left_semantic_signature="semantic:x",
            right_semantic_signature="semantic:x",
            domain_lower=(0,),
            domain_upper=(1,),
        )
        self.assertTrue(certificate.global_equivalence_eligible)
        self.assertTrue(certificate.mathematical_equivalence)
        self.assertTrue(certificate.semantic_equivalence)

    def test_same_polynomial_with_different_meaning_is_not_global_algorithm_equivalence(self) -> None:
        system = poly(1, 1, ((0, (1,), 1),))
        certificate = certify_exact_polynomial_global_equivalence(
            system,
            system,
            left_semantic_signature="temperature",
            right_semantic_signature="pressure",
            domain_lower=(0,),
            domain_upper=(1,),
        )
        self.assertEqual("GLOBAL_MATHEMATICAL_MATCH_SEMANTIC_DIFFERENCE", certificate.status)
        self.assertFalse(certificate.global_equivalence_eligible)

    def test_finite_zero_error_cover_can_certify_whole_normalized_domain(self) -> None:
        cells = (
            make_global_equivalence_cell(
                lower=(0,), upper=(Fraction(1, 2),), output_delta_upper=(0,),
                semantic_signature="semantic:x", certificate_id="cell:a"
            ),
            make_global_equivalence_cell(
                lower=(Fraction(1, 2),), upper=(1,), output_delta_upper=(0,),
                semantic_signature="semantic:x", certificate_id="cell:b"
            ),
        )
        certificate = certify_regional_global_equivalence(
            cells,
            domain_lower=(0,),
            domain_upper=(1,),
        )
        self.assertTrue(certificate.complete_domain_coverage)
        self.assertTrue(certificate.global_equivalence_eligible)

    def test_gap_in_regional_cover_blocks_global_promotion(self) -> None:
        cells = (
            make_global_equivalence_cell(
                lower=(0,), upper=(Fraction(2, 5),), output_delta_upper=(0,),
                semantic_signature="semantic:x", certificate_id="cell:a"
            ),
            make_global_equivalence_cell(
                lower=(Fraction(3, 5),), upper=(1,), output_delta_upper=(0,),
                semantic_signature="semantic:x", certificate_id="cell:b"
            ),
        )
        certificate = certify_regional_global_equivalence(cells, domain_lower=(0,), domain_upper=(1,))
        self.assertFalse(certificate.complete_domain_coverage)
        self.assertFalse(certificate.global_equivalence_eligible)


class SAA711LiftTests(unittest.TestCase):
    def test_linear_polynomial_dynamics_close_exactly_in_finite_monomial_lift(self) -> None:
        dynamics = poly(1, 1, ((0, (1,), 1),))
        lift = build_carleman_koopman_lift(dynamics, lift_degree=2)
        self.assertTrue(lift.exact_finite_closure)
        self.assertTrue(lift.canonical_equivalence_eligible)
        self.assertFalse(lift.discovery_aid_only)
        self.assertEqual((), lift.remainder_terms)

    def test_nonlinear_polynomial_dynamics_expose_truncation_remainder(self) -> None:
        dynamics = poly(1, 1, ((0, (2,), 1),))
        lift = build_carleman_koopman_lift(dynamics, lift_degree=2)
        self.assertFalse(lift.exact_finite_closure)
        self.assertFalse(lift.canonical_equivalence_eligible)
        self.assertTrue(lift.discovery_aid_only)
        self.assertTrue(any(item.powers == (3,) for item in lift.remainder_terms))


if __name__ == "__main__":
    unittest.main()
