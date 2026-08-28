from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Mapping


def _summary(value: Any, maximum: int = 180) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = repr(value)
    else:
        text = str(value)
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


class PropertyGrid(ttk.Frame):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.tree = ttk.Treeview(
            self,
            columns=("value",),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Property")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=180, stretch=False)
        self.tree.column("value", width=420, stretch=True)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def set_properties(self, properties: Mapping[str, Any]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for key, value in properties.items():
            self.tree.insert("", "end", text=str(key), values=(_summary(value),))

