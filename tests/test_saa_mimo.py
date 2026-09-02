from __future__ import annotations

import math
import unittest
from fractions import Fraction

from ourd.egcf.algebra import (
    LinearTransferFunction,
    MIMOTransferMatrix,
    build_normalization_contract,
    canonicalize_mapping,
    canonicalize_mimo_transfer_matrix,
    mimo_algorithm_signature,
    structure_from_mapping,
)
from ourd.egcf.errors import EGCFError


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
        "name": "mimo-fixture",
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


def normalization(
    inputs: int,
    outputs: int,
    *,
    input_bounds=None,
    output_bounds=None,
    time=1,
):
    spec = structure_from_mapping(algorithm_mapping(inputs, outputs))
    return build_normalization_contract(
        spec,
        input_bounds=(
            input_bounds
            if input_bounds is not None
            else {index: [0, 1] for index in range(inputs)}
        ),
        output_bounds=(
            output_bounds
            if output_bounds is not None
            else {index: [0, 1] for index in range(outputs)}
        ),
        time=time,
    )


def ctf(value, *, sample_period=None):
    return LinearTransferFunction(
        domain="DISCRETE" if sample_period is not None else "CONTINUOUS",
        numerator=(str(value),),
        denominator=(1,),
        sample_period=sample_period,
    )


def tf(numerator, denominator, *, sample_period=None):
    return LinearTransferFunction(
        domain="DISCRETE" if sample_period is not None else "CONTINUOUS",
        numerator=tuple(numerator),
        denominator=tuple(denominator),
        sample_period=sample_period,
    )


