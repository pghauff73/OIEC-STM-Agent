from __future__ import annotations

import math
import unittest

from ourd.egcf.algebra import canonicalize_mapping
from ourd.egcf.algebra.dynamics import (
    MAX_STATE_ORDER,
    LinearStateSpace,
    LinearTransferFunction,
    canonicalize_state_space,
    canonicalize_transfer_function,
    dynamic_algorithm_signature,
)
from ourd.egcf.algebra.ir import structure_from_mapping
from ourd.egcf.algebra.normalize import build_normalization_contract
from ourd.egcf.errors import EGCFError


def siso_mapping(*, input_type="scalar", output_type="scalar", input_name="u", output_name="y"):
    return {
        "name": "siso-linear-shell",
        "inputs": [
            {"position": 0, "name": input_name, "data_type": input_type},
        ],
        "outputs": [
            {
                "position": 0,
                "name": output_name,
                "data_type": output_type,
                "source": {"node": "identity"},
            }
        ],
        "nodes": [
            {
                "id": "identity",
                "primitive": "MULTIPLY",
                "operands": [{"input": 0}, {"constant": 1}],
            }
        ],
        "entry_nodes": ["identity"],
    }


def mimo_mapping():
    return {
        "name": "mimo-shell",
        "inputs": [
            {"position": 0, "name": "u0", "data_type": "scalar"},
            {"position": 1, "name": "u1", "data_type": "scalar"},
        ],
        "outputs": [
            {
                "position": 0,
                "name": "y",
                "data_type": "scalar",
                "source": {"node": "sum"},
            }
        ],
        "nodes": [
            {
                "id": "sum",
                "primitive": "ADD",
                "operands": [{"input": 0}, {"input": 1}],
            }
        ],
        "entry_nodes": ["sum"],
    }


def normalization(
    *,
    input_bounds=(0.0, 1.0),
    output_bounds=(0.0, 1.0),
    characteristic_time=1.0,
    bound_kind="EXACT_BOUND",
    mapping=None,
):
    payload = mapping or siso_mapping()
    return build_normalization_contract(
        structure_from_mapping(payload),
        input_bounds={
            index: {
                "minimum": bounds[0],
                "maximum": bounds[1],
                "kind": bound_kind,
            }
            for index, bounds in enumerate(
                [input_bounds]
                if len(payload.get("inputs", [])) == 1
                else [input_bounds] * len(payload.get("inputs", []))
            )
        },
        output_bounds={0: {
            "minimum": output_bounds[0],
            "maximum": output_bounds[1],
            "kind": bound_kind,
        }},
        time={
            "characteristic_time": characteristic_time,
            "kind": bound_kind,
            "unit": "source-time-unit",
        },
    )


