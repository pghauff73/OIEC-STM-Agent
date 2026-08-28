from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ourd.egcf.models import AssuranceCase

from ..assurance_exports import assurance_html, assurance_json, assurance_markdown
from ..read_models import ReadOnlyEGCFRepository
from ..widgets.json_view import JsonView

__all__ = [
    "AssuranceRecordView",
    "assurance_html",
    "assurance_json",
    "assurance_markdown",
]


class AssuranceRecordView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        *,
        on_object_selected: Callable[[str], None] | None = None,
        on_export: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        self.on_export = on_export
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Completed-task assurance records").pack(side="left", padx=4)
        for label, format_name in (("JSON", "json"), ("Markdown", "markdown"), ("HTML", "html")):
            ttk.Button(
                toolbar,
                text=f"Export {label}",
                command=lambda value=format_name: self._export(value),
            ).pack(side="right", padx=2)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("conclusion", "created"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Subject")
        self.tree.heading("conclusion", text="Conclusion")
        self.tree.heading("created", text="Created")
        self.details = JsonView(paned)
        paned.add(self.tree, weight=2)
        paned.add(self.details, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._records: dict[str, AssuranceCase] = {}
        self._selected_id = ""
        self.refresh()

    def refresh(self) -> None:
        self._records.clear()
        self._selected_id = ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        records = [
            record
            for record in self.repository.list("assurance-case")
            if isinstance(record, AssuranceCase)
        ]
        records.sort(key=lambda item: (item.created_at, item.object_id), reverse=True)
        for record in records:
            self._records[record.object_id] = record
            self.tree.insert(
                "",
                "end",
                iid=record.object_id,
                text=record.subject_id,
                values=(record.conclusion, record.created_at),
            )

    def _selected(self, event: tk.Event) -> None:
        del event
        selection = self.tree.selection()
        if not selection:
            return
        self._selected_id = selection[0]
        record = self._records[self._selected_id]
        self.details.set_value(
            {
                "object_id": record.object_id,
                "subject_id": record.subject_id,
                "goal": record.top_claim,
                "verdict": record.conclusion,
                "evidence": record.supporting_evidence,
                "refuting_evidence": record.refuting_evidence,
                "invariants": record.invariant_ids,
                "decisions": record.decision_ids,
                "approval": record.approval_facts,
                "rollback": record.rollback_argument,
                "gaps": record.gaps,
                "conflicts": record.conflicts,
                "uncertainties": record.uncertainties,
            }
        )
        if self.on_object_selected is not None:
            self.on_object_selected(record.object_id)

    def _export(self, format_name: str) -> None:
        if self._selected_id and self.on_export is not None:
            self.on_export(self._selected_id, format_name)
