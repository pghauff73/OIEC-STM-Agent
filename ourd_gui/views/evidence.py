from __future__ import annotations

import tkinter as tk
from dataclasses import asdict, is_dataclass
from tkinter import ttk
from typing import Callable, Iterable

from ..evidence_graph import evidence_graph
from ..governance_models import build_evidence_dashboard
from ..read_models import ReadOnlyEGCFRepository
from ..widgets.coverage_dashboard import CoverageDashboard
from ..widgets.graph_view import GraphNode, GraphView
from ..widgets.json_view import JsonView


class EvidenceView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
        on_export: Callable[[tuple[str, ...], str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        self.on_export = on_export
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Evidence coverage and exact immutable records").pack(
            side="left", padx=4
        )
        for label, format_name in (("JSON", "json"), ("Markdown", "markdown")):
            ttk.Button(
                toolbar,
                text=f"Export {label}",
                command=lambda value=format_name: self._export(value),
            ).pack(side="right", padx=2)
        self.dashboard = CoverageDashboard(self)
        self.dashboard.pack(fill="x")
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        records_tab = ttk.Frame(tabs)
        paned = ttk.PanedWindow(records_tab, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(paned, exportselection=False, width=46)
        self.details = JsonView(paned)
        paned.add(self.listbox, weight=2)
        paned.add(self.details, weight=3)
        self.graph = GraphView(tabs, on_select=self._graph_selected)
        tabs.add(records_tab, text="Records")
        tabs.add(self.graph, text="Evidence Graph")
        self.listbox.bind("<<ListboxSelect>>", self._selected)
        self._ids: list[str] = []

    def set_evidence_ids(self, identifiers: Iterable[str]) -> None:
        self._ids = list(dict.fromkeys(str(item) for item in identifiers if item))
        model = build_evidence_dashboard(self.repository, self._ids)
        self.dashboard.set_model(model)
        graph_nodes, graph_edges = evidence_graph(self.repository, self._ids)
        self.graph.set_graph(graph_nodes, graph_edges)
        self.listbox.delete(0, "end")
        for identifier in self._ids:
            self.listbox.insert("end", identifier)
        if self._ids:
            self.listbox.selection_set(0)
            self._show(0)
        else:
            self.details.set_value({"message": "No evidence references"})

    def _selected(self, event: tk.Event) -> None:
        selection = self.listbox.curselection()
        if selection:
            self._show(selection[0])

    def _show(self, index: int) -> None:
        identifier = self._ids[index]
        try:
            record = self.repository.get(identifier)
            payload = asdict(record) if is_dataclass(record) else record
        except Exception as exc:
            payload = {"object_id": identifier, "error": f"{type(exc).__name__}: {exc}"}
        self.details.set_value({"object_id": identifier, "payload": payload})
        if self.on_object_selected is not None:
            self.on_object_selected(identifier)

    def _export(self, format_name: str) -> None:
        if self._ids and self.on_export is not None:
            self.on_export(tuple(self._ids), format_name)

    def _graph_selected(self, node: GraphNode) -> None:
        if node.object_id and self.on_object_selected is not None:
            self.on_object_selected(node.object_id)
