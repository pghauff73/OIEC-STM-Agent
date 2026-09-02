from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..reasoning_projection import load_reasoning_projection, write_reasoning_export
from ..widgets.json_view import JsonView


class ReasoningInspectorView(ttk.Frame):
    def __init__(self, master: tk.Misc, repository_root: Path) -> None:
        super().__init__(master)
        self.repository_root = repository_root
        self.payload: dict = {}
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.summary = ttk.Label(toolbar, text="No OIEC-SR episode")
        self.summary.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export JSON", command=lambda: self._export("json")).pack(
            side="left", padx=2
        )
        ttk.Button(
            toolbar,
            text="Export Markdown",
            command=lambda: self._export("markdown"),
        ).pack(side="left", padx=2)
        self.details = JsonView(self)
        self.details.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        try:
            self.payload = load_reasoning_projection(self.repository_root)
        except (OSError, ValueError, KeyError) as exc:
            self.payload = {
                "authoritative": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        certificate = self.payload.get("certificate") or {}
        limits = self.payload.get("limits") or {}
        self.summary.configure(
            text=(
                f"{certificate.get('decision', 'NO EPISODE')} | "
                f"{certificate.get('terminal_state', 'UNAVAILABLE')} | "
                f"{limits.get('path_count', 0)} paths | "
                f"{limits.get('contradiction_count', 0)} contradictions"
            )
        )
        self.details.set_value(self.payload)

    def _export(self, format_name: str) -> None:
        try:
            path = write_reasoning_export(self.repository_root, self.payload, format_name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("OIEC-SR export failed", str(exc), parent=self)
            return
        messagebox.showinfo(
            "OIEC-SR export",
            f"Wrote non-authoritative export to {path}",
            parent=self,
        )


__all__ = ["ReasoningInspectorView"]
