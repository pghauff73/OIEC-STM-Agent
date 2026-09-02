from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import (
    MAX_PINNED_CONTEXT_PATHS,
    PinnedContextSet,
    build_pinned_context_envelope,
)
from ourd.workspace import Workspace


class PinnedContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_add_is_canonical_order_independent_and_content_addressed(self) -> None:
        first = PinnedContextSet().add(self.workspace, ("docs", "README.md"))
        second = PinnedContextSet().add(self.workspace, ("README.md", "docs"))
        self.assertEqual(("README.md", "docs"), first.paths)
        self.assertEqual(first.context_id, second.context_id)
        self.assertEqual(first.signature, second.signature)

    def test_apply_adds_only_missing_references_and_skips_commands(self) -> None:
        context = PinnedContextSet().add(self.workspace, ("README.md", "docs"))
        applied = context.apply_to("inspect @path[README.md]", self.workspace)
        self.assertEqual("inspect @path[README.md] @path[docs]", applied)
        self.assertEqual("/status", context.apply_to("/status", self.workspace))

    def test_remove_and_clear_create_new_exact_states(self) -> None:
        context = PinnedContextSet().add(self.workspace, ("README.md", "docs"))
        removed = context.remove(self.workspace, ("docs",))
        self.assertEqual(("README.md",), removed.paths)
        self.assertEqual((), removed.clear().paths)
        self.assertNotEqual(context.signature, removed.signature)

    def test_workspace_escape_fails_closed(self) -> None:
        with self.assertRaisesRegex(PolicyError, "escapes workspace"):
            PinnedContextSet().add(self.workspace, ("../secret",))

    def test_path_count_is_hard_bounded(self) -> None:
        paths = tuple(f"path-{index}" for index in range(MAX_PINNED_CONTEXT_PATHS + 1))
        with self.assertRaisesRegex(PolicyError, "exceeds"):
            PinnedContextSet().add(self.workspace, paths)

    def test_unrepresentable_bracket_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            PinnedContextSet(paths=("bad]path",))

    def test_shared_draft_envelope_binds_every_pinned_path(self) -> None:
        context = PinnedContextSet().add(self.workspace, ("README.md", "docs"))
        envelope = build_pinned_context_envelope(
            context,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        assert envelope is not None
        self.assertEqual(set(context.paths), {item.value for item in envelope.attachments})

    def test_empty_pinned_context_has_no_draft_envelope(self) -> None:
        self.assertIsNone(
            build_pinned_context_envelope(
                PinnedContextSet(),
                self.workspace,
                source_snapshot_hash=self.workspace.snapshot_hash(),
            )
        )


if __name__ == "__main__":
    unittest.main()
