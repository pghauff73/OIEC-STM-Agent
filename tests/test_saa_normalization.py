from __future__ import annotations

import math
import unittest

from ourd.egcf.algebra import canonicalize_mapping
from ourd.egcf.algebra.normalize import (
    NumericBound,
    TimeNormalization,
    build_normalization_contract,
    denormalize_role,
    denormalize_time,
    denormalize_value,
    normalize_role,
    normalize_time,
    normalize_value,
    normalized_algorithm_signature,
)
from ourd.egcf.algebra.ir import structure_from_mapping
from ourd.egcf.errors import EGCFError


def bounded_binary(*, primitive: str = "ADD", names=("left", "right"), reverse=False):
    operands = [{"input": 0}, {"input": 1}]
    if reverse:
        operands.reverse()
    return {
        "name": "bounded-binary",
        "inputs": [
            {"position": 0, "name": names[0], "data_type": "scalar"},
            {"position": 1, "name": names[1], "data_type": "scalar"},
        ],
        "outputs": [
            {
                "position": 0,
                "name": "answer",
                "data_type": "scalar",
                "source": {"node": "combine"},
            }
        ],
        "nodes": [
            {
                "id": "combine",
                "primitive": primitive,
                "operands": operands,
            }
        ],
        "entry_nodes": ["combine"],
    }


class NumericBoundTests(unittest.TestCase):
    def test_endpoints_and_midpoint_map_to_unit_interval(self) -> None:
        bound = NumericBound(-20.0, 80.0)
        self.assertEqual(0.0, normalize_value(bound, -20.0))
        self.assertEqual(0.5, normalize_value(bound, 30.0))
        self.assertEqual(1.0, normalize_value(bound, 80.0))

    def test_affine_normalization_is_reversible(self) -> None:
        bound = NumericBound(10.0, 70.0)
        for value in (10.0, 13.25, 40.0, 69.5, 70.0):
            self.assertAlmostEqual(
                value,
                denormalize_value(bound, normalize_value(bound, value)),
                places=12,
            )

    def test_source_values_are_not_silently_clipped(self) -> None:
        bound = NumericBound(0.0, 1.0)
        with self.assertRaises(EGCFError):
            normalize_value(bound, -0.0001)
        with self.assertRaises(EGCFError):
            normalize_value(bound, 1.0001)

    def test_inverse_rejects_out_of_range_normalized_values(self) -> None:
        bound = NumericBound(0.0, 100.0)
        with self.assertRaises(EGCFError):
            denormalize_value(bound, -0.1)
        with self.assertRaises(EGCFError):
            denormalize_value(bound, 1.1)

    def test_invalid_and_nonfinite_bounds_fail_closed(self) -> None:
        with self.assertRaises(EGCFError):
            NumericBound(1.0, 1.0)
        with self.assertRaises(EGCFError):
            NumericBound(2.0, 1.0)
        with self.assertRaises(EGCFError):
            NumericBound(0.0, math.inf)
        with self.assertRaises(EGCFError):
            NumericBound(math.nan, 1.0)

    def test_nonfinite_values_fail_closed(self) -> None:
        bound = NumericBound(0.0, 1.0)
        with self.assertRaises(EGCFError):
            normalize_value(bound, math.nan)
        with self.assertRaises(EGCFError):
            denormalize_value(bound, math.inf)


