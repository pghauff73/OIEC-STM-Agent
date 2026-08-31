"""Regression tests for repository-owned acronym expansions."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CanonicalAcronymTests(unittest.TestCase):
    def test_registry_uses_owner_declared_expansions(self) -> None:
        text = (ROOT / "tools" / "docs_learning_catalog.py").read_text(encoding="utf-8")
        self.assertIn('AcronymRecord("STM", "State Transition Machine"', text)
        self.assertIn('AcronymRecord("OURD", "Orthogonal Unique Relational Decomposition"', text)
        self.assertNotIn("Object Unique Relational Decomposition", text)
        self.assertNotIn("Object-Universe-Relation-Dependency", text)

    def test_reader_glossary_matches_registry(self) -> None:
        text = (ROOT / "docs" / "ACRONYM_GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn("State Transition Machine", text)
        self.assertIn("Orthogonal Unique Relational Decomposition", text)
        self.assertNotIn("Object Unique Relational Decomposition", text)
        self.assertNotIn("Object-Universe-Relation-Dependency", text)


if __name__ == "__main__":
    unittest.main()
