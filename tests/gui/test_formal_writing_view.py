from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from ourd.formal_writing import FormalWritingService, compile_formal_writing_request
from ourd_gui.formal_writing_models import FormalWritingFormState
from ourd_gui.formal_writing_projection import ProjectionDiagnostic
from ourd_gui.views.formal_writing import FormalWritingView


class FormalWritingViewTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()

    def tearDown(self) -> None:
        if hasattr(self, "root"):
            self.root.destroy()

    def test_form_round_trip_and_read_only_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("# Source\n\nGrounded evidence.\n", encoding="utf-8")
            expected = FormalWritingFormState(
                objective="Evaluate grounded evidence",
                profile="scientific-essay",
                genre="report",
                audience="reviewers",
                discipline="engineering",
                word_target=900,
                source_paths=("source.md",),
                constraints=("include limitations",),
                citation_style="apa-7",
                network_policy="offline",
                output_paths=("output.md",),
            )
            view = FormalWritingView(self.root, root, initial_form=expected)
            observed = view.form_state()
        self.assertEqual(expected, observed)
        self.assertEqual("disabled", str(view.draft_text.cget("state")))

    def test_manifest_and_exact_audit_status_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text(
                "# Source\n\nA grounded claim with evidence.\n",
                encoding="utf-8",
            )
            result = FormalWritingService(root).execute(
                compile_formal_writing_request(
                    operation="draft",
                    objective="grounded claim evidence",
                    source_paths=("source.md",),
                )
            )
            view = FormalWritingView(
                self.root,
                root,
                initial_form=FormalWritingFormState(
                    objective="grounded claim evidence",
                    source_paths=("source.md",),
                ),
            )
            view.refresh(select_identifier=result.request.request_id)
            manifest = str(view.source_list.get(0))
            selected_id = view.selected_result.request_id if view.selected_result else ""
        self.assertIn("source.md", manifest)
        self.assertIn("source:", manifest)
        self.assertIn("CURRENT", manifest)
        self.assertEqual(result.request.request_id, selected_id)
        self.assertEqual(
            result.qualified_document.audit.status,
            view.audit_status_var.get().removeprefix("Audit: "),
        )

    def test_refresh_preserves_exact_selected_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("# Source\n\nEvidence.\n", encoding="utf-8")
            service = FormalWritingService(root)
            first = service.execute(
                compile_formal_writing_request(
                    operation="plan",
                    objective="First plan",
                    source_paths=("source.md",),
                )
            )
            service.execute(
                compile_formal_writing_request(
                    operation="plan",
                    objective="Second plan",
                    source_paths=("source.md",),
                )
            )
            view = FormalWritingView(self.root, root)
            view.refresh(select_identifier=first.request.request_id)
            view.refresh()
            selected_id = view.selected_result.request_id if view.selected_result else ""
        self.assertEqual(first.request.request_id, selected_id)

    def test_governed_prepare_button_requires_exact_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.md").write_text("# Source\n\nEvidence.\n", encoding="utf-8")
            result = FormalWritingService(root).execute(
                compile_formal_writing_request(
                    operation="draft",
                    objective="Evidence",
                    source_paths=("source.md",),
                )
            )
            authority = root / "authority.json"
            authority.write_text("{}", encoding="utf-8")
            view = FormalWritingView(
                self.root,
                root,
                on_prepare_write=lambda _form: None,
                authority_path=authority,
                initial_form=FormalWritingFormState(output_paths=("output.md",)),
            )
            view.refresh(select_identifier=result.request.request_id)
            ready_state = str(view.prepare_write_button.cget("state"))
            view.set_busy(True)
            busy_state = str(view.prepare_write_button.cget("state"))
            view.set_busy(False)
            view.draft_id_var.set("draft:wrong")
            wrong_draft_state = str(view.prepare_write_button.cget("state"))
        self.assertEqual("normal", ready_state)
        self.assertEqual("disabled", busy_state)
        self.assertEqual("disabled", wrong_draft_state)

    def test_optional_ocr_state_matches_detected_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = FormalWritingView(self.root, Path(directory))
            if view.capabilities["ocr"]:
                self.assertEqual("normal", str(view.ocr_checkbox.cget("state")))
            else:
                self.assertEqual("disabled", str(view.ocr_checkbox.cget("state")))
                view.allow_ocr_var.set(True)
                self.assertFalse(view.execution_options().allow_ocr)

    def test_narrow_layout_keeps_all_primary_panes_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.root.deiconify()
            self.root.geometry("1100x700+0+0")
            view = FormalWritingView(self.root, Path(directory))
            view.pack(fill="both", expand=True)
            self.root.update_idletasks()
            view.rebalance_panes(force=True)
            self.root.update_idletasks()
            widths = (
                view.document_frame.winfo_width(),
                view.graph_frame.winfo_width(),
                view.evidence_frame.winfo_width(),
                view.audit_frame.winfo_width(),
            )
        self.assertTrue(all(width >= 220 for width in widths), widths)
        self.assertEqual(1, int(view.request_canvas.cget("takefocus")))

    def test_diagnostic_export_is_atomic_bounded_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "formal-diagnostics.json"
            view = FormalWritingView(self.root, root)
            view.diagnostics = (
                ProjectionDiagnostic(
                    path=root / "broken.json",
                    category="INVALID_RESULT_ARTIFACT",
                    message="api_key=super-secret-token",
                ),
            )
            with mock.patch(
                "ourd_gui.views.formal_writing.filedialog.asksaveasfilename",
                return_value=str(destination),
            ):
                view._export_diagnostics()
            exported = destination.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-token", exported)
        self.assertIn("<redacted>", exported)
        self.assertLessEqual(len(exported), 100_100)


if __name__ == "__main__":
    unittest.main()
