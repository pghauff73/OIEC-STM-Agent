from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..model_backend import ModelBackendInfo
from ..widgets.json_view import JsonView
from ..widgets.status_badge import StatusBadge


class ModelBackendView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        info: ModelBackendInfo,
        on_prepare_preflight: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.health = StatusBadge(toolbar, info.health.upper(), "neutral")
        self.health.pack(side="left", padx=4, pady=4)
        ttk.Label(toolbar, text="Model output is advisory, never approval authority.").pack(
            side="left", padx=4
        )
        if on_prepare_preflight is not None:
            ttk.Button(
                toolbar,
                text="Prepare Health Check",
                command=on_prepare_preflight,
            ).pack(side="right", padx=4)
        self.details = JsonView(self)
        self.details.pack(fill="both", expand=True)
        self.set_info(info)

    def set_info(self, info: ModelBackendInfo) -> None:
        self.details.set_value(info.to_dict())
