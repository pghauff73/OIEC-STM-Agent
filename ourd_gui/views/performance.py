from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Mapping

from ..widgets.json_view import JsonView


class PerformanceView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        supplier: Callable[[], Mapping[str, Any]],
    ) -> None:
        super().__init__(master)
        self.supplier = supplier
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Bounded, non-authoritative GUI telemetry").pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="right", padx=4)
        self.details = JsonView(self)
        self.details.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        self.details.set_value(self.supplier())
