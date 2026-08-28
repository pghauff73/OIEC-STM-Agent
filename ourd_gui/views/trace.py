from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..events import AgentEvent
from ..widgets.json_view import JsonView


class TraceTimelineView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_object_selected: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self.on_object_selected = on_object_selected
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open First Object", command=self._open_first_object).pack(
            side="right", padx=4, pady=4
        )
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("sequence", "source", "task"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Event")
        self.tree.heading("sequence", text="#")
        self.tree.heading("source", text="Source")
        self.tree.heading("task", text="Task")
        self.tree.column("#0", width=250)
        self.tree.column("sequence", width=60, stretch=False)
        self.tree.column("source", width=80, stretch=False)
        self.tree.column("task", width=110, stretch=False)
        self.details = JsonView(paned)
        paned.add(self.tree, weight=2)
        paned.add(self.details, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._events: dict[str, AgentEvent] = {}
        self._selected_event_id = ""

    def append(self, event: AgentEvent) -> None:
        self._events[event.event_id] = event
        self.tree.insert(
            "",
            "end",
            iid=event.event_id,
            text=event.event_type.value,
            values=(event.sequence, event.source, event.task_id[:8]),
        )
        self.tree.see(event.event_id)

    def set_events(self, events: list[AgentEvent]) -> None:
        self._events.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for event in events:
            self.append(event)

    def _selected(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection:
            self._selected_event_id = selection[0]
            self.details.set_value(self._events[selection[0]].to_dict())

    def _open_first_object(self) -> None:
        event = self._events.get(self._selected_event_id)
        if event is not None and event.object_ids and self.on_object_selected is not None:
            self.on_object_selected(event.object_ids[0])
