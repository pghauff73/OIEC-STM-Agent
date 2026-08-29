from __future__ import annotations

import unittest
from fractions import Fraction

from ourd.egcf.algebra import (
    LinearTransferFunction,
    MIMOTransferMatrix,
    assess_mimo_representation,
    build_normalization_contract,
    canonicalize_mimo_transfer_matrix,
    discover_representative_inputs,
    structure_from_mapping,
)


def algorithm_mapping(inputs: int, outputs: int):
    nodes = [
        {
            "id": f"out{index}",
            "primitive": "CONST",
            "operands": [{"constant": 0}],
        }
        for index in range(outputs)
    ]
    return {
        "name": "representative-fixture",
        "inputs": [
            {"position": index, "name": f"u{index}", "data_type": "scalar"}
            for index in range(inputs)
        ],
        "outputs": [
            {
                "position": index,
                "name": f"y{index}",
                "data_type": "scalar",
                "source": {"node": f"out{index}"},
            }
            for index in range(outputs)
        ],
        "nodes": nodes,
        "entry_nodes": [node["id"] for node in nodes],
    }


def normalization(inputs: int, outputs: int, *, time=1):
    return build_normalization_contract(
        structure_from_mapping(algorithm_mapping(inputs, outputs)),
        input_bounds={index: [0, 1] for index in range(inputs)},
        output_bounds={index: [0, 1] for index in range(outputs)},
        time=time,
    )


def ctf(value):
    return LinearTransferFunction(
        "CONTINUOUS",
        numerator=(str(value),),
        denominator=(1,),
    )


def tf(numerator, denominator):
    return LinearTransferFunction(
        "CONTINUOUS",
        numerator=tuple(numerator),
        denominator=tuple(denominator),
    )


def canonical(rows):
    matrix = MIMOTransferMatrix("CONTINUOUS", tuple(tuple(row) for row in rows))
    return canonicalize_mimo_transfer_matrix(
        matrix,
        normalization(len(rows[0]), len(rows)),
    )


class SAA41RepresentationAssessmentTests(unittest.TestCase):
    def test_exact_diagonal_basis_is_representative(self) -> None:
        result = canonical(((ctf(2), ctf(0)), (ctf(0), ctf(3))))
        assessment = assess_mimo_representation(result)
        self.assertEqual("REPRESENTATIVE_EXACT", assessment.status)
        self.assertEqual(0, assessment.coupling_bp)
        self.assertTrue(assessment.canonical_admission_eligible)
        self.assertFalse(assessment.requires_representative_search)

    def test_crossed_port_order_is_representative_up_to_pairing(self) -> None:
        result = canonical(((ctf(0), ctf(2)), (ctf(3), ctf(0))))
        assessment = assess_mimo_representation(result)
        self.assertEqual("REPRESENTATIVE_EXACT", assessment.status)
        self.assertEqual((1, 0), assessment.preferred_input_to_output_pairing)
        self.assertEqual(0, assessment.coupling_bp)

    def test_coupling_marks_source_as_non_representative(self) -> None:
        result = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        assessment = assess_mimo_representation(result)
        self.assertEqual("NON_REPRESENTATIVE_COUPLED", assessment.status)
        self.assertGreater(assessment.coupling_bp or 0, 0)
        self.assertFalse(assessment.canonical_admission_eligible)
        self.assertTrue(assessment.requires_representative_search)

    def test_exact_redundant_inputs_are_non_representative(self) -> None:
        result = canonical(
            (
                (ctf(1), ctf(2), ctf(0)),
                (ctf(0), ctf(0), ctf(1)),
            )
        )
        assessment = assess_mimo_representation(result)
        self.assertEqual("NON_REPRESENTATIVE_REDUNDANT_INPUTS", assessment.status)
        assert assessment.minimality is not None
        self.assertEqual(2, assessment.minimality.effective_input_rank)
        self.assertEqual(1, assessment.minimality.redundant_input_count)
        self.assertEqual((0, 2), assessment.minimality.pivot_input_positions)
        self.assertEqual(
            (
                (Fraction(1), Fraction(2), Fraction(0)),
                (Fraction(0), Fraction(0), Fraction(1)),
            ),
            assessment.minimality.source_to_basis_projection,
        )

    def test_approximate_dynamics_do_not_claim_representativeness(self) -> None:
        approximate = LinearTransferFunction(
            "CONTINUOUS", numerator=(1.0,), denominator=(1.0,)
        )
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            ((approximate, ctf(0)), (ctf(0), ctf(1))),
        )
        mimo = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        assessment = assess_mimo_representation(mimo)
        self.assertEqual("REPRESENTATION_UNRESOLVED_APPROXIMATE", assessment.status)
        self.assertFalse(assessment.canonical_admission_eligible)

    def test_rank_budget_failure_is_explicit(self) -> None:
        result = canonical(((ctf(1), ctf(1)), (ctf(1), ctf(-1))))
        assessment = assess_mimo_representation(result, max_rank_terms=1)
        self.assertEqual("REPRESENTATION_UNRESOLVED_RANK_BUDGET", assessment.status)
        self.assertTrue(assessment.warnings)


