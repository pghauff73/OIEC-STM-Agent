from __future__ import annotations

import importlib.util
import json
import mimetypes
import os
import tempfile
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from ourd.writing_engine.compiler import WRITING_PROFILES

from ..formal_writing_models import (
    NETWORK_POLICIES,
    MAX_FORMAL_WRITING_INPUT_BYTES,
    MAX_FORMAL_WRITING_INPUTS,
    MAX_FORMAL_WRITING_TOTAL_INPUT_BYTES,
    FormalWritingExecutionOptions,
    FormalWritingFormState,
    FormalWritingGuiEvent,
    FormalWritingGuiEventType,
)
from ..formal_writing_projection import (
    FormalWritingProjectionStore,
    FormalWritingResultProjection,
    ProjectionDiagnostic,
    SourcePageProjection,
)
from ..redaction import safe_projection
from ..widgets.graph_view import GraphNode, GraphView


SubmitCallback = Callable[
    [str, FormalWritingFormState, FormalWritingExecutionOptions],
    None,
]
PrepareWriteCallback = Callable[[FormalWritingFormState], None]
AuthorityCallback = Callable[[Path], None]
AlgorithmsCallback = Callable[[tuple[str, ...]], None]

SUPPORTED_SOURCE_SUFFIXES = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".markdown",
    ".md",
    ".pdf",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 2_000
MAX_DIAGNOSTIC_CHARACTERS = 100_000
MAX_PDF_PREVIEW_PIXELS = 4_000_000
MAX_DISPLAYED_TEXT_CHARACTERS = 500_000
MAX_DISPLAYED_SOURCE_CHARACTERS = 200_000


def optional_capabilities() -> dict[str, bool]:
    pdf = importlib.util.find_spec("fitz") is not None
    ocr = (
        pdf
        and importlib.util.find_spec("PIL") is not None
        and importlib.util.find_spec("pytesseract") is not None
    )
    return {"pdf": pdf, "ocr": ocr}