class TransferFunctionCanonicalizationTests(unittest.TestCase):
    def test_scalar_polynomial_scaling_preserves_exact_signature(self) -> None:
        contract = normalization()
        first = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (2, 6, 4), (2, 8, 6)),
            contract,
        )
        second = canonicalize_transfer_function(
            LinearTransferFunction("s", (1, 2), (1, 3)),
            contract,
        )
        self.assertEqual("EXACT_LINEAR_DYNAMICS", first.dynamic_strength)
        self.assertEqual(first.canonical_signature, second.canonical_signature)
        self.assertIn("EXACT_COMMON_FACTOR_CANCELLATION", first.reductions)
        self.assertEqual(1, first.dynamic_order)

    def test_exact_common_pole_zero_factor_is_cancelled(self) -> None:
        result = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1, 3, 2), (1, 4, 3)),
            normalization(),
        )
        self.assertEqual(((1, 1), (2, 1)), tuple((v.numerator, v.denominator) for v in result.numerator))
        self.assertEqual(((1, 1), (3, 1)), tuple((v.numerator, v.denominator) for v in result.denominator))
        self.assertEqual(1, result.dynamic_order)

    def test_approximate_coefficients_do_not_receive_unsafe_factor_cancellation(self) -> None:
        approximate = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1.0, 3.0, 2.0), (1.0, 4.0, 3.0)),
            normalization(),
        )
        exact_reduced = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1, 2), (1, 3)),
            normalization(),
        )
        self.assertEqual("APPROXIMATE_LINEAR_DYNAMICS", approximate.dynamic_strength)
        self.assertEqual(2, approximate.dynamic_order)
        self.assertTrue(approximate.warnings)
        self.assertNotEqual(approximate.canonical_signature, exact_reduced.canonical_signature)

    def test_continuous_characteristic_time_removes_source_time_scale(self) -> None:
        slow = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1,), (1, 1)),
            normalization(characteristic_time=1.0),
        )
        fast = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1000,), (1, 1000)),
            normalization(characteristic_time=0.001),
        )
        self.assertEqual(slow.canonical_signature, fast.canonical_signature)
        self.assertEqual("SIGMA", slow.variable)

    def test_interface_range_scaling_removes_input_output_units(self) -> None:
        volts = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (2,), (1,)),
            normalization(input_bounds=(0.0, 10.0), output_bounds=(0.0, 20.0)),
        )
        millivolts = canonicalize_transfer_function(
            LinearTransferFunction("continuous", ("0.002",), (1,)),
            normalization(input_bounds=(0.0, 10000.0), output_bounds=(0.0, 20.0)),
        )
        self.assertEqual(volts.canonical_signature, millivolts.canonical_signature)
        self.assertEqual((1,), tuple(value.numerator for value in volts.numerator))

    def test_exact_and_approximate_evidence_do_not_share_signature(self) -> None:
        exact = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1,), (1, 1)),
            normalization(),
        )
        approximate = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1,), (1, 1)),
            normalization(bound_kind="OBSERVED_BOUND"),
        )
        self.assertEqual("EXACT_LINEAR_DYNAMICS", exact.dynamic_strength)
        self.assertEqual("APPROXIMATE_LINEAR_DYNAMICS", approximate.dynamic_strength)
        self.assertNotEqual(exact.canonical_signature, approximate.canonical_signature)

    def test_zero_transfer_has_unique_order_zero_form(self) -> None:
        result = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (0, 0), (1, 2, 1)),
            normalization(),
        )
        self.assertEqual((0,), tuple(value.numerator for value in result.numerator))
        self.assertEqual((1,), tuple(value.numerator for value in result.denominator))
        self.assertEqual(0, result.dynamic_order)
        self.assertTrue(result.proper)

    def test_improper_transfer_is_retained_with_warning(self) -> None:
        result = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1, 0), (1,)),
            normalization(),
        )
        self.assertFalse(result.proper)
        self.assertEqual(-1, result.relative_degree)
        self.assertTrue(result.warnings)

    def test_zero_and_nonfinite_denominators_fail_closed(self) -> None:
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("continuous", (1,), (0, 0)),
                normalization(),
            )
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("continuous", (1,), (1, math.inf)),
                normalization(),
            )


class DiscreteDynamicsTests(unittest.TestCase):
    def test_discrete_signature_contains_dimensionless_sample_interval(self) -> None:
        first = canonicalize_transfer_function(
            LinearTransferFunction("discrete", (1,), (1, "-0.5"), sample_period="0.01"),
            normalization(characteristic_time=0.1),
        )
        second = canonicalize_transfer_function(
            LinearTransferFunction("z", (1,), (1, "-0.5"), sample_period="0.1"),
            normalization(characteristic_time=1.0),
        )
        self.assertEqual("Z", first.variable)
        self.assertEqual(first.canonical_signature, second.canonical_signature)
        self.assertEqual((1, 10), (
            first.normalized_sample_interval.numerator,
            first.normalized_sample_interval.denominator,
        ))

    def test_float_sample_period_downgrades_dynamic_strength(self) -> None:
        result = canonicalize_transfer_function(
            LinearTransferFunction("discrete", (1,), (1, "-0.5"), sample_period=0.01),
            normalization(characteristic_time=0.1),
        )
        self.assertEqual("APPROXIMATE_LINEAR_DYNAMICS", result.dynamic_strength)

    def test_discrete_requires_sample_period(self) -> None:
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("discrete", (1,), (1, "-0.5")),
                normalization(),
            )

    def test_continuous_and_discrete_forms_never_share_signature(self) -> None:
        continuous = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (1,), (1, 1)),
            normalization(),
        )
        discrete = canonicalize_transfer_function(
            LinearTransferFunction("discrete", (1,), (1, 1), sample_period="1"),
            normalization(),
        )
        self.assertNotEqual(continuous.canonical_signature, discrete.canonical_signature)


