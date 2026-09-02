from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_completion_inventory import (
    PLAN_FILES,
    build_inventory,
    extract_requirements,
    git_candidate_paths,
    requirement_identity,
)


class CompletionInventoryTests(unittest.TestCase):
    def test_requirement_identity_deduplicates_equivalent_formatting(self) -> None:
        self.assertEqual(
            requirement_identity("**Run tests.**"),
            requirement_identity("Run   tests"),
        )

    def test_extraction_preserves_line_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary) / "PLAN.md"
            plan.write_text(
                "## Phase P1 — Example\n\n1. First requirement.\n2. Second requirement.\n",
                encoding="utf-8",
            )
            rows = extract_requirements(plan)
        texts = {row.requirement_text: row.source_line for row in rows}
        self.assertEqual(1, texts["Phase P1 — Example"])
        self.assertEqual(3, texts["First requirement"])
        self.assertEqual(4, texts["Second requirement"])

    def test_repository_inventory_is_deterministic_and_complete(self) -> None:
        root = Path(__file__).resolve().parents[1]
        first_manifest, first = build_inventory(root)
        second_manifest, second = build_inventory(root)
        self.assertEqual(first_manifest["tree_hash"], second_manifest["tree_hash"])
        self.assertEqual(first["signature"], second["signature"])
        self.assertGreater(first["requirement_count"], 500)
        self.assertEqual(set(PLAN_FILES), set(first["plan_hashes"]))
        for row in first["requirements"]:
            self.assertTrue(row["requirement_id"].startswith("REQ-"))
            self.assertTrue(row["canonical_owner"])
            self.assertTrue(row["implementation_paths"])
            self.assertTrue(row["test_or_evidence_owner"])
            self.assertEqual(first_manifest["tree_hash"], row["last_verified_source_hash"])

    def test_source_manifest_excludes_generated_reports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertFalse(
            any(path.startswith("reports/") for path in git_candidate_paths(root))
        )


if __name__ == "__main__":
    unittest.main()
