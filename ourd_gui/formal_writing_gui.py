from __future__ import annotations

import argparse
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Sequence

from ourd.writing_engine.compiler import WRITING_PROFILES

from .formal_writing_controller import FormalWritingController
from .formal_writing_models import (
    NETWORK_POLICIES,
    FormalWritingExecutionOptions,
    FormalWritingFormState,
    GovernedWritePreview,
)
from .persistence import GuiPreferencesStore
from .views.formal_writing import FormalWritingView


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-formal-writing-gui",
        description="Standalone source-grounded formal-writing workbench",
    )
    parser.add_argument(
        "--workspace",
        "--repo",
        dest="workspace",
        default=".",
        help="Repository/workspace root",
    )
    parser.add_argument("--authority", type=Path, help="Exact-snapshot authority manifest")
    parser.add_argument("--open-result", default="", help="Persisted request, plan, draft, or audit ID")
    parser.add_argument("--profile", choices=WRITING_PROFILES, default="general")
    parser.add_argument("--task", default="", help="Initial task or research question")
    parser.add_argument("--genre", default="essay")
    parser.add_argument("--audience", default="general")
    parser.add_argument("--discipline", default="general")
    parser.add_argument("--word-target", type=int, default=0)
    parser.add_argument("--citation-style", default="author-date")
    parser.add_argument("--locale", default="en")
    parser.add_argument("--source", action="append", default=[], help="Workspace source path")
    parser.add_argument("--rubric", action="append", default=[], help="Workspace rubric path")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--output", action="append", default=[], help="Governed output path")
    parser.add_argument(
        "--network-policy",
        choices=NETWORK_POLICIES,
        default="offline",
    )
    parser.add_argument("--require-page-accuracy", action="store_true")
    parser.add_argument("--allow-ocr", action="store_true")
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--require-qualified", action="store_true")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Build and close the workbench without entering the event loop",
    )
    return parser


class GovernedWriteConfirmationDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, preview: GovernedWritePreview) -> None:
        super().__init__(parent)
        self._preview = preview
        self.title("Confirm Governed Write Preparation")
        self.geometry("860x680")
        self.minsize(680, 520)
        self.transient(parent)
        self.result: str | None = None
        self.signature_var = tk.StringVar()

        ttk.Label(
            self,
            text=(
                "Preparation creates a governed transaction and EON action only. "
                "It does not approve, apply, or certify the output."
            ),
            wraplength=820,
            justify="left",
        ).pack(fill="x", padx=12, pady=(12, 6))
        details = ScrolledText(self, wrap="word", height=24)
        details.pack(fill="both", expand=True, padx=12, pady=6)
        details.insert("1.0", _governed_preview_text(preview))
        details.configure(state="disabled")

        ttk.Label(
            self,
            text="Type the exact request signature to confirm this immutable preview:",
        ).pack(anchor="w", padx=12, pady=(6, 2))
        entry = ttk.Entry(self, textvariable=self.signature_var)
        entry.pack(fill="x", padx=12)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right")
        self.confirm_button = ttk.Button(
            buttons,
            text="Prepare Governed Transaction",
            command=self._confirm,
            state="disabled",
        )
        self.confirm_button.pack(side="right", padx=(0, 8))
        self.signature_var.trace_add("write", self._update_confirmation_state)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Return>", self._submit_if_valid)
        self.grab_set()
        entry.focus_set()

    def _update_confirmation_state(self, *_args: object) -> None:
        expected = self._preview.request_signature
        state = "normal" if self.signature_var.get() == expected else "disabled"
        self.confirm_button.configure(state=state)

    def _submit_if_valid(self, _event: object | None = None) -> str:
        if str(self.confirm_button.cget("state")) == "normal":
            self._confirm()
        return "break"

    def _confirm(self) -> None:
        self.result = self.signature_var.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def _governed_preview_text(preview: GovernedWritePreview) -> str:
    sources = "\n".join(
        f"  - {source_id}\n    path={path}\n    sha256={digest}"
        for source_id, path, digest in preview.source_bindings
    ) or "  - none"
    outputs = "\n".join(f"  - {path}" for path in preview.output_paths) or "  - none"
    limitations = "\n".join(f"  - {item}" for item in preview.limitations) or "  - none"
    return (
        f"Request ID: {preview.request.request_id}\n"
        f"Request signature: {preview.request_signature}\n"
        f"Task: {preview.request.objective}\n"
        f"Profile: {preview.request.profile}\n"
        f"Draft ID: {preview.draft_id}\n"
        f"Draft SHA-256: {preview.draft_sha256}\n"
        f"Audit ID: {preview.audit_id or 'missing'}\n"
        f"Audit status: {preview.audit_status}\n"
        f"Qualified document ID: {preview.qualified_document_id or 'missing'}\n"
        f"Authority: {preview.authority_path}\n"
        f"Authority SHA-256: {preview.authority_sha256}\n\n"
        f"Source bindings:\n{sources}\n\n"
        f"Output paths:\n{outputs}\n\n"
        f"Limitations:\n{limitations}\n"
    )