class StateSpaceCanonicalizationTests(unittest.TestCase):
    def test_first_order_state_space_matches_transfer_function(self) -> None:
        contract = normalization()
        state = canonicalize_state_space(
            LinearStateSpace("continuous", ((-1,),), (1,), (2,), 0),
            contract,
        )
        transfer = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (2,), (1, 1)),
            contract,
        )
        self.assertEqual(state.canonical_signature, transfer.canonical_signature)

    def test_state_similarity_scaling_preserves_transfer_signature(self) -> None:
        contract = normalization()
        original = canonicalize_state_space(
            LinearStateSpace("continuous", ((-1,),), (1,), (2,), 0),
            contract,
        )
        scaled_state = canonicalize_state_space(
            LinearStateSpace("continuous", ((-1,),), (3,), ("2/3",), 0),
            contract,
        )
        self.assertEqual(original.canonical_signature, scaled_state.canonical_signature)

    def test_exact_unobservable_mode_is_removed_by_transfer_reduction(self) -> None:
        contract = normalization()
        nonminimal = canonicalize_state_space(
            LinearStateSpace(
                "continuous",
                ((-1, 0), (0, -2)),
                (1, 0),
                (2, 0),
                0,
            ),
            contract,
        )
        minimal = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (2,), (1, 1)),
            contract,
        )
        self.assertEqual(1, nonminimal.dynamic_order)
        self.assertIn("EXACT_COMMON_FACTOR_CANCELLATION", nonminimal.reductions)
        self.assertEqual(nonminimal.canonical_signature, minimal.canonical_signature)

    def test_column_b_and_row_c_are_accepted(self) -> None:
        result = canonicalize_state_space(
            LinearStateSpace("continuous", ((-1,),), ((1,),), ((2,),), 0),
            normalization(),
        )
        self.assertEqual(1, result.dynamic_order)

    def test_non_square_and_oversized_state_space_fail_closed(self) -> None:
        with self.assertRaises(EGCFError):
            canonicalize_state_space(
                LinearStateSpace("continuous", ((1, 0),), (1,), (1,), 0),
                normalization(),
            )
        oversized = tuple(
            tuple(1 if row == column else 0 for column in range(MAX_STATE_ORDER + 1))
            for row in range(MAX_STATE_ORDER + 1)
        )
        with self.assertRaises(EGCFError):
            canonicalize_state_space(
                LinearStateSpace(
                    "continuous",
                    oversized,
                    tuple(0 for _ in range(MAX_STATE_ORDER + 1)),
                    tuple(0 for _ in range(MAX_STATE_ORDER + 1)),
                    0,
                ),
                normalization(),
            )


class SAA3BoundaryTests(unittest.TestCase):
    def test_characteristic_time_is_required(self) -> None:
        spec = structure_from_mapping(siso_mapping())
        contract = build_normalization_contract(
            spec,
            input_bounds={0: [0.0, 1.0]},
            output_bounds={0: [0.0, 1.0]},
        )
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("continuous", (1,), (1, 1)),
                contract,
            )

    def test_mimo_contract_fails_closed(self) -> None:
        mapping = mimo_mapping()
        contract = normalization(mapping=mapping)
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("continuous", (1,), (1, 1)),
                contract,
            )

    def test_integer_coordinates_fail_closed(self) -> None:
        mapping = siso_mapping(input_type="integer")
        contract = normalization(mapping=mapping)
        with self.assertRaises(EGCFError):
            canonicalize_transfer_function(
                LinearTransferFunction("continuous", (1,), (1, 1)),
                contract,
            )

    def test_combined_signature_binds_structure_normalization_and_dynamics(self) -> None:
        mapping = siso_mapping(input_name="voltage", output_name="speed")
        structural = canonicalize_mapping(mapping)
        contract = normalization(mapping=mapping)
        dynamics = canonicalize_transfer_function(
            LinearTransferFunction("continuous", (2,), (1, 1)),
            contract,
        )
        signature = dynamic_algorithm_signature(structural, contract, dynamics)
        self.assertEqual(64, len(signature))

        incompatible_contract = normalization(
            mapping=mapping,
            bound_kind="OBSERVED_BOUND",
        )
        with self.assertRaises(EGCFError):
            dynamic_algorithm_signature(structural, incompatible_contract, dynamics)


if __name__ == "__main__":
    unittest.main()
