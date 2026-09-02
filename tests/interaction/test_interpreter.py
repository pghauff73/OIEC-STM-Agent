from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.interaction import interpret_natural_language
from ourd.workspace import Workspace


class NaturalLanguageInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "parser.py").write_text("pass\n", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_classifies_major_intent_modes(self) -> None:
        cases = {
            "inspect @parser.py": "INSPECT",
            "explain parser architecture": "EXPLAIN",
            "compare parser alternatives": "COMPARE",
            "create an implementation plan": "WRITE",
            "validate @parser.py": "TEST",
            "commit the accepted candidate": "EXECUTE",
            "rollback the failed transaction": "RECOVER",
            "export the reasoning report": "EXPORT",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, interpret_natural_language(text, self.workspace).mode)

    def test_non_execution_instruction_downgrades_to_proposal(self) -> None:
        intent = interpret_natural_language(
            "implement parser changes but do not execute @parser.py",
            self.workspace,
        )
        self.assertEqual("PROPOSE", intent.mode)
        self.assertEqual("L0", intent.proposed_risk)

    def test_unresolved_reference_requires_confirmation(self) -> None:
        intent = interpret_natural_language(
            "explain evidence #evidence[missing]",
            self.workspace,
            known_evidence_ids=("known",),
        )
        self.assertTrue(intent.requires_confirmation)
        self.assertGreaterEqual(intent.ambiguity_bp, 4_000)

    def test_vague_improvement_request_is_write_with_confirmation(self) -> None:
        intent = interpret_natural_language(
            "Make the documentation better.",
            self.workspace,
        )
        self.assertEqual("WRITE", intent.mode)
        self.assertTrue(intent.requires_confirmation)
        self.assertGreaterEqual(intent.ambiguity_bp, 3_500)

    def test_identical_inputs_have_identical_identity(self) -> None:
        first = interpret_natural_language("inspect @parser.py", self.workspace)
        second = interpret_natural_language("inspect @parser.py", self.workspace)
        self.assertEqual(first.intent_id, second.intent_id)
        self.assertEqual(first.signature, second.signature)


if __name__ == "__main__":
    unittest.main()
