from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.errors import PolicyError
from ourd.interaction import (
    ContextDelta,
    ContextProjectionBudget,
    PinnedContextSet,
    build_pinned_context_envelope,
    build_context_envelope,
    compare_context_envelopes,
    pinned_context_freshness,
    require_fresh_pinned_context,
    route_interaction,
)
from ourd.workspace import Workspace


class ContextFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.txt").write_text("alpha\n", encoding="utf-8")
        (self.root / "docs" / "b.txt").write_text("beta\n", encoding="utf-8")
        self.workspace = Workspace(self.root)
        self.pinned = PinnedContextSet().add(self.workspace, ("docs",))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def envelope(self, *, budget: ContextProjectionBudget | None = None):
        envelope = build_pinned_context_envelope(
            self.pinned,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
            budget=budget,
        )
        assert envelope is not None
        return envelope

    def test_identical_context_is_fresh_and_deterministic(self) -> None:
        envelope = self.envelope()
        first = compare_context_envelopes(envelope, envelope)
        second = compare_context_envelopes(envelope, envelope)
        self.assertEqual("FRESH", first.freshness)
        self.assertEqual(2, first.unchanged_count)
        self.assertEqual(first.signature, second.signature)
        restored = ContextDelta.from_dict(first.__dict__)
        self.assertEqual(first.signature, restored.signature)

    def test_tampered_delta_counts_fail_closed(self) -> None:
        envelope = self.envelope()
        delta = compare_context_envelopes(envelope, envelope)
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            ContextDelta.from_dict({**delta.__dict__, "unchanged_count": 99})

    def test_changed_missing_and_new_files_are_classified(self) -> None:
        baseline = self.envelope()
        (self.root / "docs" / "a.txt").write_text("changed\n", encoding="utf-8")
        (self.root / "docs" / "b.txt").unlink()
        (self.root / "docs" / "c.txt").write_text("new\n", encoding="utf-8")
        observed = self.envelope()
        delta = compare_context_envelopes(baseline, observed)
        statuses = {item.path: item.status for item in delta.files}
        self.assertEqual("changed", statuses["docs/a.txt"])
        self.assertEqual("missing", statuses["docs/b.txt"])
        self.assertEqual("new", statuses["docs/c.txt"])
        self.assertEqual("STALE", delta.freshness)
        self.assertTrue(delta.workspace_snapshot_changed)

    def test_unrelated_workspace_change_still_stales_exact_snapshot(self) -> None:
        baseline = self.envelope()
        (self.root / "unrelated.txt").write_text("outside pinned context\n", encoding="utf-8")
        observed = self.envelope()
        delta = compare_context_envelopes(baseline, observed)
        self.assertEqual("STALE", delta.freshness)
        self.assertEqual(2, delta.unchanged_count)
        self.assertEqual(0, delta.changed_count)

    def test_applied_refresh_preserves_delta_and_marks_active_state_fresh(self) -> None:
        baseline = self.envelope()
        (self.root / "docs" / "a.txt").write_text("changed\n", encoding="utf-8")
        observed = self.envelope()
        delta = compare_context_envelopes(
            baseline,
            observed,
            refresh_applied=True,
        )
        self.assertEqual("FRESH", delta.freshness)
        self.assertTrue(delta.refresh_applied)
        self.assertEqual(1, delta.changed_count)

    def test_omitted_hash_change_is_indeterminate_when_size_is_equal(self) -> None:
        budget = ContextProjectionBudget(max_hash_file_bytes=1)
        baseline = self.envelope(budget=budget)
        (self.root / "docs" / "a.txt").write_text("omega\n", encoding="utf-8")
        observed = self.envelope(budget=budget)
        delta = compare_context_envelopes(baseline, observed)
        statuses = {item.path: item.status for item in delta.files}
        self.assertEqual("indeterminate", statuses["docs/a.txt"])

    def test_pinned_freshness_states_are_explicit(self) -> None:
        current = self.workspace.snapshot_hash()
        self.assertEqual(
            "EMPTY",
            pinned_context_freshness(
                PinnedContextSet(),
                None,
                current_source_snapshot_hash=current,
            ),
        )
        self.assertEqual(
            "UNBOUND",
            pinned_context_freshness(
                self.pinned,
                None,
                current_source_snapshot_hash=current,
            ),
        )
        envelope = self.envelope()
        self.assertEqual(
            "FRESH",
            pinned_context_freshness(
                self.pinned,
                envelope,
                current_source_snapshot_hash=current,
            ),
        )

    def test_stale_pinned_context_blocks_until_explicit_refresh(self) -> None:
        envelope = self.envelope()
        (self.root / "docs" / "a.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "pinned context is stale"):
            require_fresh_pinned_context(
                self.pinned,
                envelope,
                current_source_snapshot_hash=self.workspace.snapshot_hash(),
            )

    def test_pinned_draft_must_project_every_pin(self) -> None:
        (self.root / "other.txt").write_text("other\n", encoding="utf-8")
        route = route_interaction("inspect @file[other.txt]", self.workspace)
        wrong_envelope = build_context_envelope(
            route,
            self.workspace,
            source_snapshot_hash=self.workspace.snapshot_hash(),
        )
        with self.assertRaisesRegex(PolicyError, "omits paths"):
            require_fresh_pinned_context(
                self.pinned,
                wrong_envelope,
                current_source_snapshot_hash=self.workspace.snapshot_hash(),
            )


if __name__ == "__main__":
    unittest.main()
