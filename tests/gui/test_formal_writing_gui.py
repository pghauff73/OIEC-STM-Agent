from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from ourd.writing_engine import compile_formal_writing_request
from ourd_gui.formal_writing_gui import (
    FormalWritingApplication,
    _governed_preview_text,
    _initial_state,
    build_parser,
    main,
)
from ourd_gui.formal_writing_models import FormalWritingFormState, GovernedWritePreview
from ourd_gui.views.shell import WorkbenchShell


class FormalWritingGuiTests(unittest.TestCase):
    def test_parser_accepts_standalone_contract_and_repo_alias(self) -> None:
        args = build_parser().parse_args(
            [
                "--repo",
                "/tmp/workspace",
                "--authority",
                "/tmp/authority.json",
                "--open-result",
                "draft:example",
                "--profile",
                "engineering-report",
                "--task",
                "Explain the result",
                "--source",
                "source.md",
                "--rubric",
                "rubric.txt",
                "--network-policy",
                "metadata-only",
                "--require-page-accuracy",
                "--allow-ocr",
                "--ocr-language",
                "eng",
                "--smoke-test",
            ]
        )
        self.assertEqual("/tmp/workspace", args.workspace)
        self.assertEqual(Path("/tmp/authority.json"), args.authority)
        self.assertEqual("draft:example", args.open_result)
        self.assertEqual(["source.md"], args.source)
        self.assertEqual(["rubric.txt"], args.rubric)
        self.assertTrue(args.require_page_accuracy)
        self.assertTrue(args.allow_ocr)
        self.assertTrue(args.smoke_test)

    def test_initial_state_is_workspace_bound_and_does_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("source", encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "--workspace",
                    str(root),
                    "--task",
                    "Draft a report",
                    "--source",
                    str(root / "source.md"),
                    "--require-qualified",
                ]
            )
            form, options = _initial_state(root, args)
        self.assertEqual(("source.md",), form.source_paths)
        self.assertEqual("Draft a report", form.objective)
        self.assertTrue(options.require_qualified)

    def test_smoke_main_constructs_and_closes_without_submitting(self) -> None:
        captured: dict[str, object] = {}

        class FakeApplication:
            def __init__(self, repository_root: Path, **kwargs: object) -> None:
                captured["repository_root"] = repository_root
                captured.update(kwargs)
                captured["submitted"] = False

            def update_idletasks(self) -> None:
                captured["updated"] = True

            def _close(self) -> None:
                captured["closed"] = True

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch(
                "ourd_gui.formal_writing_gui.FormalWritingApplication",
                FakeApplication,
            ):
                exit_code = main(
                    [
                        "--workspace",
                        directory,
                        "--task",
                        "Inspect only",
                        "--smoke-test",
                    ]
                )
        self.assertEqual(0, exit_code)
        self.assertTrue(captured["updated"])
        self.assertTrue(captured["closed"])
        self.assertFalse(captured["submitted"])

    def test_invalid_workspace_fails_before_tk_construction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with mock.patch(
                "ourd_gui.formal_writing_gui.FormalWritingApplication"
            ) as application:
                exit_code = main(["--workspace", str(missing), "--smoke-test"])
        self.assertEqual(2, exit_code)
        application.assert_not_called()

    def test_standalone_preferences_exclude_form_authority_and_document_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_objective = "PRIVATE_FORM_OBJECTIVE_8675309"
            secret_source_body = "PRIVATE_SOURCE_BODY_314159"
            authority = root / "authority.json"
            authority.write_text('{"private_authority":"AUTHORITY_SECRET_2718"}', encoding="utf-8")
            (root / "source.md").write_text(secret_source_body, encoding="utf-8")
            try:
                application = FormalWritingApplication(
                    root,
                    authority_path=authority,
                    initial_form=FormalWritingFormState(
                        objective=secret_objective,
                        source_paths=("source.md",),
                    ),
                )
            except tk.TclError as exc:
                self.skipTest(f"Tk display unavailable: {exc}")
            application.update_idletasks()
            application._close()
            preference_path = root / ".ourd-agent" / "gui" / "preferences.json"
            raw = preference_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        self.assertNotIn(secret_objective, raw)
        self.assertNotIn(secret_source_body, raw)
        self.assertNotIn("AUTHORITY_SECRET_2718", raw)
        self.assertNotIn("authority", payload)
        self.assertNotIn("task", payload)
        self.assertNotIn("source_paths", payload)

    def test_governed_preview_text_preserves_exact_statuses_and_bindings(self) -> None:
        request = compile_formal_writing_request(
            operation="write",
            objective="Prepare an output",
            source_document_ids=("source:" + "a" * 64,),
            source_paths=("source.md",),
            output_paths=("output.md",),
            authority_binding="/tmp/authority.json",
        )
        preview = GovernedWritePreview(
            request=request,
            draft_id="draft:exact",
            draft_sha256="b" * 64,
            audit_id="writing-audit:exact",
            audit_status="EVIDENCE_INSUFFICIENT",
            qualified_document_id="qualified-document:exact",
            source_bindings=(("source:" + "a" * 64, "source.md", "a" * 64),),
            output_paths=("output.md",),
            authority_path="/tmp/authority.json",
            authority_sha256="c" * 64,
            limitations=("POTENTIAL_NOVELTY_REQUIRES_REVIEW",),
        )
        text = _governed_preview_text(preview)
        self.assertIn(request.request_signature, text)
        self.assertIn("EVIDENCE_INSUFFICIENT", text)
        self.assertIn("POTENTIAL_NOVELTY_REQUIRES_REVIEW", text)
        self.assertIn("source.md", text)
        self.assertIn("output.md", text)

    def test_embedded_shell_exposes_formal_writing_callbacks(self) -> None:
        parameters = WorkbenchShell.__init__.__annotations__
        self.assertIn("on_formal_writing_submit", parameters)
        self.assertIn("on_formal_writing_prepare", parameters)
        self.assertIn("on_formal_writing_authority", parameters)


if __name__ == "__main__":
    unittest.main()
