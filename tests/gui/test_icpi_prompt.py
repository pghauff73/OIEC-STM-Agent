from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.interaction import PinnedContextSet
from ourd.workspace import Workspace
from ourd_gui.icpi_prompt import (
    ICPICommandHistory,
    attachment_reference_text,
    command_suggestions,
    complete_slash_command,
    format_route_preview,
    format_pinned_route_preview,
    projection_surface,
)


class ICPICommandHistoryTests(unittest.TestCase):
    def test_history_is_bounded_and_collapses_consecutive_duplicates(self) -> None:
        history = ICPICommandHistory(maximum_entries=2)
        history.record("first")
        history.record("first")
        history.record("second")
        history.record("third")
        self.assertEqual(("second", "third"), history.entries)

    def test_history_restores_draft_after_navigation(self) -> None:
        history = ICPICommandHistory()
        history.record("first")
        history.record("second")
        self.assertEqual("second", history.previous("draft"))
        self.assertEqual("first", history.previous("second"))
        self.assertEqual("second", history.next("first"))
        self.assertEqual("draft", history.next("second"))


class ICPIPromptProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_slash_suggestions_are_prefix_filtered(self) -> None:
        suggestions = command_suggestions("/to")
        self.assertEqual(("/topology — show the reasoning topology",), suggestions)

    def test_context_suggestion_discloses_refresh_semantics(self) -> None:
        suggestions = command_suggestions("/context")
        self.assertEqual(1, len(suggestions))
        self.assertIn("explicitly refresh", suggestions[0])

    def test_attachment_reference_text_preserves_spaces_without_shell_parsing(self) -> None:
        self.assertEqual(
            "@path[docs/my file.md] @path[README.md]",
            attachment_reference_text(("docs/my file.md", "README.md")),
        )

    def test_attachment_reference_text_rejects_unrepresentable_bracket_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            attachment_reference_text(("docs/bad]name.md",))

    def test_context_command_maps_to_context_inspector(self) -> None:
        self.assertEqual("context", projection_surface("projection.context"))

    def test_tab_completion_replaces_only_the_command_prefix(self) -> None:
        self.assertEqual("/topology ", complete_slash_command("/to"))
        self.assertEqual("  /files docs", complete_slash_command("  /fi docs"))
        self.assertEqual("/files docs", complete_slash_command("/files docs"))
        self.assertEqual("inspect parser", complete_slash_command("inspect parser"))

    def test_partial_slash_prefix_is_not_reported_as_blocked(self) -> None:
        preview = format_route_preview("/to", self.workspace)
        self.assertIn("1 command suggestion", preview)
        self.assertNotIn("BLOCKED", preview)

    def test_preview_exposes_governed_route_and_confirmation(self) -> None:
        preview = format_route_preview("fix @README.md", self.workspace)
        self.assertIn("WRITE → agent.governed_candidate", preview)
        self.assertIn("confirmation required", preview)

    def test_pinned_preview_discloses_count_signature_and_route(self) -> None:
        pinned = PinnedContextSet().add(self.workspace, ("README.md",))
        preview = format_pinned_route_preview("inspect project", self.workspace, pinned)
        self.assertIn("PINNED 1", preview)
        self.assertIn(pinned.signature[:12], preview)
        self.assertIn("INSPECT → agent.read_only", preview)

    def test_preview_fails_closed_for_unsafe_path(self) -> None:
        preview = format_route_preview("inspect @path[../secret]", self.workspace)
        self.assertIn("BLOCKED", preview)
        self.assertIn("escapes workspace", preview)

    def test_projection_targets_map_to_existing_surfaces(self) -> None:
        self.assertEqual("repository", projection_surface("projection.files"))
        self.assertEqual("reasoning", projection_surface("projection.topology"))
        self.assertEqual("eon", projection_surface("projection.diff"))
        self.assertEqual("", projection_surface("unknown"))


if __name__ == "__main__":
    unittest.main()
