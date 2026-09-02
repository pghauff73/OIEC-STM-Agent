from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable, Iterable, Mapping

from ..styles import status_palette


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    layer: int
    order: int
    status: str = "neutral"
    subtitle: str = ""
    object_id: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    label: str = ""


class GraphView(ttk.Frame):
    NODE_WIDTH = 220
    NODE_HEIGHT = 82
    X_GAP = 90
    Y_GAP = 28
    MARGIN = 40

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_select: Callable[[GraphNode], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_select = on_select
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(toolbar, text="Zoom").pack(side="left", padx=(4, 2))
        for label, zoom in (("75%", 0.75), ("100%", 1.0), ("125%", 1.25)):
            ttk.Button(
                toolbar,
                text=label,
                width=5,
                command=lambda value=zoom: self.set_zoom(value),
            ).pack(side="left", padx=2)
        self.canvas = tk.Canvas(self, background="#f7f8fa", highlightthickness=0)
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._nodes: dict[str, GraphNode] = {}
        self._boxes: dict[str, tuple[float, float, float, float]] = {}
        self._item_to_node: dict[int, str] = {}
        self._focus_order: list[str] = []
        self._selected = ""
        self._zoom = 1.0
        self._node_list: list[GraphNode] = []
        self._edge_list: list[GraphEdge] = []
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Left>", lambda event: self._move_focus(-1))
        self.canvas.bind("<Right>", lambda event: self._move_focus(1))
        self.canvas.bind("<Up>", lambda event: self._move_focus(-1))
        self.canvas.bind("<Down>", lambda event: self._move_focus(1))
        self.canvas.bind("<Return>", lambda event: self._activate_selected())
        self.canvas.configure(takefocus=True)

    @classmethod
    def layout(
        cls,
        nodes: Iterable[GraphNode],
    ) -> dict[str, tuple[float, float, float, float]]:
        grouped: dict[int, list[GraphNode]] = {}
        for node in nodes:
            grouped.setdefault(node.layer, []).append(node)
        boxes: dict[str, tuple[float, float, float, float]] = {}
        for layer, layer_nodes in sorted(grouped.items()):
            for row, node in enumerate(sorted(layer_nodes, key=lambda item: (item.order, item.node_id))):
                x1 = cls.MARGIN + layer * (cls.NODE_WIDTH + cls.X_GAP)
                y1 = cls.MARGIN + row * (cls.NODE_HEIGHT + cls.Y_GAP)
                boxes[node.node_id] = (x1, y1, x1 + cls.NODE_WIDTH, y1 + cls.NODE_HEIGHT)
        return boxes

    def set_graph(
        self,
        nodes: Iterable[GraphNode],
        edges: Iterable[GraphEdge],
    ) -> None:
        self._node_list = list(nodes)
        self._edge_list = list(edges)
        self._render()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.5, min(float(zoom), 2.0))
        self._render()

    def _render(self) -> None:
        node_list = self._node_list
        edge_list = self._edge_list
        self._nodes = {node.node_id: node for node in node_list}
        self._focus_order = [
            node.node_id for node in sorted(node_list, key=lambda item: (item.layer, item.order, item.node_id))
        ]
        self._boxes = {
            node_id: tuple(value * self._zoom for value in box)
            for node_id, box in self.layout(node_list).items()
        }
        self.canvas.delete("all")
        self._item_to_node.clear()
        for edge in edge_list:
            source = self._boxes.get(edge.source)
            target = self._boxes.get(edge.target)
            if source is None or target is None:
                continue
            x1, y1 = source[2], (source[1] + source[3]) / 2
            x2, y2 = target[0], (target[1] + target[3]) / 2
            self.canvas.create_line(x1, y1, x2, y2, fill="#7a8088", width=2, arrow="last")
            if edge.label:
                self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2 - 8, text=edge.label, fill="#4f545b")
        for node in node_list:
            x1, y1, x2, y2 = self._boxes[node.node_id]
            background, foreground = status_palette(node.status)
            rectangle = self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=background,
                outline="#2f343a",
                width=2,
                tags=("node",),
            )
            label = self.canvas.create_text(
                (x1 + x2) / 2,
                y1 + 27,
                text=node.label,
                fill=foreground,
                width=self.NODE_WIDTH - 20,
                font=("TkDefaultFont", max(8, round(10 * self._zoom)), "bold"),
                tags=("node",),
            )
            subtitle = self.canvas.create_text(
                (x1 + x2) / 2,
                y1 + 57,
                text=node.subtitle,
                fill=foreground,
                width=self.NODE_WIDTH - 20,
                font=("TkDefaultFont", max(7, round(8 * self._zoom))),
                tags=("node",),
            )
            for item_id in (rectangle, label, subtitle):
                self._item_to_node[item_id] = node.node_id
        if self._boxes:
            maximum_x = max(box[2] for box in self._boxes.values()) + self.MARGIN
            maximum_y = max(box[3] for box in self._boxes.values()) + self.MARGIN
            self.canvas.configure(scrollregion=(0, 0, maximum_x, maximum_y))
        else:
            self.canvas.configure(scrollregion=(0, 0, 1, 1))
        if self._selected not in self._nodes:
            self._selected = ""

    def select(self, node_id: str, *, notify: bool = True) -> None:
        if node_id not in self._nodes:
            return
        self._selected = node_id
        self.canvas.delete("selection-outline")
        x1, y1, x2, y2 = self._boxes[node_id]
        self.canvas.create_rectangle(
            x1 - 4,
            y1 - 4,
            x2 + 4,
            y2 + 4,
            outline="#111111",
            width=3,
            dash=(5, 3),
            tags=("selection-outline",),
        )
        self.canvas.tag_raise("selection-outline")
        self.canvas.focus_set()
        if notify and self.on_select is not None:
            self.on_select(self._nodes[node_id])

    def _click(self, event: tk.Event) -> None:
        item_ids = self.canvas.find_overlapping(
            self.canvas.canvasx(event.x),
            self.canvas.canvasy(event.y),
            self.canvas.canvasx(event.x),
            self.canvas.canvasy(event.y),
        )
        for item_id in reversed(item_ids):
            node_id = self._item_to_node.get(item_id)
            if node_id:
                self.select(node_id)
                return

    def _move_focus(self, offset: int) -> str:
        if not self._focus_order:
            return "break"
        try:
            index = self._focus_order.index(self._selected)
        except ValueError:
            index = 0 if offset >= 0 else len(self._focus_order) - 1
        else:
            index = max(0, min(len(self._focus_order) - 1, index + offset))
        self.select(self._focus_order[index])
        return "break"

    def _activate_selected(self) -> str:
        if self._selected and self.on_select is not None:
            self.on_select(self._nodes[self._selected])
        return "break"
