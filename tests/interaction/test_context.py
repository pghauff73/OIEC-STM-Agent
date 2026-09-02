from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import resolve_context
from ourd.workspace import Workspace


class ContextResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_resolves_file_folder_and_prospective_path(self) -> None:
        context = resolve_context(
            "inspect @file[README.md] @folder[docs] @path[src/new.py]",
            self.workspace,
        )
        statuses = {(item.kind, item.value): item.status for item in context.references}
        self.assertEqual("resolved", statuses[("file", "README.md")])
        self.assertEqual("resolved", statuses[("folder", "docs")])
        self.assertEqual("prospective", statuses[("path", "src/new.py")])
        self.assertEqual(("README.md", "docs", "src/new.py"), context.target_paths)

    def test_shorthand_and_quoted_paths_are_supported(self) -> None:
        context = resolve_context(
            'inspect @README.md "@docs/my file.md" !constraint:read-only',
            self.workspace,
        )
        self.assertEqual(("README.md", "docs/my file.md"), context.target_paths)
        self.assertEqual(("read-only",), context.constraints)

    def test_bare_missing_paths_and_globs_remain_context_targets(self) -> None:
        context = resolve_context(
            "summarise docs/does-not-exist/ and docs/__no_match__*.md",
            self.workspace,
        )
        statuses = {(item.kind, item.value): item.status for item in context.references}
        self.assertEqual("unresolved", statuses[("folder", "docs/does-not-exist")])
        self.assertEqual("prospective", statuses[("path", "docs/__no_match__*.md")])
        self.assertEqual(("docs/__no_match__*.md", "docs/does-not-exist"), context.target_paths)
        self.assertTrue(context.has_unresolved_references)

    def test_workspace_escape_is_rejected(self) -> None:
        with self.assertRaisesRegex(PolicyError, "escapes workspace"):
            resolve_context("inspect @path[../secret.txt]", self.workspace)

    def test_evidence_status_uses_known_registry(self) -> None:
        context = resolve_context(
            "compare #evidence[known] #evidence[missing]",
            self.workspace,
            known_evidence_ids=("known",),
        )
        statuses = {item.value: item.status for item in context.references}
        self.assertEqual("resolved", statuses["known"])
        self.assertEqual("unresolved", statuses["missing"])
        self.assertTrue(context.has_unresolved_references)

    def test_evidence_is_unverified_when_registry_is_not_supplied(self) -> None:
        context = resolve_context("explain #evidence:artifact-1", self.workspace)
        self.assertEqual("unverified", context.references[0].status)
        self.assertFalse(context.has_unresolved_references)


if __name__ == "__main__":
    unittest.main()