class NormalizationContractTests(unittest.TestCase):
    def structure(self):
        return structure_from_mapping(bounded_binary())

    def contract(self, *, scale=1.0, unit="", kind="EXACT_BOUND", time=None):
        return build_normalization_contract(
            self.structure(),
            input_bounds={
                0: {
                    "minimum": -10.0 * scale,
                    "maximum": 10.0 * scale,
                    "kind": kind,
                    "unit": unit,
                    "provenance": {"source": "test"},
                },
                1: {
                    "minimum": 0.0,
                    "maximum": 20.0 * scale,
                    "kind": kind,
                    "unit": unit,
                },
            },
            output_bounds={
                0: {
                    "minimum": -10.0 * scale,
                    "maximum": 30.0 * scale,
                    "kind": kind,
                    "unit": unit,
                }
            },
            time=time,
        )

    def test_exact_rescaling_changes_audit_hash_not_canonical_signature(self) -> None:
        first = self.contract(scale=1.0, unit="V")
        second = self.contract(scale=1000.0, unit="mV")
        self.assertEqual("EXACT_NORMALIZATION", first.normalization_strength)
        self.assertEqual(first.canonical_signature, second.canonical_signature)
        self.assertNotEqual(first.contract_hash, second.contract_hash)

    def test_unit_and_provenance_are_audited_but_not_equivalence_identity(self) -> None:
        first = self.contract(unit="metre")
        second = self.contract(unit="millimetre")
        self.assertEqual(first.canonical_signature, second.canonical_signature)
        self.assertNotEqual(first.contract_hash, second.contract_hash)

    def test_approximate_bounds_downgrade_strength_and_signature(self) -> None:
        exact = self.contract(kind="EXACT_BOUND")
        observed = self.contract(kind="OBSERVED_BOUND")
        self.assertEqual("EXACT_NORMALIZATION", exact.normalization_strength)
        self.assertEqual("APPROXIMATE_NORMALIZATION", observed.normalization_strength)
        self.assertNotEqual(exact.canonical_signature, observed.canonical_signature)
        self.assertTrue(observed.warnings)

    def test_domain_bound_is_exact_strength(self) -> None:
        exact = self.contract(kind="EXACT_BOUND")
        domain = self.contract(kind="DOMAIN_BOUND")
        self.assertEqual("EXACT_NORMALIZATION", domain.normalization_strength)
        self.assertEqual(exact.canonical_signature, domain.canonical_signature)

    def test_mapping_order_does_not_change_contract_identity(self) -> None:
        spec = self.structure()
        first = build_normalization_contract(
            spec,
            input_bounds={0: [0.0, 1.0], 1: [10.0, 20.0]},
            output_bounds={0: [5.0, 25.0]},
        )
        second = build_normalization_contract(
            spec,
            input_bounds={1: [10.0, 20.0], 0: [0.0, 1.0]},
            output_bounds={0: [5.0, 25.0]},
        )
        self.assertEqual(first.contract_hash, second.contract_hash)
        self.assertEqual(first.canonical_signature, second.canonical_signature)

    def test_missing_and_extra_bindings_fail_closed(self) -> None:
        spec = self.structure()
        with self.assertRaises(EGCFError):
            build_normalization_contract(
                spec,
                input_bounds={0: [0.0, 1.0]},
                output_bounds={0: [0.0, 1.0]},
            )
        with self.assertRaises(EGCFError):
            build_normalization_contract(
                spec,
                input_bounds={0: [0.0, 1.0], 1: [0.0, 1.0], 3: [0.0, 1.0]},
                output_bounds={0: [0.0, 1.0]},
            )

    def test_vector_ports_fail_closed_in_saa2(self) -> None:
        payload = bounded_binary()
        payload["inputs"][0]["shape"] = [2]
        spec = structure_from_mapping(payload)
        with self.assertRaises(EGCFError):
            build_normalization_contract(
                spec,
                input_bounds={0: [0.0, 1.0], 1: [0.0, 1.0]},
                output_bounds={0: [0.0, 1.0]},
            )

    def test_role_vectors_normalize_and_denormalize_positionally(self) -> None:
        contract = self.contract()
        normalized = normalize_role(contract, "INPUT", (-10.0, 10.0))
        self.assertEqual((0.0, 0.5), normalized)
        self.assertEqual((-10.0, 10.0), denormalize_role(contract, "INPUT", normalized))

    def test_time_is_dimensionless_and_reversible(self) -> None:
        time = TimeNormalization(
            characteristic_time=0.25,
            kind="EXACT_BOUND",
            unit="s",
            provenance=(("source", "model"),),
        )
        self.assertEqual(4.0, normalize_time(time, 1.0))
        self.assertEqual(1.0, denormalize_time(time, 4.0))

    def test_exact_time_scale_changes_audit_hash_not_canonical_signature(self) -> None:
        first = self.contract(time={"characteristic_time": 1.0, "unit": "s"})
        second = self.contract(time={"characteristic_time": 0.001, "unit": "ms"})
        self.assertEqual(first.canonical_signature, second.canonical_signature)
        self.assertNotEqual(first.contract_hash, second.contract_hash)

    def test_invalid_characteristic_time_fails_closed(self) -> None:
        with self.assertRaises(EGCFError):
            TimeNormalization(0.0)
        with self.assertRaises(EGCFError):
            TimeNormalization(math.inf)


class NormalizedAlgorithmIdentityTests(unittest.TestCase):
    def test_renamed_and_rescaled_algorithms_have_same_normalized_signature(self) -> None:
        first_mapping = bounded_binary(names=("temperature", "pressure"))
        second_mapping = bounded_binary(names=("x", "y"))
        first_ir = canonicalize_mapping(first_mapping)
        second_ir = canonicalize_mapping(second_mapping)
        first_contract = build_normalization_contract(
            structure_from_mapping(first_mapping),
            input_bounds={0: [-20.0, 80.0], 1: [100.0, 200.0]},
            output_bounds={0: [80.0, 280.0]},
        )
        second_contract = build_normalization_contract(
            structure_from_mapping(second_mapping),
            input_bounds={0: [0.0, 1000.0], 1: [-1.0, 1.0]},
            output_bounds={0: [-500.0, 500.0]},
        )
        self.assertEqual(first_ir.structural_hash, second_ir.structural_hash)
        self.assertEqual(first_contract.canonical_signature, second_contract.canonical_signature)
        self.assertEqual(
            normalized_algorithm_signature(first_ir, first_contract),
            normalized_algorithm_signature(second_ir, second_contract),
        )

    def test_structural_difference_survives_normalization(self) -> None:
        first_mapping = bounded_binary(primitive="ADD")
        second_mapping = bounded_binary(primitive="SUBTRACT")
        first_ir = canonicalize_mapping(first_mapping)
        second_ir = canonicalize_mapping(second_mapping)
        first_contract = build_normalization_contract(
            structure_from_mapping(first_mapping),
            input_bounds={0: [0.0, 1.0], 1: [0.0, 1.0]},
            output_bounds={0: [-1.0, 2.0]},
        )
        second_contract = build_normalization_contract(
            structure_from_mapping(second_mapping),
            input_bounds={0: [0.0, 1.0], 1: [0.0, 1.0]},
            output_bounds={0: [-1.0, 2.0]},
        )
        self.assertNotEqual(first_ir.structural_hash, second_ir.structural_hash)
        self.assertNotEqual(
            normalized_algorithm_signature(first_ir, first_contract),
            normalized_algorithm_signature(second_ir, second_contract),
        )


if __name__ == "__main__":
    unittest.main()
