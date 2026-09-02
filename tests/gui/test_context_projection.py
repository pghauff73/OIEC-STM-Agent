from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ourd.interaction import (
    build_context_envelope,
    compare_context_envelopes,
    route_interaction,
)
from ourd.workspace import Workspace
from ourd_gui.context_projection import (
    context_delta_audit_metadata,
    context_delta_projection,
    context_envelope_audit_metadata,
    context_envelope_projection,
)


class ContextProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "a.txt").write_text("SENSITIVE-PREVIEW-BODY\n", encoding="utf-8")
        (self.root / "b.txt").write_text("second\n", encoding="utf-8")
        self.workspace = Workspace(self.root)
        route = route_interaction(
            "inspect @file[a.txt] @file[b.txt] !constraint[read-only]",
            self.workspace,
        )
        self.envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_preview_bodies_are_redacted_by_default(self) -> None:
        projection = context_envelope_projection(self.envelope)
        serialized = json.dumps(projection, sort_keys=True)
        self.assertNotIn("SENSITIVE-PREVIEW-BODY", serialized)
        self.assertTrue(projection["files"][0]["preview_redacted"])
        self.assertFalse(projection["preview_text_included"])
        self.assertFalse(projection["model_input_included"])

    def test_reveal_uses_same_exact_inspector_identity(self) -> None:
        redacted = context_envelope_projection(self.envelope)
        revealed = context_envelope_projection(
            self.envelope,
            include_preview_text=True,
        )
        self.assertEqual(
            redacted["inspector_signature"],
            revealed["inspector_signature"],
        )
        self.assertEqual("SENSITIVE-PREVIEW-BODY\n", revealed["files"][0]["preview_text"])
        self.assertFalse(revealed["files"][0]["preview_redacted"])

    def test_rows_are_bounded_and_omissions_are_explicit(self) -> None:
        projection = context_envelope_projection(
            self.envelope,
            max_attachments=1,
            max_files=1,
        )
        self.assertEqual(1, len(projection["attachments"]))
        self.assertEqual(2, projection["omitted_attachment_count"])
        self.assertEqual(1, len(projection["files"]))
        self.assertEqual(1, projection["omitted_file_count"])

    def test_projection_preserves_exact_envelope_metadata(self) -> None:
        projection = context_envelope_projection(self.envelope)
        self.assertEqual(self.envelope.envelope_id, projection["envelope_id"])
        self.assertEqual(self.envelope.signature, projection["envelope_signature"])
        self.assertEqual(
            self.envelope.source_snapshot_hash,
            projection["source_snapshot_hash"],
        )
        self.assertEqual(self.envelope.budget.signature, projection["budget"]["signature"])

    def test_audit_metadata_never_contains_preview_or_prompt_bodies(self) -> None:
        metadata = context_envelope_audit_metadata(self.envelope)
        serialized = json.dumps(metadata, sort_keys=True)
        self.assertNotIn("SENSITIVE-PREVIEW-BODY", serialized)
        self.assertNotIn(self.envelope.original_request, serialized)
        self.assertNotIn("a.txt", serialized)
        self.assertFalse(metadata["context_preview_bodies_persisted"])

    def test_context_delta_projection_is_body_free(self) -> None:
        baseline = self.envelope
        (self.root / "a.txt").write_text("CHANGED-SENSITIVE-BODY\n", encoding="utf-8")
        route = route_interaction(
            "inspect @file[a.txt] @file[b.txt] !constraint[read-only]",
            self.workspace,
        )
        observed = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        delta = compare_context_envelopes(baseline, observed)
        projection = context_delta_projection(delta)
        metadata = context_delta_audit_metadata(delta)
        serialized = json.dumps({"projection": projection, "metadata": metadata})
        self.assertEqual("STALE", projection["freshness"])
        self.assertEqual(1, projection["counts"]["changed"])
        self.assertNotIn("CHANGED-SENSITIVE-BODY", serialized)
        self.assertFalse(metadata["context_preview_bodies_persisted"])


if __name__ == "__main__":
    unittest.main()
