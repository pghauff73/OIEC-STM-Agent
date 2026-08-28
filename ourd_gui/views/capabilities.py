from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk

from ourd.egcf.models import ExecutionPlan

from ..governance_models import build_capability_ladder
from ..read_models import ReadOnlyEGCFRepository
from ..widgets.json_view import JsonView


class CapabilityLadderView(ttk.Frame):
    def __init__(self, master: tk.Misc, repository: ReadOnlyEGCFRepository) -> None:
        super().__init__(master)
        self.repository = repository
        self.plan: ExecutionPlan | None = None
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="Authority = capability × evidence × approval",
        ).pack(side="left", padx=4, pady=4)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="right", padx=4)
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("description", "status"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Level")
        self.tree.heading("description", text="Capability class")
        self.tree.heading("status", text="Authority")
        self.tree.column("#0", width=70, stretch=False)
        self.tree.column("description", width=220)
        self.tree.column("status", width=110, stretch=False)
        self.details = JsonView(paned)
        paned.add(self.tree, weight=2)
        paned.add(self.details, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._levels = {}
        self.refresh()

    def set_plan(self, plan: ExecutionPlan | None) -> None:
        self.plan = plan
        self.refresh()

    def refresh(self) -> None:
        self._levels = {
            item.level: item
            for item in build_capability_ladder(self.repository, plan=self.plan)
        }
        for item in self.tree.get_children():
            self.tree.delete(item)
        for level, item in self._levels.items():
            self.tree.insert(
                "",
                "end",
                iid=level,
                text=level,
                values=(item.description, item.status.upper()),
            )
        if self._levels:
            first = next(iter(self._levels))
            self.tree.selection_set(first)
            self._show(first)

    def _selected(self, event: tk.Event) -> None:
        del event
        selection = self.tree.selection()
        if selection:
            self._show(selection[0])

    def _show(self, level: str) -> None:
        item = self._levels[level]
        self.details.set_value(
            {
                **asdict(item),
                "active_plan_id": self.plan.object_id if self.plan is not None else "",
                "gui_can_grant": False,
            }
        )