class FormalWritingView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository_root: Path,
        *,
        on_submit: SubmitCallback | None = None,
        on_cancel: Callable[[], None] | None = None,
        on_prepare_write: PrepareWriteCallback | None = None,
        on_authority_selected: AuthorityCallback | None = None,
        on_show_algorithms: AlgorithmsCallback | None = None,
        authority_path: Path | None = None,
        initial_form: FormalWritingFormState | None = None,
    ) -> None:
        super().__init__(master)
        self.repository_root = repository_root.resolve()
        self.store = FormalWritingProjectionStore(self.repository_root)
        self.on_submit = on_submit
        self.on_cancel = on_cancel
        self.on_prepare_write = on_prepare_write
        self.on_authority_selected = on_authority_selected
        self.on_show_algorithms = on_show_algorithms
        self.results: tuple[FormalWritingResultProjection, ...] = ()
        self.pages: tuple[SourcePageProjection, ...] = ()
        self.diagnostics: tuple[ProjectionDiagnostic, ...] = ()
        self.selected_result: FormalWritingResultProjection | None = None
        self._selected_pages: tuple[SourcePageProjection, ...] = ()
        self._pdf_image: tk.PhotoImage | None = None
        self._busy = False
        self._path_values: dict[tk.Listbox, tuple[str, ...]] = {}
        self._pane_layout_handle: str | None = None
        self._last_pane_layout_size: tuple[int, int] = (0, 0)
        self.capabilities = optional_capabilities()
        self._selected_algorithm_ids: tuple[str, ...] = ()

        self.status_var = tk.StringVar(value="Idle")
        self.audit_status_var = tk.StringVar(value="Audit: not selected")
        self.objective_var = tk.StringVar()
        self.profile_var = tk.StringVar(value="general")
        self.genre_var = tk.StringVar(value="essay")
        self.audience_var = tk.StringVar(value="general")
        self.discipline_var = tk.StringVar(value="general")
        self.word_target_var = tk.StringVar(value="0")
        self.citation_style_var = tk.StringVar(value="author-date")
        self.locale_var = tk.StringVar(value="en")
        self.network_policy_var = tk.StringVar(value="offline")
        self.plan_id_var = tk.StringVar()
        self.draft_id_var = tk.StringVar()
        self.require_page_accuracy_var = tk.BooleanVar(value=False)
        self.allow_ocr_var = tk.BooleanVar(value=False)
        self.ocr_language_var = tk.StringVar(value="eng")
        self.require_qualified_var = tk.BooleanVar(value=False)
        self.authority_path_var = tk.StringVar(
            value=str(authority_path.resolve()) if authority_path is not None else "Not selected"
        )

        self._build_toolbar()
        self._build_workbench()
        self.bind("<Destroy>", self._cancel_pane_layout, add="+")
        self.set_form_state(initial_form or FormalWritingFormState())
        self.refresh()

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=8)
        toolbar.columnconfigure(0, weight=1)
        summary = ttk.Frame(toolbar)
        summary.grid(row=0, column=0, sticky="ew")
        ttk.Label(summary, text="Source-grounded formal writing").pack(side="left")
        ttk.Separator(summary, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(summary, textvariable=self.status_var).pack(side="left")
        ttk.Label(summary, textvariable=self.audit_status_var).pack(side="left", padx=(16, 0))
        actions = ttk.Frame(toolbar)
        actions.grid(row=1, column=0, sticky="e", pady=(4, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="right")
        self.cancel_button = ttk.Button(
            actions,
            text="Stop After Current Phase",
            command=self._cancel,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=(0, 8))

    def _build_workbench(self) -> None:
        self.outer_paned = ttk.PanedWindow(self, orient="horizontal")
        self.outer_paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        controls = ttk.Frame(self.outer_paned)
        self.workbench_paned = ttk.PanedWindow(self.outer_paned, orient="vertical")
        self.outer_paned.add(controls, weight=2)
        self.outer_paned.add(self.workbench_paned, weight=3)
        self._build_controls(controls)

        self.top_paned = ttk.PanedWindow(self.workbench_paned, orient="horizontal")
        self.bottom_paned = ttk.PanedWindow(self.workbench_paned, orient="horizontal")
        self.workbench_paned.add(self.top_paned, weight=3)
        self.workbench_paned.add(self.bottom_paned, weight=2)

        self.document_frame = ttk.Labelframe(self.top_paned, text="Document")
        self.graph_frame = ttk.Labelframe(self.top_paned, text="Argument Graph")
        self.top_paned.add(self.document_frame, weight=11)
        self.top_paned.add(self.graph_frame, weight=9)
        self._build_document_panel(self.document_frame)
        self._build_graph_panel(self.graph_frame)

        self.evidence_frame = ttk.Labelframe(self.bottom_paned, text="Evidence")
        self.audit_frame = ttk.Labelframe(self.bottom_paned, text="Formal Writing Audit")
        self.bottom_paned.add(self.evidence_frame, weight=11)
        self.bottom_paned.add(self.audit_frame, weight=9)
        self._build_evidence_panel(self.evidence_frame)
        self._build_audit_panel(self.audit_frame)
        self.outer_paned.bind("<Configure>", self._schedule_pane_layout, add="+")
        self._schedule_pane_layout()

    def _build_controls(self, parent: ttk.Frame) -> None:
        tabs = ttk.Notebook(parent)
        tabs.pack(fill="both", expand=True)
        request = ttk.Frame(tabs)
        inputs = ttk.Frame(tabs)
        runs = ttk.Frame(tabs)
        tabs.add(request, text="Request")
        tabs.add(inputs, text="Inputs")
        tabs.add(runs, text="Workflow & Runs")
        self.control_tabs = tabs
        self._build_request_editor(self._scrollable_editor(request))
        self._build_input_editor(inputs)
        self._build_runs_panel(runs)

    def _scrollable_editor(self, parent: ttk.Frame) -> ttk.Frame:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        background = ttk.Style(self).lookup("TFrame", "background") or "#f0f0f0"
        canvas = tk.Canvas(
            parent,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
        )
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
            add="+",
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
            add="+",
        )
        canvas.bind("<Prior>", lambda _event: canvas.yview_scroll(-1, "pages"))
        canvas.bind("<Next>", lambda _event: canvas.yview_scroll(1, "pages"))
        canvas.bind("<Home>", lambda _event: canvas.yview_moveto(0.0))
        canvas.bind("<End>", lambda _event: canvas.yview_moveto(1.0))
        canvas.bind(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, "units"),
        )
        canvas.bind("<Button-4>", lambda _event: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda _event: canvas.yview_scroll(1, "units"))
        self.request_canvas = canvas
        return content

    def _schedule_pane_layout(self, _event: tk.Event | None = None) -> None:
        if self._pane_layout_handle is not None:
            return
        self._pane_layout_handle = self.after_idle(self.rebalance_panes)

    def _cancel_pane_layout(self, event: tk.Event) -> None:
        if event.widget is not self or self._pane_layout_handle is None:
            return
        try:
            self.after_cancel(self._pane_layout_handle)
        except tk.TclError:
            pass
        self._pane_layout_handle = None

    def rebalance_panes(self, *, force: bool = False) -> None:
        self._pane_layout_handle = None
        width = self.outer_paned.winfo_width()
        height = self.outer_paned.winfo_height()
        if width <= 1 or height <= 1:
            return
        current_size = (width, height)
        if not force and current_size == self._last_pane_layout_size:
            return
        self._last_pane_layout_size = current_size
        try:
            controls_width = max(340, min(width - 560, round(width * 0.38)))
            self.outer_paned.sashpos(0, controls_width)
            workbench_height = self.workbench_paned.winfo_height()
            self.workbench_paned.sashpos(0, round(workbench_height * 0.55))
            self.top_paned.sashpos(0, round(self.top_paned.winfo_width() * 0.55))
            self.bottom_paned.sashpos(0, round(self.bottom_paned.winfo_width() * 0.55))
        except tk.TclError:
            return

    def _build_request_editor(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(parent, text="Task or research question").grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=6,
            pady=(6, 2),
        )
        row += 1
        self.objective_text = tk.Text(parent, height=6, wrap="word", undo=True)
        self.objective_text.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=6)
        parent.rowconfigure(row, weight=1)
        row += 1
        row = self._field(parent, row, "Profile", self.profile_var, values=WRITING_PROFILES)
        row = self._field(parent, row, "Genre", self.genre_var)
        row = self._field(parent, row, "Audience", self.audience_var)
        row = self._field(parent, row, "Discipline", self.discipline_var)
        row = self._field(parent, row, "Word target", self.word_target_var)
        row = self._field(parent, row, "Citation style", self.citation_style_var)
        row = self._field(parent, row, "Locale", self.locale_var)
        row = self._field(
            parent,
            row,
            "Network policy",
            self.network_policy_var,
            values=NETWORK_POLICIES,
        )
        ttk.Label(parent, text="Constraints (one per line)").grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=6,
            pady=(6, 2),
        )
        row += 1
        self.constraints_text = tk.Text(parent, height=4, wrap="word", undo=True)
        self.constraints_text.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6)
        row += 1
        ttk.Checkbutton(
            parent,
            text="Require exact page traceability",
            variable=self.require_page_accuracy_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 0))
        row += 1
        self.ocr_checkbox = ttk.Checkbutton(
            parent,
            text="Allow OCR when supported",
            variable=self.allow_ocr_var,
        )
        self.ocr_checkbox.grid(row=row, column=0, columnspan=2, sticky="w", padx=6)
        row += 1
        ttk.Label(parent, text="OCR language").grid(
            row=row,
            column=0,
            sticky="w",
            padx=6,
            pady=2,
        )
        self.ocr_language_entry = ttk.Entry(parent, textvariable=self.ocr_language_var)
        self.ocr_language_entry.grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        row += 1
        if not self.capabilities["ocr"]:
            self.allow_ocr_var.set(False)
            self.ocr_checkbox.configure(state="disabled")
            self.ocr_language_entry.configure(state="disabled")
            ttk.Label(parent, text="OCR unavailable in this installation").grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="w",
                padx=6,
            )
            row += 1
        ttk.Checkbutton(
            parent,
            text="Require qualified audit status",
            variable=self.require_qualified_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=6)
        row += 1
        row = self._field(parent, row, "Persisted plan ID", self.plan_id_var)
        row = self._field(parent, row, "Persisted draft ID", self.draft_id_var)
        ttk.Button(parent, text="Clear persisted lineage", command=self._clear_lineage).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=6,
            pady=6,
        )

    @staticmethod
    def _field(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        *,
        values: tuple[str, ...] | None = None,
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=2)
        if values is None:
            widget: ttk.Entry | ttk.Combobox = ttk.Entry(parent, textvariable=variable)
        else:
            widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        widget.grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        return row + 1

    def _build_input_editor(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(5, weight=1)
        parent.rowconfigure(9, weight=1)
        parent.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Sources").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.source_list = tk.Listbox(parent, exportselection=False)
        self.source_list.grid(row=1, column=0, sticky="nsew", padx=6)
        self._input_buttons(parent, 2, self.source_list, "source")

        ttk.Separator(parent).grid(row=3, column=0, sticky="ew", padx=6, pady=6)
        ttk.Label(parent, text="Rubrics").grid(row=4, column=0, sticky="nw", padx=6)
        self.rubric_list = tk.Listbox(parent, exportselection=False)
        self.rubric_list.grid(row=5, column=0, sticky="nsew", padx=6)
        self._input_buttons(parent, 6, self.rubric_list, "rubric")

        ttk.Separator(parent).grid(row=7, column=0, sticky="ew", padx=6, pady=6)
        ttk.Label(parent, text="Governed output paths").grid(row=8, column=0, sticky="nw", padx=6)
        self.output_list = tk.Listbox(parent, exportselection=False)
        self.output_list.grid(row=9, column=0, sticky="nsew", padx=6)
        buttons = ttk.Frame(parent)
        buttons.grid(row=10, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(buttons, text="Choose Output", command=self._choose_output).pack(side="left")
        ttk.Button(
            buttons,
            text="Remove",
            command=lambda: self._remove_selected(self.output_list),
        ).pack(side="left", padx=(4, 0))
        authority = ttk.Labelframe(parent, text="Authority Manifest")
        authority.grid(row=11, column=0, sticky="ew", padx=6, pady=(4, 6))
        authority.columnconfigure(0, weight=1)
        ttk.Label(
            authority,
            textvariable=self.authority_path_var,
            wraplength=280,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(authority, text="Select Authority", command=self._choose_authority).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=4,
            pady=(0, 4),
        )

    def _input_buttons(
        self,
        parent: ttk.Frame,
        row: int,
        widget: tk.Listbox,
        kind: str,
    ) -> None:
        buttons = ttk.Frame(parent)
        buttons.grid(row=row, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(
            buttons,
            text="Add Files",
            command=lambda: self._add_files(widget, kind),
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Add Folder",
            command=lambda: self._add_folder(widget, kind),
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            buttons,
            text="Remove",
            command=lambda: self._remove_selected(widget),
        ).pack(side="left", padx=(4, 0))

    def _build_runs_panel(self, parent: ttk.Frame) -> None:
        workflow = ttk.Labelframe(parent, text="Workflow")
        workflow.pack(fill="x", padx=6, pady=6)
        actions = (
            ("Research", "research"),
            ("Argument", "argue"),
            ("Plan", "plan"),
            ("Draft", "draft"),
            ("Audit", "audit"),
            ("Revise", "revise"),
            ("Inspect", "inspect"),
            ("Locate", "locate"),
            ("Explain", "explain"),
            ("References", "export"),
        )
        self.action_buttons: list[ttk.Button] = []
        for index, (label, operation) in enumerate(actions):
            button = ttk.Button(
                workflow,
                text=label,
                command=lambda action=operation: self._invoke_action(action),
            )
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
            workflow.columnconfigure(index % 2, weight=1)
            self.action_buttons.append(button)
        self.prepare_write_button = ttk.Button(
            workflow,
            text="Prepare Governed Write",
            command=self._prepare_write,
        )
        self.prepare_write_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=3, pady=3)
        self.draft_id_var.trace_add("write", lambda *_args: self._update_prepare_state())

        ttk.Label(parent, text="Writing Runs").pack(anchor="w", padx=6)
        self.run_list = tk.Listbox(parent, exportselection=False, height=10)
        self.run_list.pack(fill="both", expand=True, padx=6)
        self.run_list.bind("<<ListboxSelect>>", self._select_run)

        diagnostics_header = ttk.Frame(parent)
        diagnostics_header.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(diagnostics_header, text="Diagnostics").pack(side="left")
        ttk.Button(
            diagnostics_header,
            text="Export Report",
            command=self._export_diagnostics,
        ).pack(side="right")
        self.diagnostic_list = tk.Listbox(parent, exportselection=False, height=6)
        self.diagnostic_list.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _build_document_panel(self, parent: ttk.Frame) -> None:
        self.draft_text = ScrolledText(parent, wrap="word", state="disabled")
        self.draft_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.draft_text.tag_configure("selected_claim", background="#fff2a8", foreground="#111111")
        self.draft_text.bind("<ButtonRelease-1>", self._select_sentence)
        self.draft_text.bind("<KeyRelease>", self._select_sentence)
        self.draft_text.bind("<Control-f>", self._find_in_focused_text)

    def _build_graph_panel(self, parent: ttk.Frame) -> None:
        tabs = ttk.Notebook(parent)
        tabs.pack(fill="both", expand=True, padx=6, pady=6)
        graph_tab = ttk.Frame(tabs)
        raw_tab = ttk.Frame(tabs)
        tabs.add(graph_tab, text="Graph")
        tabs.add(raw_tab, text="Details")
        self.graph_view = GraphView(graph_tab, on_select=self._select_graph_node)
        self.graph_view.pack(fill="both", expand=True)
        self.argument_text = ScrolledText(raw_tab, wrap="none", state="disabled")
        self.argument_text.pack(fill="both", expand=True)
        self.argument_text.bind("<Control-f>", self._find_in_focused_text)

    def _build_evidence_panel(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=6, pady=6)
        toolbar.columnconfigure(0, weight=1)
        self.source_choice = ttk.Combobox(toolbar, state="readonly")
        self.source_choice.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.source_choice.bind("<<ComboboxSelected>>", self._select_source)
        self.page_choice = ttk.Combobox(toolbar, state="readonly", width=18)
        self.page_choice.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.page_choice.bind("<<ComboboxSelected>>", self._select_page)
        ttk.Button(toolbar, text="Copy Locator", command=self._copy_locator).grid(
            row=1,
            column=1,
            sticky="e",
            padx=(6, 0),
            pady=(4, 0),
        )

        tabs = ttk.Notebook(parent)
        tabs.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        text_tab = ttk.Frame(tabs)
        preview_tab = ttk.Frame(tabs)
        tabs.add(text_tab, text="Text & Locator")
        tabs.add(preview_tab, text="Safe PDF Preview")
        self.source_text = ScrolledText(text_tab, wrap="word", state="disabled")
        self.source_text.pack(fill="both", expand=True)
        self.source_text.bind("<Control-f>", self._find_in_focused_text)
        self.preview_label = ttk.Label(
            preview_tab,
            text="Select an ingested PDF page. Rendering is inert and optional.",
            anchor="center",
            justify="center",
        )
        self.preview_label.pack(fill="both", expand=True)

    def _build_audit_panel(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))
        self.algorithms_button = ttk.Button(
            toolbar,
            text="Qualified Algorithms",
            command=self._show_algorithms,
            state="disabled",
        )
        self.algorithms_button.pack(side="right")
        columns = ("metric", "value")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="x", padx=6, pady=6)
        tree_frame.columnconfigure(0, weight=1)
        self.audit_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=9)
        self.audit_tree.heading("metric", text="Metric / Status")
        self.audit_tree.heading("value", text="Canonical Value")
        self.audit_tree.column("metric", width=210, stretch=True)
        self.audit_tree.column("value", width=150, stretch=True)
        audit_scroll = ttk.Scrollbar(
            tree_frame,
            orient="horizontal",
            command=self.audit_tree.xview,
        )
        self.audit_tree.configure(xscrollcommand=audit_scroll.set)
        self.audit_tree.grid(row=0, column=0, sticky="ew")
        audit_scroll.grid(row=1, column=0, sticky="ew")
        self.audit_tree.bind("<<TreeviewSelect>>", self._select_audit_finding)
        self.audit_text = ScrolledText(parent, wrap="word", state="disabled", height=10)
        self.audit_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.audit_text.bind("<Control-f>", self._find_in_focused_text)

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        if len(value) > MAX_DISPLAYED_TEXT_CHARACTERS:
            value = (
                value[:MAX_DISPLAYED_TEXT_CHARACTERS]
                + "\n\n[display truncated at the formal-writing GUI character limit]"
            )
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _list_values(self, widget: tk.Listbox) -> tuple[str, ...]:
        return self._path_values.get(
            widget,
            tuple(str(value) for value in widget.get(0, "end")),
        )

    def _replace_list(self, widget: tk.Listbox, values: tuple[str, ...]) -> None:
        self._path_values[widget] = values
        widget.delete(0, "end")
        for value in values:
            widget.insert("end", self._input_display(widget, value))
        if hasattr(self, "prepare_write_button"):
            self._update_prepare_state()

    def _input_display(self, widget: tk.Listbox, value: str) -> str:
        if hasattr(self, "output_list") and widget is self.output_list:
            return value
        path = self.repository_root / value
        try:
            size = path.stat().st_size
        except OSError:
            return f"{value} | unavailable"
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        ingested = tuple(page for page in self.pages if page.source_path == value)
        if not ingested:
            return f"{value} | {media_type} | {size} bytes | not ingested"
        page = ingested[0]
        page_count = str(page.page_count) if page.page_count else "reflowable"
        return (
            f"{value} | {media_type} | {size} bytes | {page.source_document_id} | "
            f"pages={page_count} | ocr={page.ocr_status} | {page.freshness} | "
            f"sha256={page.content_sha256}"
        )

    def _refresh_input_manifests(self) -> None:
        for widget in (self.source_list, self.rubric_list, self.output_list):
            self._replace_list(widget, self._list_values(widget))

    def form_state(self) -> FormalWritingFormState:
        try:
            word_target = int(self.word_target_var.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("word target must be a whole number") from exc
        form = FormalWritingFormState(
            objective=self.objective_text.get("1.0", "end-1c"),
            profile=self.profile_var.get(),
            genre=self.genre_var.get(),
            audience=self.audience_var.get(),
            discipline=self.discipline_var.get(),
            word_target=word_target,
            source_paths=self._list_values(self.source_list),
            rubric_paths=self._list_values(self.rubric_list),
            constraints=tuple(self.constraints_text.get("1.0", "end-1c").splitlines()),
            citation_style=self.citation_style_var.get(),
            locale=self.locale_var.get(),
            network_policy=self.network_policy_var.get(),
            plan_id=self.plan_id_var.get(),
            draft_id=self.draft_id_var.get(),
            output_paths=self._list_values(self.output_list),
        )
        return form.with_paths_relative_to(self.repository_root)

    def execution_options(self) -> FormalWritingExecutionOptions:
        return FormalWritingExecutionOptions(
            allow_ocr=self.allow_ocr_var.get() and self.capabilities["ocr"],
            ocr_language=self.ocr_language_var.get(),
            require_page_accuracy=self.require_page_accuracy_var.get(),
            require_qualified=self.require_qualified_var.get(),
        )

    def set_form_state(self, form: FormalWritingFormState) -> None:
        self.objective_text.delete("1.0", "end")
        self.objective_text.insert("1.0", form.objective)
        self.profile_var.set(form.profile)
        self.genre_var.set(form.genre)
        self.audience_var.set(form.audience)
        self.discipline_var.set(form.discipline)
        self.word_target_var.set(str(form.word_target))
        self.citation_style_var.set(form.citation_style)
        self.locale_var.set(form.locale)
        self.network_policy_var.set(form.network_policy)
        self.plan_id_var.set(form.plan_id)
        self.draft_id_var.set(form.draft_id)
        self.constraints_text.delete("1.0", "end")
        self.constraints_text.insert("1.0", "\n".join(form.constraints))
        self._replace_list(self.source_list, form.source_paths)
        self._replace_list(self.rubric_list, form.rubric_paths)
        self._replace_list(self.output_list, form.output_paths)

    def set_authority_path(self, authority_path: Path | None) -> None:
        self.authority_path_var.set(
            str(authority_path.resolve()) if authority_path is not None else "Not selected"
        )
        self._update_prepare_state()

    def refresh(self, *, select_identifier: str = "") -> None:
        if not select_identifier and self.selected_result is not None:
            select_identifier = self.selected_result.request_id
        snapshot = self.store.snapshot()
        self.results = snapshot.results
        self.pages = snapshot.source_pages
        self.diagnostics = snapshot.diagnostics
        self._refresh_input_manifests()
        self.run_list.delete(0, "end")
        selected_index = -1
        for index, result in enumerate(self.results):
            self.run_list.insert(
                "end",
                f"{result.operation} · {result.audit_status} · {result.objective[:52]}",
            )
            if select_identifier and select_identifier in result.identifiers:
                selected_index = index
        self._refresh_diagnostics()
        source_paths = tuple(dict.fromkeys(page.source_path for page in self.pages))
        self.source_choice["values"] = source_paths
        if source_paths:
            self.source_choice.current(0)
            self._select_source()
        else:
            self.page_choice["values"] = ()
            self._set_text(self.source_text, "No ingested source pages are available.")
            self._clear_preview("No ingested PDF page is available.")
        if selected_index < 0 and self.results:
            selected_index = 0
        if selected_index >= 0:
            self.run_list.selection_clear(0, "end")
            self.run_list.selection_set(selected_index)
            self.run_list.see(selected_index)
            self._select_run()
        elif not self.results:
            self.selected_result = None
            self.audit_status_var.set("Audit: not selected")
            self._set_text(self.draft_text, "No formal-writing results are available.")
            self.graph_view.set_graph((), ())
            self._set_text(self.argument_text, "No argument graph is available.")
            self._render_audit(None)

    def apply_preferences(
        self,
        *,
        selected_control_tab: int = 0,
        selected_result_id: str = "",
    ) -> None:
        if 0 <= selected_control_tab < self.control_tabs.index("end"):
            self.control_tabs.select(selected_control_tab)
        if selected_result_id:
            self.refresh(select_identifier=selected_result_id)

    def preference_state(self) -> dict[str, object]:
        return {
            "selected_control_tab": self.control_tabs.index("current"),
            "selected_result_id": (
                self.selected_result.request_id if self.selected_result is not None else ""
            ),
        }

    def set_busy(self, busy: bool, *, message: str = "") -> None:
        self._busy = bool(busy)
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        self._update_prepare_state()
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.status_var.set(message or ("Working" if busy else "Idle"))

    def _update_prepare_state(self) -> None:
        if not hasattr(self, "prepare_write_button"):
            return
        result = self.selected_result
        ready = (
            not self._busy
            and self.on_prepare_write is not None
            and result is not None
            and bool(result.draft_id)
            and self.draft_id_var.get().strip() == result.draft_id
            and bool(result.audit_id)
            and bool(self._list_values(self.output_list))
            and self.authority_path_var.get() != "Not selected"
        )
        self.prepare_write_button.configure(state="normal" if ready else "disabled")

    def apply_event(self, event: FormalWritingGuiEvent) -> None:
        message = event.message or event.phase or event.event_type.value
        terminal = event.event_type in {
            FormalWritingGuiEventType.JOB_COMPLETED,
            FormalWritingGuiEventType.JOB_FAILED,
            FormalWritingGuiEventType.JOB_CANCELLED,
        }
        if event.event_type == FormalWritingGuiEventType.JOB_COMPLETED:
            self.set_busy(False, message=f"Completed {event.operation}: {message}")
            if event.audit_status:
                self.audit_status_var.set(f"Audit: {event.audit_status}")
            if event.details:
                self._append_runtime_diagnostic(event)
            self.refresh(select_identifier=event.result_request_id or event.request_id)
            self.run_list.focus_set()
            return
        if terminal:
            self.set_busy(False, message=f"{event.event_type.value}: {message}")
            if event.event_type == FormalWritingGuiEventType.JOB_FAILED:
                self._append_runtime_diagnostic(event)
            return
        self.set_busy(True, message=f"{event.operation}: {message}")

    def _invoke_action(self, operation: str) -> None:
        if self.on_submit is None:
            messagebox.showinfo(
                "Formal Writing",
                "This embedded view is observational because no execution controller is connected.",
                parent=self,
            )
            return
        try:
            form = self.form_state()
            if operation in {"inspect", "locate", "research", "argue", "plan", "explain", "export"}:
                form = replace(form, plan_id="", draft_id="")
            self.on_submit(operation, form, self.execution_options())
            self.set_busy(True, message=f"Queued {operation}")
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Formal Writing", str(exc), parent=self)

    def _prepare_write(self) -> None:
        if self.on_prepare_write is None:
            messagebox.showinfo(
                "Governed Write",
                "Governed preparation is unavailable in this read-only surface.",
                parent=self,
            )
            return
        try:
            self.on_prepare_write(self.form_state())
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Governed Write", str(exc), parent=self)

    def _cancel(self) -> None:
        if self.on_cancel is not None:
            self.on_cancel()

    def _clear_lineage(self) -> None:
        self.plan_id_var.set("")
        self.draft_id_var.set("")

    def _select_run(self, _event: object | None = None) -> None:
        selection = self.run_list.curselection()
        if not selection:
            return
        result = self.results[selection[0]]
        self.selected_result = result
        self.plan_id_var.set(result.document_plan_id or result.plan_id)
        self.draft_id_var.set(result.draft_id)
        self._set_text(
            self.draft_text,
            result.draft_text or "No persisted draft belongs to this operation.",
        )
        nodes = result.graph_nodes[:MAX_GRAPH_NODES]
        node_ids = {node.node_id for node in nodes}
        edges = tuple(
            edge
            for edge in result.graph_edges[:MAX_GRAPH_EDGES]
            if edge.source in node_ids and edge.target in node_ids
        )
        self.graph_view.set_graph(nodes, edges)
        graph_details = {
            "request_id": result.request_id,
            "plan_id": result.document_plan_id or result.plan_id,
            "draft_id": result.draft_id,
            "selected_path_id": result.selected_path_id,
            "rendered_nodes": len(nodes),
            "canonical_nodes": len(result.graph_nodes),
            "rendered_edges": len(edges),
            "canonical_edges": len(result.graph_edges),
            "argument_graph": result.argument_graph,
        }
        self._set_text(
            self.argument_text,
            json.dumps(safe_projection(graph_details), indent=2, sort_keys=True, ensure_ascii=False),
        )
        self.audit_status_var.set(f"Audit: {result.audit_status}")
        self._render_audit(result)
        self._update_prepare_state()
        if result.source_paths:
            source_path = result.source_paths[0]
            values = tuple(self.source_choice["values"])
            if source_path in values:
                self.source_choice.current(values.index(source_path))
                self._select_source()

    def _select_sentence(self, _event: object | None = None) -> None:
        result = self.selected_result
        if result is None:
            return
        try:
            offset = int(self.draft_text.count("1.0", "insert", "chars")[0])
        except (tk.TclError, TypeError, ValueError):
            return
        trace = next((item for item in result.sentence_traces if item.start <= offset <= item.end), None)
        self.draft_text.tag_remove("selected_claim", "1.0", "end")
        if trace is None:
            return
        self.draft_text.tag_add(
            "selected_claim",
            f"1.0 + {trace.start} chars",
            f"1.0 + {trace.end} chars",
        )
        claim_node = next(
            (node for node in result.graph_nodes if node.object_id == trace.claim_id or node.node_id == trace.claim_id),
            None,
        )
        if claim_node is not None:
            self.graph_view.select(claim_node.node_id, notify=False)
        details = {
            "section": trace.section_heading,
            "claim_id": trace.claim_id,
            "evidence_ids": trace.evidence_ids,
            "reasoning_edge_ids": trace.reasoning_edge_ids,
            "qualification_ids": trace.qualification_ids,
        }
        self._set_text(self.argument_text, json.dumps(details, indent=2, sort_keys=True))
        self._show_trace_evidence(trace.evidence_ids)

    def _select_graph_node(self, node: GraphNode) -> None:
        self._set_text(
            self.argument_text,
            json.dumps(safe_projection(node.data), indent=2, sort_keys=True, ensure_ascii=False),
        )
        result = self.selected_result
        if result is None:
            return
        claim_id = node.object_id or node.node_id
        trace = next((item for item in result.sentence_traces if item.claim_id == claim_id), None)
        if trace is not None:
            self.draft_text.tag_remove("selected_claim", "1.0", "end")
            self.draft_text.tag_add(
                "selected_claim",
                f"1.0 + {trace.start} chars",
                f"1.0 + {trace.end} chars",
            )
            self.draft_text.see(f"1.0 + {trace.start} chars")
            self._show_trace_evidence(trace.evidence_ids)
            return
        evidence_id = str(node.data.get("evidence_artifact_id", ""))
        reference = result.reference(evidence_id)
        if reference is not None:
            self._show_reference(reference.reference_span_id)

    def _show_trace_evidence(self, evidence_ids: tuple[str, ...]) -> None:
        result = self.selected_result
        if result is None:
            return
        references = [result.reference(identifier) for identifier in evidence_ids]
        references = [reference for reference in references if reference is not None]
        if not references:
            self._set_text(
                self.source_text,
                "No exact source-bound reference is stored for this sentence trace.",
            )
            return
        self._show_reference(references[0].reference_span_id)

    def _show_reference(self, reference_id: str) -> None:
        result = self.selected_result
        if result is None:
            return
        reference = result.reference(reference_id)
        if reference is None:
            self._set_text(self.source_text, f"Missing reference projection: {reference_id}")
            return
        evidence_link = next(
            (
                link
                for link in result.argument_graph.get("evidence_links", ())
                if str(link.get("evidence_artifact_id", "")) == reference_id
            ),
            {},
        )
        source_id = str(evidence_link.get("source_document_id", ""))
        candidate_pages = tuple(page for page in self.pages if page.source_document_id == source_id)
        if not candidate_pages and len(result.source_document_ids) == 1:
            candidate_pages = tuple(
                page for page in self.pages if page.source_document_id == result.source_document_ids[0]
            )
        if candidate_pages:
            source_path = candidate_pages[0].source_path
            values = tuple(self.source_choice["values"])
            if source_path in values:
                self.source_choice.current(values.index(source_path))
                self._select_source()
                page_number = next(
                    (
                        page.physical_page_number
                        for page in candidate_pages
                        if reference.verbatim_text and reference.verbatim_text in page.text
                    ),
                    candidate_pages[0].physical_page_number,
                )
                page_index = next(
                    (
                        index
                        for index, page in enumerate(self._selected_pages)
                        if page.physical_page_number == page_number
                    ),
                    0,
                )
                self.page_choice.current(page_index)
                self._select_page()
        payload = {
            "reference_span_id": reference.reference_span_id,
            "anchor_id": reference.anchor_id,
            "reference_kind": reference.reference_kind,
            "verbatim_text": reference.verbatim_text,
            "bounded_context": reference.bounded_context,
            "locator": reference.locator_display,
            "extraction_confidence": reference.extraction_confidence,
            "verification_status": reference.verification_status,
            "verification_failures": reference.verification_failures,
            "source_document_id": source_id,
        }
        current = self.source_text.get("1.0", "end-1c")
        self._set_text(
            self.source_text,
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n\n" + current,
        )

    def _select_source(self, _event: object | None = None) -> None:
        source_path = self.source_choice.get()
        self._selected_pages = tuple(page for page in self.pages if page.source_path == source_path)
        self.page_choice["values"] = tuple(page.display_page_label for page in self._selected_pages)
        if self._selected_pages:
            self.page_choice.current(0)
            self._select_page()

    def _select_page(self, _event: object | None = None) -> None:
        index = self.page_choice.current()
        if not self._selected_pages or index < 0:
            return
        page = self._selected_pages[index]
        header = (
            f"{page.title}\n"
            f"path={page.source_path}\n"
            f"source_document_id={page.source_document_id}\n"
            f"page={page.display_page_label} physical_index={page.physical_page_index} "
            f"physical_number={page.physical_page_number}\n"
            f"layer={page.text_layer_kind} confidence={page.extraction_confidence}/10000 "
            f"ocr={page.ocr_status}\n"
            f"freshness={page.freshness} media_type={page.media_type} bytes={page.byte_size}\n"
            f"sha256={page.content_sha256}\n\n"
        )
        source_text = page.text
        if len(source_text) > MAX_DISPLAYED_SOURCE_CHARACTERS:
            source_text = (
                source_text[:MAX_DISPLAYED_SOURCE_CHARACTERS]
                + "\n\n[source display truncated at the evidence-reader character limit]"
            )
        self._set_text(self.source_text, header + source_text)
        self._render_pdf_page(page)

    def _render_pdf_page(self, page: SourcePageProjection) -> None:
        if page.media_type != "application/pdf" or page.physical_page_index < 0:
            self._clear_preview("This source has no fixed-layout PDF page preview.")
            return
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError:
            self._clear_preview("Optional PDF preview is unavailable. Install formal-writing-pdf support.")
            return
        path = (self.repository_root / page.source_path).resolve()
        try:
            path.relative_to(self.repository_root)
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("PDF exceeds the 32 MiB preview limit")
            with fitz.open(path) as document:
                if page.physical_page_index >= document.page_count:
                    raise ValueError("persisted page index is outside the current PDF")
                pdf_page = document.load_page(page.physical_page_index)
                rectangle = pdf_page.rect
                pixels = max(1.0, float(rectangle.width) * float(rectangle.height))
                scale = min(1.5, max(0.25, (MAX_PDF_PREVIEW_PIXELS / pixels) ** 0.5))
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                if pixmap.width * pixmap.height > MAX_PDF_PREVIEW_PIXELS:
                    raise ValueError("rendered PDF page exceeds the preview pixel limit")
                image = tk.PhotoImage(data=pixmap.tobytes("ppm"), format="PPM")
            self._pdf_image = image
            self.preview_label.configure(image=image, text="", compound="center")
        except (OSError, RuntimeError, ValueError, tk.TclError) as exc:
            self._clear_preview(f"PDF preview unavailable: {type(exc).__name__}: {exc}")

    def _clear_preview(self, message: str) -> None:
        self._pdf_image = None
        self.preview_label.configure(image="", text=message)

    def _render_audit(self, result: FormalWritingResultProjection | None) -> None:
        self.audit_tree.delete(*self.audit_tree.get_children())
        if result is None:
            self._selected_algorithm_ids = ()
            self.algorithms_button.configure(state="disabled")
            self._set_text(self.audit_text, "No canonical audit is selected.")
            return
        audit = result.audit
        values = (
            ("Audit status", audit.status),
            ("Audit ID", audit.audit_id or "missing"),
            ("Claim support", f"{audit.claim_support_rate_bp / 100:.2f}%"),
            ("Evidence coverage", f"{audit.evidence_coverage_bp / 100:.2f}%"),
            ("Semantic consistency", f"{audit.semantic_consistency_bp / 100:.2f}%"),
            ("Argument connectivity", f"{audit.argument_connectivity_bp / 100:.2f}%"),
            ("Unsupported claim rate", f"{audit.unsupported_claim_rate_bp / 100:.2f}%"),
            ("Counterargument coverage", f"{audit.counterargument_coverage_bp / 100:.2f}%"),
            ("Qualification adequacy", f"{audit.qualification_adequacy_bp / 100:.2f}%"),
            ("Citation traceability", f"{audit.citation_traceability_bp / 100:.2f}%"),
        )
        for index, value in enumerate(values):
            self.audit_tree.insert("", "end", iid=f"metric:{index}", values=value)
        for claim_id in audit.unsupported_claim_ids:
            self.audit_tree.insert(
                "",
                "end",
                iid=f"claim:{claim_id}",
                values=("Unsupported claim", claim_id),
            )
        for index, code in enumerate(audit.graph_issue_codes):
            self.audit_tree.insert(
                "",
                "end",
                iid=f"issue:{index}",
                values=("Graph issue", code),
            )
        details = {
            "audit": result.writing_audit,
            "integrity_report": result.integrity_report,
            "certificate": result.certificate,
            "limitations": result.limitations,
            "novelty_assessments": result.novelty_assessments,
            "reasoning_algorithm_proposal": result.reasoning_algorithm_proposal,
            "reasoning_paths": result.reasoning_paths,
            "selected_reasoning_path": result.selected_reasoning_path,
        }
        selected_path = result.selected_reasoning_path
        self._selected_algorithm_ids = tuple(
            str(item) for item in selected_path.get("source_algorithm_ids", ()) if str(item)
        )
        self.algorithms_button.configure(
            state=(
                "normal"
                if self.on_show_algorithms is not None and self._selected_algorithm_ids
                else "disabled"
            )
        )
        for index, check in enumerate(audit.performed_checks):
            self.audit_tree.insert(
                "",
                "end",
                iid=f"check:{index}",
                values=("Performed check", check),
            )
        for index, limitation in enumerate((*audit.limitations, *result.limitations)):
            self.audit_tree.insert(
                "",
                "end",
                iid=f"limitation:{index}",
                values=("Limitation", limitation),
            )
        for index, novelty in enumerate(result.novelty_assessments):
            self.audit_tree.insert(
                "",
                "end",
                iid=f"novelty:{index}",
                values=("Novelty status", str(novelty.get("status", ""))),
            )
        if selected_path:
            self.audit_tree.insert(
                "",
                "end",
                iid="reasoning-path:selected",
                values=(
                    "Selected reasoning path",
                    f"{selected_path.get('pattern_name', '')} · "
                    f"{int(selected_path.get('total_score_bp', 0)) / 100:.2f}%",
                ),
            )
        if result.reasoning_algorithm_proposal:
            self.audit_tree.insert(
                "",
                "end",
                iid="algorithm-proposal:selected",
                values=(
                    "Algorithm proposal status",
                    str(result.reasoning_algorithm_proposal.get("status", "")),
                ),
            )
        self._set_text(
            self.audit_text,
            json.dumps(safe_projection(details), indent=2, sort_keys=True, ensure_ascii=False),
        )

    def _select_audit_finding(self, _event: object | None = None) -> None:
        selection = self.audit_tree.selection()
        if not selection or self.selected_result is None:
            return
        item_id = selection[0]
        if not item_id.startswith("claim:"):
            if item_id.startswith("issue:"):
                issue_index = int(item_id.removeprefix("issue:"))
                issues = tuple(self.selected_result.argument_graph.get("issues", ()) or ())
                if issue_index < len(issues):
                    subject_ids = tuple(issues[issue_index].get("subject_ids", ()) or ())
                    if subject_ids:
                        self._select_claim_or_graph_object(str(subject_ids[0]))
            return
        self._select_claim_or_graph_object(item_id.removeprefix("claim:"))

    def _select_claim_or_graph_object(self, claim_id: str) -> None:
        if self.selected_result is None:
            return
        node = next(
            (
                item
                for item in self.selected_result.graph_nodes
                if item.node_id == claim_id or item.object_id == claim_id
            ),
            None,
        )
        if node is not None:
            self.graph_view.select(node.node_id)

    def _show_algorithms(self) -> None:
        if self.on_show_algorithms is not None and self._selected_algorithm_ids:
            self.on_show_algorithms(self._selected_algorithm_ids)

    def _copy_locator(self) -> None:
        if not self._selected_pages or self.page_choice.current() < 0:
            return
        page = self._selected_pages[self.page_choice.current()]
        locator = (
            f"{page.source_path}#page={page.display_page_label};"
            f"physical={page.physical_page_number};sha256={page.content_sha256}"
        )
        self.clipboard_clear()
        self.clipboard_append(locator)
        self.status_var.set("Copied exact source locator")

    def _find_in_focused_text(self, event: tk.Event | None = None) -> str:
        widget = event.widget if event is not None else self.focus_get()
        if not isinstance(widget, tk.Text):
            return "break"
        query = simpledialog.askstring("Find", "Find text:", parent=self)
        widget.tag_remove("formal_find", "1.0", "end")
        if not query:
            widget.focus_set()
            return "break"
        start = widget.search(query, "1.0", "end", nocase=True)
        if start:
            end = f"{start} + {len(query)} chars"
            widget.tag_configure("formal_find", background="#b8e3ff", foreground="#111111")
            widget.tag_add("formal_find", start, end)
            widget.mark_set("insert", start)
            widget.see(start)
        else:
            self.status_var.set(f"Text not found: {query}")
        widget.focus_set()
        return "break"

    def _add_files(self, widget: tk.Listbox, kind: str) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title=f"Select formal-writing {kind} files",
            initialdir=self.repository_root,
            filetypes=(("Supported documents", " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED_SOURCE_SUFFIXES))), ("All files", "*")),
        )
        self._add_paths(widget, tuple(paths))

    def _add_folder(self, widget: tk.Listbox, kind: str) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title=f"Select formal-writing {kind} folder",
            initialdir=self.repository_root,
            mustexist=True,
        )
        if not selected:
            return
        root = Path(selected).resolve()
        try:
            root.relative_to(self.repository_root)
        except ValueError:
            messagebox.showerror(
                "Formal Writing",
                "Selected folders must be inside the workspace.",
                parent=self,
            )
            return
        paths = tuple(
            path
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
            and not path.is_symlink()
        )
        self._add_paths(widget, tuple(str(path) for path in paths))

    def _add_paths(self, widget: tk.Listbox, paths: tuple[str, ...]) -> None:
        existing = list(self._list_values(widget))
        total_bytes = sum(
            (self.repository_root / path).stat().st_size
            for path in existing
            if (self.repository_root / path).is_file()
        )
        for value in paths:
            unresolved = Path(value).expanduser()
            if unresolved.is_symlink():
                messagebox.showerror(
                    "Formal Writing",
                    f"Input symlinks are not supported: {value}",
                    parent=self,
                )
                continue
            path = unresolved.resolve()
            try:
                relative = path.relative_to(self.repository_root).as_posix()
            except ValueError:
                messagebox.showerror(
                    "Formal Writing",
                    f"Input is outside the workspace: {value}",
                    parent=self,
                )
                continue
            if path.suffix.casefold() not in SUPPORTED_SOURCE_SUFFIXES:
                messagebox.showerror(
                    "Formal Writing",
                    f"Unsupported source format: {path.suffix or '(none)'}",
                    parent=self,
                )
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                messagebox.showerror("Formal Writing", str(exc), parent=self)
                continue
            if size > MAX_FORMAL_WRITING_INPUT_BYTES:
                messagebox.showerror(
                    "Formal Writing",
                    f"Input exceeds the individual size limit: {relative} ({size} bytes)",
                    parent=self,
                )
                continue
            if total_bytes + size > MAX_FORMAL_WRITING_TOTAL_INPUT_BYTES:
                messagebox.showerror(
                    "Formal Writing",
                    "Selected inputs exceed the total size limit.",
                    parent=self,
                )
                break
            if relative not in existing:
                existing.append(relative)
                total_bytes += size
            if len(existing) >= MAX_FORMAL_WRITING_INPUTS:
                if len(paths) > 1:
                    messagebox.showerror(
                        "Formal Writing",
                        f"Selected inputs are limited to {MAX_FORMAL_WRITING_INPUTS} files.",
                        parent=self,
                    )
                break
        self._replace_list(widget, tuple(sorted(existing)))

    def _choose_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Select governed output path",
            initialdir=self.repository_root,
            defaultextension=".md",
            filetypes=(("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*")),
        )
        if not selected:
            return
        path = Path(selected).expanduser().resolve()
        try:
            relative = path.relative_to(self.repository_root).as_posix()
        except ValueError:
            messagebox.showerror(
                "Governed Output",
                "Output paths must be inside the workspace.",
                parent=self,
            )
            return
        existing = list(self._list_values(self.output_list))
        if relative not in existing:
            existing.append(relative)
        self._replace_list(self.output_list, tuple(existing))

    def _choose_authority(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select exact-snapshot authority manifest",
            initialdir=self.repository_root,
            filetypes=(("JSON", "*.json"), ("All files", "*")),
        )
        if not selected:
            return
        authority_path = Path(selected).expanduser().resolve()
        self.set_authority_path(authority_path)
        if self.on_authority_selected is not None:
            self.on_authority_selected(authority_path)

    def _remove_selected(self, widget: tk.Listbox) -> None:
        values = list(self._list_values(widget))
        for index in reversed(widget.curselection()):
            del values[index]
        self._replace_list(widget, tuple(values))

    def _refresh_diagnostics(self) -> None:
        self.diagnostic_list.delete(0, "end")
        for diagnostic in self.diagnostics:
            text = f"{diagnostic.category}: {diagnostic.path.name}: {diagnostic.message}"
            self.diagnostic_list.insert("end", text[:2_000])
        if not self.diagnostics:
            self.diagnostic_list.insert("end", "No projection diagnostics")

    def _append_runtime_diagnostic(self, event: FormalWritingGuiEvent) -> None:
        payload = safe_projection(
            {
                "event": event.event_type.value,
                "operation": event.operation,
                "phase": event.phase,
                "error_type": event.error_type,
                "message": event.message,
                "details": dict(event.details),
            },
            max_string_characters=2_000,
        )
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        self.diagnostic_list.insert(0, text[:2_000])

    def _export_diagnostics(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Export formal-writing diagnostics",
            initialdir=self.repository_root,
            defaultextension=".json",
            filetypes=(("JSON", "*.json"),),
        )
        if not selected:
            return
        payload = safe_projection(
            {
                "workspace": str(self.repository_root),
                "result_count": len(self.results),
                "source_page_count": len(self.pages),
                "diagnostics": self.diagnostics,
                "selected_request_id": self.selected_result.request_id if self.selected_result else "",
            },
            max_items=1_000,
            max_string_characters=2_000,
        )
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        if len(text) > MAX_DIAGNOSTIC_CHARACTERS:
            text = text[:MAX_DIAGNOSTIC_CHARACTERS] + "\n[diagnostic report truncated]\n"
        destination = Path(selected).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        self.status_var.set(f"Exported diagnostic report: {destination.name}")


__all__ = [
    "AuthorityCallback",
    "AlgorithmsCallback",
    "FormalWritingView",
    "PrepareWriteCallback",
    "SubmitCallback",
    "optional_capabilities",
]
