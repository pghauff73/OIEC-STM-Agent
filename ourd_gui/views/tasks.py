from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Mapping

from ..paging import incremental_window
from ..state import GuiTask


class TaskListView(ttk.Frame):
    PAGE_SIZE = 500

    def __init__(self, master: tk.Misc, on_select: Callable[[str], None]):
        super().__init__(master)
        self.on_select = on_select
        self._tasks: Mapping[str, GuiTask] = {}
        self._selected_task_id = ""
        self._visible_limit = self.PAGE_SIZE
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.count_label = ttk.Label(toolbar, text="0 tasks")
        self.count_label.pack(side="left", padx=4)
        self.load_more = ttk.Button(toolbar, text="Load More", command=self._load_more)
        self.load_more.pack(side="right", padx=4)
        self.tree = ttk.Treeview(self, columns=("status",), show="tree headings")
        self.tree.heading("#0", text="Task")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=210, stretch=True)
        self.tree.column("status", width=90, stretch=False)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._selected)

    def set_tasks(self, tasks: Mapping[str, GuiTask], selected_task_id: str = "") -> None:
        self._tasks = tasks
        self._selected_task_id = selected_task_id
        self._render()

    def _render(self) -> None:
        visible_ids = incremental_window(
            self._tasks,
            limit=self._visible_limit,
            selected_id=self._selected_task_id,
        )
        existing = set(self.tree.get_children())
        for task_id in visible_ids:
            task = self._tasks[task_id]
            values = (task.status,)
            if task_id in existing:
                self.tree.item(task_id, text=task.title, values=values)
                existing.remove(task_id)
            else:
                self.tree.insert("", "end", iid=task_id, text=task.title, values=values)
        for task_id in existing:
            self.tree.delete(task_id)
        if self._selected_task_id and self.tree.exists(self._selected_task_id):
            self.tree.selection_set(self._selected_task_id)
            self.tree.see(self._selected_task_id)
        total = len(self._tasks)
        self.count_label.configure(text=f"Showing {len(visible_ids)} of {total} tasks")
        self.load_more.configure(
            state="normal" if len(visible_ids) < total else "disabled"
        )

    def _load_more(self) -> None:
        self._visible_limit += self.PAGE_SIZE
        self._render()

    def _selected(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection:
            self.on_select(selection[0])