class MIMOCanonicalizationTests(unittest.TestCase):
    def test_exact_diagonal_matrix_has_identity_rga_and_zero_residual(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(2), ctf(0)),
                (ctf(0), ctf(4)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertEqual("EXACT_MIMO_LINEAR_DYNAMICS", result.dynamic_strength)
        self.assertEqual("EXACT_COUPLING_ANALYSIS", result.coupling_strength)
        self.assertTrue(result.permutation_decoupled)
        self.assertEqual((0, 1), result.exact_diagonal_input_permutation)
        self.assertEqual(
            ((Fraction(1), Fraction(0)), (Fraction(0), Fraction(1))),
            result.relative_gain_array,
        )
        self.assertEqual((0, 1), result.preferred_rga_pairing)
        self.assertEqual(Fraction(0), result.rga_off_pairing_mass)
        self.assertIsNotNone(result.static_decoupling)
        assert result.static_decoupling is not None
        self.assertTrue(
            all(ratio == 0.0 for _, ratio in result.static_decoupling.residual_coupling_samples)
        )

    def test_crossed_diagonal_matrix_finds_port_pairing(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(0), ctf(2)),
                (ctf(3), ctf(0)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertTrue(result.permutation_decoupled)
        self.assertEqual((1, 0), result.exact_diagonal_input_permutation)
        self.assertEqual((1, 0), result.preferred_rga_pairing)
        self.assertEqual(Fraction(0), result.rga_off_pairing_mass)

    def test_rga_reports_coupling_and_static_decoupler(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(1), ctf("1/2")),
                (ctf("1/4"), ctf(1)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertFalse(result.permutation_decoupled)
        self.assertEqual(
            (
                (Fraction(8, 7), Fraction(-1, 7)),
                (Fraction(-1, 7), Fraction(8, 7)),
            ),
            result.relative_gain_array,
        )
        self.assertEqual((0, 1), result.preferred_rga_pairing)
        self.assertEqual(Fraction(1, 9), result.rga_off_pairing_mass)
        self.assertIsNotNone(result.static_decoupling)
        assert result.static_decoupling is not None
        self.assertTrue(
            all(ratio == 0.0 for _, ratio in result.static_decoupling.residual_coupling_samples)
        )

    def test_dynamic_system_retains_residual_coupling_after_dc_decoupling(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (tf((1,), (1, 1)), tf((1,), (1, 2))),
                (tf((1,), (1, 3)), tf((1,), (1, 1))),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertIsNotNone(result.static_decoupling)
        assert result.static_decoupling is not None
        ratios = [ratio for _, ratio in result.static_decoupling.residual_coupling_samples]
        self.assertTrue(any(math.isfinite(value) and value > 1e-8 for value in ratios))

    def test_port_permutation_changes_ordered_not_invariant_signature(self) -> None:
        first = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(1), ctf(2)),
                (ctf(3), ctf(4)),
            ),
        )
        second = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(2), ctf(1)),
                (ctf(4), ctf(3)),
            ),
        )
        contract = normalization(2, 2)
        left = canonicalize_mimo_transfer_matrix(first, contract)
        right = canonicalize_mimo_transfer_matrix(second, contract)
        self.assertNotEqual(left.ordered_signature, right.ordered_signature)
        self.assertEqual(
            left.permutation_invariant_signature,
            right.permutation_invariant_signature,
        )
        self.assertEqual("EXACT_PORT_PERMUTATION", left.permutation_strength)

    def test_permutation_budget_fails_conservatively(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            tuple(
                tuple(ctf(1 if row == column else 0) for column in range(5))
                for row in range(5)
            ),
        )
        result = canonicalize_mimo_transfer_matrix(
            matrix,
            normalization(5, 5),
            max_port_permutations=10,
        )
        self.assertIsNone(result.permutation_invariant_signature)
        self.assertEqual(
            "ORDERED_ONLY_PERMUTATION_BUDGET_EXCEEDED",
            result.permutation_strength,
        )
        self.assertTrue(result.warnings)

    def test_singular_steady_gain_has_no_rga_or_static_decoupler(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(1), ctf(1)),
                (ctf(2), ctf(2)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertIsNone(result.relative_gain_array)
        self.assertIsNone(result.static_decoupling)
        self.assertTrue(any("RGA unavailable" in warning for warning in result.warnings))

    def test_dc_pole_blocks_rga(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (tf((1,), (1, 0)), ctf(0)),
                (ctf(0), ctf(1)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertIsNone(result.steady_gain[0][0])
        self.assertIsNone(result.relative_gain_array)
        self.assertIsNone(result.static_decoupling)

    def test_approximate_channel_downgrades_and_blocks_exact_decoupler(self) -> None:
        approximate = LinearTransferFunction(
            "CONTINUOUS", numerator=(1.0,), denominator=(1.0,)
        )
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (approximate, ctf(0)),
                (ctf(0), ctf(1)),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))
        self.assertEqual("APPROXIMATE_MIMO_LINEAR_DYNAMICS", result.dynamic_strength)
        self.assertEqual("APPROXIMATE_COUPLING_ANALYSIS", result.coupling_strength)
        self.assertIsNone(result.static_decoupling)

    def test_discrete_matrix_records_common_dimensionless_sample_interval(self) -> None:
        matrix = MIMOTransferMatrix(
            "DISCRETE",
            (
                (ctf(1, sample_period="1/2"), ctf(0, sample_period="1/2")),
                (ctf(0, sample_period="1/2"), ctf(1, sample_period="1/2")),
            ),
        )
        result = canonicalize_mimo_transfer_matrix(
            matrix, normalization(2, 2, time=1)
        )
        self.assertEqual("DISCRETE", result.domain)
        self.assertEqual(Fraction(1, 2), result.normalized_sample_interval)

    def test_mixed_discrete_sample_intervals_fail_closed(self) -> None:
        matrix = MIMOTransferMatrix(
            "DISCRETE",
            (
                (ctf(1, sample_period=1), ctf(0, sample_period=1)),
                (ctf(0, sample_period=1), ctf(1, sample_period=2)),
            ),
        )
        with self.assertRaises(EGCFError):
            canonicalize_mimo_transfer_matrix(matrix, normalization(2, 2))

    def test_normalization_dimension_mismatch_fails_closed(self) -> None:
        matrix = MIMOTransferMatrix(
            "CONTINUOUS",
            (
                (ctf(1), ctf(0)),
                (ctf(0), ctf(1)),
            ),
        )
        with self.assertRaises(EGCFError):
            canonicalize_mimo_transfer_matrix(matrix, normalization(1, 2))

    def test_non_rectangular_and_oversized_matrices_fail_closed(self) -> None:
        with self.assertRaises(EGCFError):
            MIMOTransferMatrix(
                "CONTINUOUS",
                ((ctf(1), ctf(2)), (ctf(3),)),
            )
        with self.assertRaises(EGCFError):
            MIMOTransferMatrix(
                "CONTINUOUS",
                tuple(tuple(ctf(0) for _ in range(7)) for _ in range(2)),
            )


class MIMOAlgorithmSignatureTests(unittest.TestCase):
    def test_combined_signature_can_ignore_port_order_only_when_qualified(self) -> None:
        mapping = algorithm_mapping(2, 2)
        ir = canonicalize_mapping(mapping)
        contract = normalization(2, 2)
        first = canonicalize_mimo_transfer_matrix(
            MIMOTransferMatrix(
                "CONTINUOUS",
                ((ctf(1), ctf(2)), (ctf(3), ctf(4))),
            ),
            contract,
        )
        second = canonicalize_mimo_transfer_matrix(
            MIMOTransferMatrix(
                "CONTINUOUS",
                ((ctf(2), ctf(1)), (ctf(4), ctf(3))),
            ),
            contract,
        )
        self.assertNotEqual(
            mimo_algorithm_signature(ir, contract, first),
            mimo_algorithm_signature(ir, contract, second),
        )
        self.assertEqual(
            mimo_algorithm_signature(
                ir, contract, first, ignore_port_order=True
            ),
            mimo_algorithm_signature(
                ir, contract, second, ignore_port_order=True
            ),
        )

    def test_ignore_port_order_fails_when_permutation_search_was_not_done(self) -> None:
        mapping = algorithm_mapping(5, 5)
        ir = canonicalize_mapping(mapping)
        contract = normalization(5, 5)
        result = canonicalize_mimo_transfer_matrix(
            MIMOTransferMatrix(
                "CONTINUOUS",
                tuple(
                    tuple(ctf(1 if row == column else 0) for column in range(5))
                    for row in range(5)
                ),
            ),
            contract,
            max_port_permutations=1,
        )
        with self.assertRaises(EGCFError):
            mimo_algorithm_signature(
                ir, contract, result, ignore_port_order=True
            )


if __name__ == "__main__":
    unittest.main()
