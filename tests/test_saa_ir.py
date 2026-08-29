from __future__ import annotations

import unittest

from ourd.egcf.algebra import canonicalize_mapping, normalize_primitive
from ourd.egcf.errors import EGCFError


def binary_algorithm(*, name_a="left", name_b="right", node_id="combine", primitive="ADD", reverse=False):
    operands = [{"input": 0}, {"input": 1}]
    if reverse:
        operands.reverse()
    return {
        "name": "display-only-name",
        "inputs": [
            {"position": 0, "name": name_a},
            {"position": 1, "name": name_b},
        ],
        "outputs": [
            {"position": 0, "name": "answer", "source": {"node": node_id}},
        ],
        "nodes": [
            {
                "id": node_id,
                "primitive": primitive,
                "operands": operands,
                "attributes": {
                    "display_name": "ignored source label",
                    "description": "ignored documentation",
                },
            }
        ],
        "entry_nodes": [node_id],
    }


def branch_algorithm(*, swapped=False, termination="normal"):
    true_target = "reject" if swapped else "accept"
    false_target = "accept" if swapped else "reject"
    return {
        "name": "branch-example",
        "inputs": [{"position": 0, "name": "score"}],
        "outputs": [
            {"position": 0, "source": {"node": "predicate"}},
        ],
        "nodes": [
            {
                "id": "predicate",
                "primitive": "COMPARE_GT",
                "operands": [{"input": 0}, {"constant": 0.5}],
            },
            {
                "id": "decision",
                "primitive": "BRANCH",
                "operands": [{"node": "predicate"}],
                "attributes": {"policy": "threshold"},
                "result_count": 0,
            },
            {
                "id": "accept",
                "primitive": "TERMINATE",
                "attributes": {"termination": termination, "outcome": "accept"},
                "result_count": 0,
            },
            {
                "id": "reject",
                "primitive": "TERMINATE",
                "attributes": {"termination": termination, "outcome": "reject"},
                "result_count": 0,
            },
        ],
        "control_edges": [
            {"from": "predicate", "to": "decision", "kind": "next"},
            {"from": "decision", "to": true_target, "kind": "true"},
            {"from": "decision", "to": false_target, "kind": "false"},
        ],
        "entry_nodes": ["predicate"],
        "termination_nodes": ["accept", "reject"],
    }


class CanonicalPrimitiveTests(unittest.TestCase):
    def test_aliases_normalize_to_fixed_vocabulary(self) -> None:
        self.assertEqual("ADD", normalize_primitive("+").name)
        self.assertEqual("MULTIPLY", normalize_primitive("mul").name)
        self.assertTrue(normalize_primitive("ADD").commutative)

    def test_unknown_primitive_fails_closed(self) -> None:
        with self.assertRaises(EGCFError):
            normalize_primitive("invented-operation")