class SAA5RepresentativeInputDiscoveryTests(unittest.TestCase):
    def test_static_coupled_system_finds_exact_representative_basis(self) -> None:
        mimo = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        search = discover_representative_inputs(mimo)
        self.assertEqual("REPRESENTATIVE_FORM_FOUND", search.search_status)
        self.assertTrue(search.representative_found)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual("REPRESENTATIVE_FORM_CANDIDATE", candidate.status)
        self.assertEqual(0, candidate.coupling_after_bp)
        self.assertTrue(candidate.exact_decoupled)
        self.assertTrue(candidate.admissibility.admissible)
        self.assertEqual("FULLY_INVERTIBLE", candidate.admissibility.invertibility_status)
        self.assertTrue(candidate.requires_renormalization)

    def test_constant_dynamic_mixing_is_decoupled_not_just_at_probe(self) -> None:
        g1 = tf((1,), (1, 1))
        g1_neg = tf((-1,), (1, 1))
        g2 = tf((1,), (1, 2))
        g2_neg = tf((-1,), (1, 2))
        # G(q) = diag(g1, g2) [[1,1],[1,-1]].
        mimo = canonical(((g1, g1), (g2, g2_neg)))
        search = discover_representative_inputs(mimo)
        self.assertTrue(search.representative_found)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual(0, candidate.coupling_after_bp)
        self.assertTrue(candidate.exact_decoupled)
        self.assertEqual("CONSTANT_LINEAR_ALGEBRAIC_PROBE", candidate.transform_class)

    def test_dc_pole_can_use_later_exact_algebraic_probe(self) -> None:
        pole = tf((1,), (1, 0))
        pole_neg = tf((-1,), (1, 0))
        mimo = canonical(((pole, pole), (ctf(1), ctf(-1))))
        self.assertIsNone(mimo.static_decoupling)
        search = discover_representative_inputs(mimo)
        self.assertTrue(search.representative_found)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertIsNotNone(candidate.algebraic_probe)
        self.assertNotEqual(Fraction(0), candidate.algebraic_probe)

    def test_system_without_constant_decoupling_remains_unresolved(self) -> None:
        mimo = canonical(
            (
                (tf((1,), (1, 1)), tf((1,), (1, 2))),
                (tf((1,), (1, 3)), tf((1,), (1, 1))),
            )
        )
        search = discover_representative_inputs(mimo)
        self.assertFalse(search.representative_found)
        self.assertEqual(
            "REPRESENTATIVE_FORM_UNRESOLVED_CONSTANT_LINEAR_SEARCH",
            search.search_status,
        )
        assert search.best_candidate is not None
        self.assertGreater(search.best_candidate.coupling_after_bp, 0)

    def test_search_budget_exhaustion_is_not_equivalence(self) -> None:
        mimo = canonical(((ctf(1), ctf(1)), (ctf(1), ctf(-1))))
        search = discover_representative_inputs(mimo, max_transforms=1)
        self.assertFalse(search.representative_found)
        self.assertEqual("REPRESENTATIVE_SEARCH_BUDGET_EXHAUSTED", search.search_status)

    def test_approximate_dynamics_do_not_enter_exact_basis_search(self) -> None:
        approximate = LinearTransferFunction(
            "CONTINUOUS", numerator=(1.0,), denominator=(1.0,)
        )
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            ((approximate, ctf(1)), (ctf(1), ctf(-1))),
        )
        mimo = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        search = discover_representative_inputs(mimo)
        self.assertEqual(
            "REPRESENTATIVE_FORM_UNRESOLVED_APPROXIMATE",
            search.search_status,
        )
        self.assertEqual(0, search.candidates_considered)
        self.assertIsNone(search.best_candidate)


