from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..styles import status_palette


class StatusBadge(ttk.Label):
    def __init__(self, master: tk.Misc, text: str = "unknown", status: str = "neutral"):
        self._style_name = f"OURD.Badge.{id(self)}.TLabel"
        super().__init__(master, text=text, style=self._style_name, anchor="center", padding=(6, 2))
        self.set_status(status, text)

    def set_status(self, status: str, text: str | None = None) -> None:
        background, foreground = status_palette(status)
        style = ttk.Style(self)
        style.configure(
            self._style_name,
            background=background,
            foreground=foreground,
            relief="solid",
            borderwidth=1,
        )
        self.configure(text=text if text is not None else status.upper())

