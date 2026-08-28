from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ourd.egcf.models import CompiledWorkflow, ExecutionPlan, ExecutionRecord

from ..read_models import ReadOnlyEGCFRepository
from ..widgets.graph_view import GraphEdge, GraphNode, GraphView
from ..widgets.json_view import JsonView


class WorkflowView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        self.summary = ttk.Label(self, text="No workflow selected", padding=4)
        self.summary.pack(fill="x")
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        self.graph = GraphView(paned, on_select=self._selected_node)
        self.details = JsonView(paned)
        paned.add(self.graph, weight=4)
        paned.add(self.details, weight=2)
        self._nodes: dict[str, dict] = {}

    def set_workflow(self, compiled_workflow_id: str, execution_plan_id: str = "") -> None:
        if not compiled_workflow_id:
            self.summary.configure(text="No workflow selected")
            self.graph.set_graph([], [])
            self.details.set_value({})
            return
        compiled = self.repository.get(compiled_workflow_id)
        if not isinstance(compiled, CompiledWorkflow):
            raise TypeError(f"not a compiled workflow: {compiled_workflow_id}")
        plan = None
        if execution_plan_id:
            candidate = self.repository.get(execution_plan_id)
            if isinstance(candidate, ExecutionPlan):
                plan = candidate
        executions = [
            item
            for item in self.repository.list("execution")
            if isinstance(item, ExecutionRecord)
            and plan is not None
            and item.plan_id == plan.object_id
        ]
        status_by_node = {item.node_id: item.status.lower() for item in executions}
        order_index = {node_id: index for index, node_id in enumerate(compiled.execution_order)}
        nodes: list[GraphNode] = []
        self._nodes = {str(node["node_id"]): dict(node) for node in compiled.nodes}
        for node in compiled.nodes:
            node_id = str(node["node_id"])
            status = status_by_node.get(node_id, "neutral")
            if status == "completed":
                status = "completed"
            elif status == "simulated":
                status = "simulated"
            elif status in {"failed", "rolled_back", "partially_compensated"}:
                status = "failed"
            nodes.append(
                GraphNode(
                    node_id=node_id,
                    label=str(node["command_id"]),
                    layer=order_index.get(node_id, 0),
                    order=0,
                    status=status,
                    subtitle=f"{node.get('capability_level', '')} / {node.get('risk', '')}",
                    object_id=str(node.get("selection_id", "")),
                    data=node,
                )
            )
        edges = [
            GraphEdge(str(edge["from"]), str(edge["to"]))
            for edge in compiled.edges
        ]
        self.graph.set_graph(nodes, edges)
        self.summary.configure(
            text=(
                f"{compiled.workflow_id} | {compiled.capability_level} / {compiled.risk} | "
                f"approval {compiled.approval_policy} | graph {compiled.graph_hash[:12]}"
            )
        )
        self.details.set_value(
            {
                "compiled_workflow_id": compiled.object_id,
                "execution_plan_id": plan.object_id if plan else "",
                "payload": asdict(compiled),
                "executions": [asdict(item) for item in executions],
            }
        )

    def _selected_node(self, node: GraphNode) -> None:
        self.details.set_value(self._nodes.get(node.node_id, {}))
        if node.object_id and self.on_object_selected is not None:
            self.on_object_selected(node.object_id)

