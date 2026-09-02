from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import (
    ContextProjectionBudget,
    InteractionContextEnvelope,
    build_context_envelope,
    route_interaction,
)
from ourd.workspace import Workspace


class ContextEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("alpha\nbeta\n", encoding="utf-8")
        (self.root / "binary.bin").write_bytes(b"\x00\x01\x02")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.txt").write_text("A\n", encoding="utf-8")
        (self.root / "docs" / "b.txt").write_text("B\n", encoding="utf-8")
        (self.root / "docs" / "c.txt").write_text("C\n", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, text: str, *, budget: ContextProjectionBudget | None = None):
        route = route_interaction(text, self.workspace)
        return build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
            budget=budget,
        )

    def test_text_file_projection_is_hashed_and_previewed(self) -> None:
        envelope = self.build("inspect @file[README.md]")
        self.assertEqual(1, len(envelope.files))
        projection = envelope.files[0]
        self.assertEqual("README.md", projection.path)
        self.assertEqual("exact", projection.hash_status)
        self.assertEqual("text", projection.preview_kind)
        self.assertEqual("alpha\nbeta\n", projection.preview_text)
        self.assertIn("[CONTROL BOUNDARY]", envelope.model_input)
        self.assertIn("does not grant authority", envelope.model_input)

    def test_binary_preview_is_omitted_but_counted(self) -> None:
        envelope = self.build("inspect @file[binary.bin]")
        projection = envelope.files[0]
        self.assertEqual("binary", projection.preview_kind)
        self.assertEqual("", projection.preview_text)
        self.assertEqual(3, projection.preview_bytes)

    def test_folder_projection_is_bounded_and_explicitly_truncated(self) -> None:
        envelope = self.build(
            "inspect @folder[docs]",
            budget=ContextProjectionBudget(max_files_per_folder=2),
        )
        self.assertEqual(("docs/a.txt", "docs/b.txt"), tuple(item.path for item in envelope.files))
        self.assertTrue(envelope.attachments[0].truncated)
        self.assertIn("limited to 2 files", envelope.attachments[0].note)

    def test_prospective_path_has_no_invented_content(self) -> None:
        envelope = self.build("plan @path[src/new.py]")
        self.assertEqual((), envelope.files)
        self.assertEqual("prospective", envelope.attachments[0].status)
        self.assertIn("no current file content", envelope.attachments[0].note)

    def test_reference_overflow_fails_closed(self) -> None:
        budget = ContextProjectionBudget(max_references=1)
        with self.assertRaisesRegex(PolicyError, "reference budget exceeded"):
            self.build(
                "inspect @file[README.md] @file[binary.bin]",
                budget=budget,
            )

    def test_preview_budget_is_global_and_bounded(self) -> None:
        envelope = self.build(
            "inspect @folder[docs]",
            budget=ContextProjectionBudget(
                max_preview_bytes_per_file=2,
                max_total_preview_bytes=2,
            ),
        )
        self.assertEqual(2, envelope.total_preview_bytes)
        self.assertEqual("text", envelope.files[0].preview_kind)
        self.assertTrue(all(item.preview_kind == "omitted_budget" for item in envelope.files[1:]))

    def test_envelope_identity_changes_with_source_content(self) -> None:
        first = self.build("inspect @file[README.md]")
        restored = InteractionContextEnvelope.from_dict(
            {
                **first.__dict__,
                "budget": first.budget.__dict__,
                "attachments": [item.__dict__ for item in first.attachments],
                "files": [item.__dict__ for item in first.files],
            }
        )
        self.assertEqual(first.signature, restored.signature)
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        second = self.build("inspect @file[README.md]")
        self.assertNotEqual(first.envelope_id, second.envelope_id)

    def test_identical_inputs_have_identical_envelopes(self) -> None:
        first = self.build("inspect @file[README.md]")
        second = self.build("inspect @file[README.md]")
        self.assertEqual(first.envelope_id, second.envelope_id)
        self.assertEqual(first.signature, second.signature)

    def test_stale_source_snapshot_is_rejected(self) -> None:
        route = route_interaction("inspect @file[README.md]", self.workspace)
        with self.assertRaisesRegex(PolicyError, "source snapshot mismatch"):
            build_context_envelope(
                route,
                self.workspace,
                source_snapshot_hash="0" * 64,
            )

    def test_wide_directory_fails_closed_before_unbounded_projection(self) -> None:
        route = route_interaction("inspect @folder[docs]", self.workspace)
        with self.assertRaisesRegex(PolicyError, "directory entry budget exceeded"):
            build_context_envelope(
                route,
                self.workspace,
                source_snapshot_hash=self.workspace.snapshot_hash(),
                budget=ContextProjectionBudget(max_directory_entries=2),
            )


if __name__ == "__main__":
    unittest.main()