def confirm_governed_write(
    parent: tk.Misc,
    preview: GovernedWritePreview,
) -> str | None:
    dialog = GovernedWriteConfirmationDialog(parent, preview)
    parent.wait_window(dialog)
    return dialog.result


class FormalWritingApplication(tk.Tk):
    POLL_MS = 50

    def __init__(
        self,
        repository_root: Path,
        *,
        authority_path: Path | None = None,
        initial_form: FormalWritingFormState | None = None,
        initial_options: FormalWritingExecutionOptions | None = None,
        open_result: str = "",
    ) -> None:
        super().__init__()
        self.repository_root = repository_root.resolve()
        self.authority_path = authority_path.resolve() if authority_path is not None else None
        self.initial_options = initial_options or FormalWritingExecutionOptions()
        self.preferences_store = GuiPreferencesStore(self.repository_root)
        self.preferences = self.preferences_store.load()
        self.font_scale_var = tk.DoubleVar(value=self.preferences.formal_font_scale)
        self._font_bases: dict[str, int] = {}
        self._apply_font_scale(self.preferences.formal_font_scale)
        self.controller = FormalWritingController(
            self.repository_root,
            authority_path=self.authority_path,
        )
        self._closing = False
        self._poll_handle: str | None = None
        self.title(f"Formal Writing Workbench — {self.repository_root.name}")
        self.geometry(self.preferences.formal_window_geometry)
        self.minsize(1100, 700)
        self._build_menu()
        self.view = FormalWritingView(
            self,
            self.repository_root,
            on_submit=self._submit,
            on_cancel=self._cancel,
            on_prepare_write=self._prepare_governed_write,
            on_authority_selected=self._set_authority,
            authority_path=self.authority_path,
            initial_form=initial_form,
        )
        self.view.pack(fill="both", expand=True)
        self.view.require_page_accuracy_var.set(self.initial_options.require_page_accuracy)
        self.view.allow_ocr_var.set(
            self.initial_options.allow_ocr and self.view.capabilities["ocr"]
        )
        self.view.ocr_language_var.set(self.initial_options.ocr_language)
        self.view.require_qualified_var.set(self.initial_options.require_qualified)
        self.view.apply_preferences(
            selected_control_tab=self.preferences.formal_selected_control_tab,
            selected_result_id=open_result or self.preferences.formal_selected_result_id,
        )
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind_all("<Control-r>", lambda _event: self.view.refresh())
        self.bind_all("<Control-Return>", lambda _event: self.view._invoke_action("draft"))
        self.bind_all("<Escape>", lambda _event: self._cancel())
        self._poll_handle = self.after(self.POLL_MS, self._poll)

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Select Authority…", command=self._select_authority)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self._close, accelerator="Ctrl+Q")
        menu.add_cascade(label="File", menu=file_menu)
        run_menu = tk.Menu(menu, tearoff=False)
        for label, operation in (
            ("Research", "research"),
            ("Argument", "argue"),
            ("Plan", "plan"),
            ("Draft", "draft"),
            ("Audit", "audit"),
            ("Revise", "revise"),
            ("Inspect Sources", "inspect"),
            ("Locate Passage", "locate"),
            ("Explain Reference", "explain"),
            ("Export References", "export"),
        ):
            run_menu.add_command(
                label=label,
                command=lambda action=operation: self.view._invoke_action(action),
            )
        run_menu.entryconfigure("Draft", accelerator="Ctrl+Enter")
        run_menu.add_separator()
        run_menu.add_command(label="Stop After Current Phase", command=self._cancel, accelerator="Esc")
        menu.add_cascade(label="Run", menu=run_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(
            label="Refresh Artifacts",
            command=lambda: self.view.refresh(),
            accelerator="Ctrl+R",
        )
        view_menu.add_separator()
        for label, scale in (("100%", 1.0), ("125%", 1.25), ("150%", 1.5), ("200%", 2.0)):
            view_menu.add_radiobutton(
                label=f"Font Scale {label}",
                variable=self.font_scale_var,
                value=scale,
                command=lambda value=scale: self._apply_font_scale(value),
            )
        menu.add_cascade(label="View", menu=view_menu)
        self.configure(menu=menu)
        self.bind_all("<Control-q>", lambda _event: self._close())

    def _apply_font_scale(self, scale: float) -> None:
        normalized = max(1.0, min(float(scale), 2.0))
        self.font_scale_var.set(normalized)
        for name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkFixedFont",
            "TkMenuFont",
            "TkHeadingFont",
        ):
            font = tkfont.nametofont(name)
            base_size = self._font_bases.setdefault(name, int(font.actual("size")))
            font.configure(size=max(7, round(base_size * normalized)))
        if hasattr(self, "view"):
            self.view.rebalance_panes(force=True)

    def _submit(
        self,
        operation: str,
        form: FormalWritingFormState,
        options: FormalWritingExecutionOptions,
    ) -> None:
        job_id = self.controller.submit(operation, form, options)
        self.view.set_busy(True, message=f"Queued {job_id}")

    def _cancel(self) -> None:
        if self.controller.request_cancel():
            self.view.status_var.set("Cancellation requested; waiting for a safe phase boundary")

    def _set_authority(self, authority_path: Path) -> None:
        self.authority_path = authority_path.resolve()
        self.controller.authority_path = self.authority_path
        self.view.set_authority_path(self.authority_path)

    def _select_authority(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select exact-snapshot authority manifest",
            initialdir=self.repository_root,
            filetypes=(("JSON", "*.json"), ("All files", "*")),
        )
        if selected:
            self._set_authority(Path(selected))

    def _prepare_governed_write(self, form: FormalWritingFormState) -> None:
        preview = self.controller.preview_governed_write(form)
        confirmed = confirm_governed_write(self, preview)
        if confirmed is None:
            self.view.status_var.set("Governed write preparation cancelled")
            return
        job_id = self.controller.submit_governed_write(
            preview,
            confirmed_request_signature=confirmed,
        )
        self.view.set_busy(True, message=f"Queued {job_id}")

    def _poll(self) -> None:
        if self._closing:
            return
        for event in self.controller.poll_events():
            self.view.apply_event(event)
        self._poll_handle = self.after(self.POLL_MS, self._poll)

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._poll_handle is not None:
            try:
                self.after_cancel(self._poll_handle)
            except tk.TclError:
                pass
            self._poll_handle = None
        self.controller.shutdown(wait=False, timeout_seconds=1.0)
        preference_state = self.view.preference_state()
        try:
            self.preferences_store.save(
                replace(
                    self.preferences,
                    formal_window_geometry=self.geometry(),
                    formal_selected_control_tab=int(
                        preference_state["selected_control_tab"]
                    ),
                    formal_selected_result_id=str(
                        preference_state["selected_result_id"]
                    ),
                    formal_font_scale=float(self.font_scale_var.get()),
                )
            )
        except (OSError, ValueError, tk.TclError):
            pass
        self.destroy()


