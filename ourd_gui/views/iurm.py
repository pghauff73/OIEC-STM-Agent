from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ..state import GuiTask
from ..task_projections import iurm_for_task
from ..widgets.json_view import JsonView


class IURMDimensionView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_prepare_command: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.summary = ttk.Label(toolbar, text="No returned IURM design")
        self.summary.pack(side="left", fill="x", expand=True, padx=4)
        if on_prepare_command is not None:
            for label, command in (
                ("Add Dimension", "iurm dimensions "),
                ("Mark Boundary", "iurm vary boundary "),
                ("Generate OFAT", "experiment ofat "),
                ("Generate Pairwise", "experiment covering "),
                ("Show MVD", "iurm mvd "),
            ):
                ttk.Button(
                    toolbar,
                    text=label,
                    command=lambda value=command: on_prepare_command(value),
                ).pack(side="left", padx=2)
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("baseline", "values", "coverage", "interactions"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Dimension")
        for name in ("baseline", "values", "coverage", "interactions"):
            self.tree.heading(name, text=name.title())
        self.details = JsonView(paned)
        paned.add(self.tree, weight=3)
        paned.add(self.details, weight=2)
        self._dimensions = {}
        self.tree.bind("<<TreeviewSelect>>", self._selected)

    def set_task(self, task: GuiTask | None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._dimensions = {}
        if task is None:
            self.summary.configure(text="No returned IURM design")
            self.details.set_value({})
            return
        projection = iurm_for_task(task)
        for dimension in projection.dimensions:
            self._dimensions[dimension.name] = dimension
            self.tree.insert(
                "",
                "end",
                iid=dimension.name,
                text=dimension.name,
                values=(
                    repr(dimension.baseline),
                    repr(list(dimension.values)),
                    dimension.coverage,
                    ", ".join(dimension.interactions),
                ),
            )
        self.summary.configure(
            text=(
                f"{len(projection.dimensions)} dimensions | "
                f"MVD: {', '.join(projection.minimum_viable_dimensions) or 'not returned'}"
            )
        )
        self.details.set_value(
            {
                "minimum_viable_dimensions": projection.minimum_viable_dimensions,
                "source_outputs": projection.source_outputs,
                "coverage_is_core_reported": True,
            }
        )

    def _selected(self, event: tk.Event) -> None:
        del event
        selection = self.tree.selection()
        if selection:
            self.details.set_value(asdict(self._dimensions[selection[0]]))