class CanonicalIRTests(unittest.TestCase):
    def test_variable_and_node_renaming_preserve_identity(self) -> None:
        first = canonicalize_mapping(
            binary_algorithm(name_a="temperature", name_b="pressure", node_id="sum_inputs")
        )
        second = canonicalize_mapping(
            binary_algorithm(name_a="x", name_b="y", node_id="node_947")
        )
        self.assertEqual("EXACT_STRUCTURAL", first.canonicalization_strength)
        self.assertEqual(first.structural_hash, second.structural_hash)
        self.assertEqual(first.canonical_payload, second.canonical_payload)

    def test_commutative_operand_order_preserves_identity(self) -> None:
        first = canonicalize_mapping(binary_algorithm(primitive="ADD", reverse=False))
        second = canonicalize_mapping(binary_algorithm(primitive="ADD", reverse=True))
        self.assertEqual(first.structural_hash, second.structural_hash)

    def test_noncommutative_operand_order_changes_identity(self) -> None:
        first = canonicalize_mapping(binary_algorithm(primitive="SUBTRACT", reverse=False))
        second = canonicalize_mapping(binary_algorithm(primitive="SUBTRACT", reverse=True))
        self.assertNotEqual(first.structural_hash, second.structural_hash)

    def test_algorithm_and_display_metadata_do_not_affect_identity(self) -> None:
        first_payload = binary_algorithm()
        second_payload = binary_algorithm()
        first_payload["name"] = "verbose-human-title"
        second_payload["name"] = "A"
        first_payload["metadata"] = {"author": "one", "note": "display only"}
        second_payload["metadata"] = {"author": "two"}
        first_payload["nodes"][0]["attributes"]["description"] = "long description"
        second_payload["nodes"][0]["attributes"]["description"] = "different description"
        self.assertEqual(
            canonicalize_mapping(first_payload).structural_hash,
            canonicalize_mapping(second_payload).structural_hash,
        )

    def test_branch_direction_is_identity_bearing(self) -> None:
        first = canonicalize_mapping(branch_algorithm(swapped=False))
        second = canonicalize_mapping(branch_algorithm(swapped=True))
        self.assertNotEqual(first.structural_hash, second.structural_hash)

    def test_termination_semantics_are_identity_bearing(self) -> None:
        first = canonicalize_mapping(branch_algorithm(termination="converged"))
        second = canonicalize_mapping(branch_algorithm(termination="budget_exhausted"))
        self.assertNotEqual(first.structural_hash, second.structural_hash)

    def test_state_variable_names_do_not_affect_identity(self) -> None:
        def state_algorithm(state_name: str, update_id: str):
            return {
                "name": "stateful",
                "inputs": [{"position": 0, "name": "increment"}],
                "states": [
                    {
                        "position": 0,
                        "name": state_name,
                        "initial": {"constant": 0},
                        "update": {"node": update_id},
                    }
                ],
                "outputs": [{"position": 0, "source": {"node": update_id}}],
                "nodes": [
                    {
                        "id": update_id,
                        "primitive": "ADD",
                        "operands": [{"state": 0}, {"input": 0}],
                    }
                ],
                "entry_nodes": [update_id],
            }

        first = canonicalize_mapping(state_algorithm("accumulator", "advance"))
        second = canonicalize_mapping(state_algorithm("x", "n1"))
        self.assertEqual(first.structural_hash, second.structural_hash)

    def test_small_symmetric_graph_is_canonicalized_exactly(self) -> None:
        def symmetric(ids):
            left, right, combine = ids
            return {
                "name": "symmetric",
                "outputs": [{"position": 0, "source": {"node": combine}}],
                "nodes": [
                    {"id": left, "primitive": "CONST", "operands": [{"constant": 1}]},
                    {"id": right, "primitive": "CONST", "operands": [{"constant": 1}]},
                    {
                        "id": combine,
                        "primitive": "ADD",
                        "operands": [{"node": left}, {"node": right}],
                    },
                ],
            }

        first = canonicalize_mapping(symmetric(("a", "b", "c")))
        second = canonicalize_mapping(symmetric(("z", "x", "q")))
        self.assertEqual("EXACT_STRUCTURAL", first.canonicalization_strength)
        self.assertGreaterEqual(first.exact_permutations_considered, 2)
        self.assertEqual(first.structural_hash, second.structural_hash)

    def test_large_symmetry_downgrades_instead_of_claiming_exact_equivalence(self) -> None:
        nodes = [
            {"id": f"c{index}", "primitive": "CONST", "operands": [{"constant": 1}]}
            for index in range(5)
        ]
        nodes.append(
            {
                "id": "result",
                "primitive": "ADD",
                "operands": [{"node": "c0"}, {"node": "c1"}],
            }
        )
        result = canonicalize_mapping(
            {
                "name": "high-symmetry",
                "outputs": [{"position": 0, "source": {"node": "result"}}],
                "nodes": nodes,
            },
            max_exact_permutations=2,
        )
        self.assertEqual("REFINED_FINGERPRINT", result.canonicalization_strength)
        self.assertTrue(result.warnings)
        self.assertEqual(0, result.exact_permutations_considered)

    def test_unknown_mapping_fields_fail_closed(self) -> None:
        payload = binary_algorithm()
        payload["mystery"] = True
        with self.assertRaises(EGCFError):
            canonicalize_mapping(payload)

    def test_port_positions_must_be_contiguous(self) -> None:
        payload = binary_algorithm()
        payload["inputs"][1]["position"] = 3
        with self.assertRaises(EGCFError):
            canonicalize_mapping(payload)


if __name__ == "__main__":
    unittest.main()