def _initial_state(
    repository_root: Path,
    args: argparse.Namespace,
) -> tuple[FormalWritingFormState, FormalWritingExecutionOptions]:
    form = FormalWritingFormState(
        objective=args.task,
        profile=args.profile,
        genre=args.genre,
        audience=args.audience,
        discipline=args.discipline,
        word_target=args.word_target,
        source_paths=tuple(args.source),
        rubric_paths=tuple(args.rubric),
        constraints=tuple(args.constraint),
        citation_style=args.citation_style,
        locale=args.locale,
        network_policy=args.network_policy,
        output_paths=tuple(args.output),
    ).with_paths_relative_to(repository_root)
    options = FormalWritingExecutionOptions(
        allow_ocr=args.allow_ocr,
        ocr_language=args.ocr_language,
        require_page_accuracy=args.require_page_accuracy,
        require_qualified=args.require_qualified,
    )
    return form, options


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = Path(args.workspace).expanduser().resolve()
    try:
        if not repository_root.is_dir():
            raise ValueError(f"workspace does not exist or is not a directory: {repository_root}")
        form, options = _initial_state(repository_root, args)
        application = FormalWritingApplication(
            repository_root,
            authority_path=args.authority,
            initial_form=form,
            initial_options=options,
            open_result=args.open_result,
        )
        if args.smoke_test:
            application.update_idletasks()
            application._close()
            return 0
        application.mainloop()
        return 0
    except (OSError, RuntimeError, ValueError, tk.TclError) as exc:
        print(f"formal-writing GUI startup failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FormalWritingApplication",
    "GovernedWriteConfirmationDialog",
    "build_parser",
    "confirm_governed_write",
    "main",
]
