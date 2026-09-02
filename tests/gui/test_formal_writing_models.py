from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd.writing_engine import compile_formal_writing_request
from ourd.writing_engine.compiler import WRITING_PROFILES
from ourd_gui.formal_writing_models import FormalWritingFormState
from ourd_gui.formal_writing_models import MAX_FORMAL_WRITING_INPUT_BYTES


class FormalWritingGuiModelTests(unittest.TestCase):
    def test_form_state_compiles_through_the_canonical_compiler(self) -> None:
        form = FormalWritingFormState(
            objective="Evaluate the evidence",
            profile="scientific-essay",
            source_paths=("source.md",),
            rubric_paths=("rubric.md",),
            constraints=("include counterevidence",),
            word_target=1800,
            citation_style="apa-7",
        )
        observed = form.compile_request("draft")
        expected = compile_formal_writing_request(
            operation="draft",
            objective="Evaluate the evidence",
            profile="scientific-essay",
            source_paths=("source.md",),
            rubric_paths=("rubric.md",),
            constraints=("include counterevidence",),
            word_target=1800,
            citation_style="apa-7",
            requested_outputs=("draft",),
        )
        self.assertEqual(expected, observed)

    def test_all_canonical_profiles_are_accepted(self) -> None:
        for profile in WRITING_PROFILES:
            with self.subTest(profile=profile):
                request = FormalWritingFormState(
                    objective="Profile test",
                    profile=profile,
                ).compile_request("plan")
                self.assertEqual(profile, request.profile)

    def test_absolute_paths_must_remain_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inside = root / "source.md"
            inside.write_text("source", encoding="utf-8")
            state = FormalWritingFormState(
                objective="Path test",
                source_paths=(str(inside),),
            ).with_paths_relative_to(root)
            self.assertEqual(("source.md",), state.source_paths)
            with self.assertRaisesRegex(ValueError, "outside the workspace"):
                FormalWritingFormState(
                    objective="Path test",
                    source_paths=("/tmp/outside.md",),
                ).with_paths_relative_to(root)

    def test_input_limits_and_symlinks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            oversized = root / "oversized.md"
            with oversized.open("wb") as handle:
                handle.truncate(MAX_FORMAL_WRITING_INPUT_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "individual size limit"):
                FormalWritingFormState(
                    objective="Limit test",
                    source_paths=("oversized.md",),
                ).with_paths_relative_to(root)
            target = root / "target.md"
            target.write_text("source", encoding="utf-8")
            link = root / "link.md"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlinks are not supported"):
                FormalWritingFormState(
                    objective="Symlink test",
                    source_paths=("link.md",),
                ).with_paths_relative_to(root)


if __name__ == "__main__":
    unittest.main()
