from __future__ import annotations

import tkinter as tk
from dataclasses import asdict, is_dataclass
from tkinter import ttk
from typing import Callable, Iterable

from ..read_models import ReadOnlyEGCFRepository
from ..widgets.json_view import JsonView


class RecordBrowser(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        object_types: Iterable[str],
        *,
        title: str = "Records",
        on_object_selected: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.object_types = tuple(object_types)
        self.on_object_selected = on_object_selected
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text=title).pack(side="left", padx=4)
        self.query = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        entry.bind("<KeyRelease>", lambda event: self.refresh())
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=4)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("type", "status"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Object")
        self.tree.heading("type", text="Type")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=320)
        self.tree.column("type", width=150, stretch=False)
        self.tree.column("status", width=110, stretch=False)
        self.details = JsonView(paned)
        paned.add(self.tree, weight=2)
        paned.add(self.details, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._records: dict[str, object] = {}
        self._selected_id = ""
        self.refresh()

    @staticmethod
    def _label(record: object) -> str:
        for attribute in (
            "name",
            "question",
            "subject_id",
            "algorithm_id",
            "plan_id",
            "workflow_id",
        ):
            value = getattr(record, attribute, "")
            if value:
                return str(value)
        return str(getattr(record, "object_id", "record"))

    def refresh(self) -> None:
        needle = self.query.get().strip().lower()
        self._records.clear()
        self._selected_id = ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        records = [
            record
            for object_type in self.object_types
            for record in self.repository.list(object_type)
        ]
        records.sort(key=lambda record: (record.object_type, record.object_id))
        for record in records:
            payload = asdict(record) if is_dataclass(record) else {}
            haystack = f"{record.object_id} {record.object_type} {payload}".lower()
            if needle and needle not in haystack:
                continue
            status = str(
                payload.get("status")
                or payload.get("conclusion")
                or payload.get("success")
                or ""
            )
            self._records[record.object_id] = record
            self.tree.insert(
                "",
                "end",
                iid=record.object_id,
                text=self._label(record),
                values=(record.object_type, status),
            )

    def _selected(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        object_id = selection[0]
        self._selected_id = object_id
        record = self._records[object_id]
        self.details.set_value({"object_id": object_id, "payload": asdict(record)})
        if self.on_object_selected is not None:
            self.on_object_selected(object_id)

    def selected_record(self) -> object | None:
        return self._records.get(self._selected_id)

    def show_details(self, value: object) -> None:
        self.details.set_value(value)
