from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..read_models import ReadOnlyEGCFRepository
from ..replay_models import compare_tasks
from ..state import GuiState
from ..widgets.json_view import JsonView


class SessionComparisonView(ttk.Frame):
    def __init__(self, master: tk.Misc, repository: ReadOnlyEGCFRepository) -> None:
        super().__init__(master)
        self.repository = repository
        self.state = GuiState()
        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Run A").pack(side="left")
        self.left = ttk.Combobox(toolbar, state="readonly", width=30)
        self.left.pack(side="left", padx=4)
        ttk.Label(toolbar, text="Run B").pack(side="left")
        self.right = ttk.Combobox(toolbar, state="readonly", width=30)
        self.right.pack(side="left", padx=4)
        ttk.Button(toolbar, text="Compare", command=self.compare).pack(side="left", padx=4)
        self.details = JsonView(self)
        self.details.pack(fill="both", expand=True)
        self._task_ids: list[str] = []

    def set_state(self, state: GuiState) -> None:
        self.state = state
        self._task_ids = list(state.tasks)
        labels = [f"{task_id[:8]} — {state.tasks[task_id].title}" for task_id in self._task_ids]
        self.left["values"] = labels
        self.right["values"] = labels
        if labels and not self.left.get():
            self.left.current(0)
        if len(labels) > 1 and not self.right.get():
            self.right.current(1)
        elif labels and not self.right.get():
            self.right.current(0)

    def compare(self) -> None:
        left_index = self.left.current()
        right_index = self.right.current()
        if left_index < 0 or right_index < 0:
            return
        left = self.state.tasks[self._task_ids[left_index]]
        right = self.state.tasks[self._task_ids[right_index]]
        self.details.set_value(compare_tasks(self.repository, left, right))
