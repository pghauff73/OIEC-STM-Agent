from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..state import GuiTask
from ..task_projections import domain_graph_for_task
from ..widgets.graph_view import GraphEdge, GraphNode, GraphView
from ..widgets.json_view import JsonView


class OURDGraphView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_object_selected: Callable[[str], None] | None = None,
        on_prepare_command: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_object_selected = on_object_selected
        self._raw_nodes: dict[str, dict] = {}
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.summary = ttk.Label(toolbar, text="No task selected")
        self.summary.pack(side="left", fill="x", expand=True, padx=4)
        if on_prepare_command is not None:
            for label, command in (
                ("Model Scope", "ourd model "),
                ("Impact Map", "ourd impact "),
                ("Show Exclusions", "ourd exclusions "),
            ):
                ttk.Button(
                    toolbar,
                    text=label,
                    command=lambda value=command: on_prepare_command(value),
                ).pack(side="left", padx=2)
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        self.graph = GraphView(paned, on_select=self._selected)
        self.details = JsonView(paned)
        paned.add(self.graph, weight=4)
        paned.add(self.details, weight=2)

    def set_task(self, task: GuiTask | None) -> None:
        if task is None:
            self.summary.configure(text="No task selected")
            self.graph.set_graph([], [])
            self.details.set_value({})
            return
        projection = domain_graph_for_task(task)
        self._raw_nodes = {
            _node_id(item, index): dict(item)
            for index, item in enumerate(projection.nodes)
        }
        order = {node_id: index for index, node_id in enumerate(self._raw_nodes)}
        nodes = [
            GraphNode(
                node_id=node_id,
                label=str(item.get("label") or item.get("name") or node_id),
                layer=0 if item.get("type") == "task" else 1,
                order=order[node_id],
                status="qualified" if projection.canonical_relationships else "neutral",
                subtitle=str(item.get("type", "object")),
                object_id=node_id if ":sha256:" in node_id else "",
                data=item,
            )
            for node_id, item in self._raw_nodes.items()
        ]
        edges = [
            GraphEdge(str(item["from"]), str(item["to"]), str(item.get("relation", "")))
            for item in projection.edges
            if str(item.get("from", "")) in self._raw_nodes
            and str(item.get("to", "")) in self._raw_nodes
        ]
        self.graph.set_graph(nodes, edges)
        authority = "canonical relations" if projection.canonical_relationships else "inferred GUI links"
        self.summary.configure(
            text=f"{len(nodes)} objects | {len(edges)} relations | {authority}"
        )
        self.details.set_value(
            {
                "source": projection.source,
                "canonical_relationships": projection.canonical_relationships,
                "task_id": task.task_id,
            }
        )

    def _selected(self, node: GraphNode) -> None:
        self.details.set_value(self._raw_nodes.get(node.node_id, node.data))
        if node.object_id and self.on_object_selected is not None:
            self.on_object_selected(node.object_id)


def _node_id(item: dict, index: int) -> str:
    return str(item.get("id") or item.get("object_id") or item.get("name") or f"node-{index}")