class SAA51MinimalityTests(unittest.TestCase):
    def test_general_constant_linear_redundancy_is_quotiented(self) -> None:
        # Third source column equals column 0 + column 1, not merely a duplicate.
        mimo = canonical(
            (
                (ctf(1), ctf(0), ctf(1)),
                (ctf(0), ctf(1), ctf(1)),
            )
        )
        search = discover_representative_inputs(mimo)
        assert search.minimality is not None
        self.assertEqual(2, search.minimality.effective_input_rank)
        self.assertEqual(
            (
                (Fraction(1), Fraction(0), Fraction(1)),
                (Fraction(0), Fraction(1), Fraction(1)),
            ),
            search.minimality.source_to_basis_projection,
        )
        self.assertTrue(search.representative_found)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual(2, candidate.representative_input_count)
        self.assertEqual(
            "INVERTIBLE_ON_BEHAVIORAL_QUOTIENT",
            candidate.admissibility.invertibility_status,
        )

    def test_zero_effective_input_system_collapses_to_zero_inputs(self) -> None:
        mimo = canonical(((ctf(0), ctf(0)), (ctf(0), ctf(0))))
        search = discover_representative_inputs(mimo)
        self.assertTrue(search.representative_found)
        candidate = search.best_candidate
        assert candidate is not None
        self.assertEqual(0, candidate.representative_input_count)
        self.assertEqual("BEHAVIORAL_ZERO_INPUT_QUOTIENT", candidate.transform_class)


class SAA52AdmissibilityTests(unittest.TestCase):
    def test_behavioral_quotient_has_exact_right_inverse_section(self) -> None:
        mimo = canonical(
            (
                (ctf(1), ctf(0), ctf(1)),
                (ctf(0), ctf(1), ctf(1)),
            )
        )
        search = discover_representative_inputs(mimo)
        candidate = search.best_candidate
        assert candidate is not None
        q = candidate.source_to_representative_projection
        section = candidate.representative_to_source_section
        product = tuple(
            tuple(
                sum(
                    (q[row][index] * section[index][column] for index in range(len(section))),
                    Fraction(0),
                )
                for column in range(candidate.representative_input_count)
            )
            for row in range(candidate.representative_input_count)
        )
        self.assertEqual(
            (
                (Fraction(1), Fraction(0)),
                (Fraction(0), Fraction(1)),
            ),
            product,
        )
        self.assertTrue(candidate.admissibility.causal)
        self.assertTrue(candidate.admissibility.stable)
        self.assertTrue(candidate.admissibility.finite_real)

    def test_large_exact_transform_is_rejected_by_configured_bit_budget(self) -> None:
        mimo = canonical(((ctf(1), ctf("1/2")), (ctf("1/4"), ctf(1))))
        search = discover_representative_inputs(
            mimo,
            max_transform_coefficient_bits=1,
        )
        self.assertFalse(search.representative_found)
        assert search.best_candidate is not None
        self.assertFalse(search.best_candidate.admissibility.admissible)
        self.assertEqual("INADMISSIBLE_TRANSFORM", search.best_candidate.admissibility.status)


if __name__ == "__main__":
    unittest.main()
