from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..governance_models import EvidenceDashboardModel
from .status_badge import StatusBadge


class CoverageDashboard(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=6)
        self.verdict = StatusBadge(self, "UNKNOWN", "neutral")
        self.verdict.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 5))
        self.summary = ttk.Label(self, text="No evidence loaded")
        self.summary.grid(row=0, column=1, columnspan=2, sticky="w", pady=(0, 5))
        self._labels: list[ttk.Label] = []
        self._bars: list[ttk.Progressbar] = []
        for index in range(6):
            label = ttk.Label(self, text="")
            label.grid(row=index + 1, column=0, sticky="w", padx=(0, 8))
            bar = ttk.Progressbar(self, maximum=100)
            bar.grid(row=index + 1, column=1, sticky="ew", padx=(0, 8))
            value = ttk.Label(self, text="—", width=12)
            value.grid(row=index + 1, column=2, sticky="e")
            self._labels.append(label)
            self._bars.append(bar)
            self._labels.append(value)
        self.classes = ttk.Label(self, text="", wraplength=760)
        self.classes.grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self.gaps = ttk.Label(self, text="", wraplength=760)
        self.gaps.grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.columnconfigure(1, weight=1)

    def set_model(self, model: EvidenceDashboardModel) -> None:
        status = {
            "APPROVE": "qualified",
            "APPROVE_WITH_LIMITS": "gated",
            "BLOCKED": "blocked",
            "REFUSE": "failed",
        }.get(model.verdict, "neutral")
        self.verdict.set_status(status, model.verdict)
        self.summary.configure(
            text=f"{len(model.evidence_ids)} evidence objects | {len(model.subject_ids)} subjects"
        )
        for index, dimension in enumerate(model.dimensions):
            name_label = self._labels[index * 2]
            value_label = self._labels[index * 2 + 1]
            name_label.configure(text=f"{dimension.code}  {dimension.name}")
            if dimension.coverage is None:
                self._bars[index]["value"] = 0
                value_label.configure(text="unknown")
            else:
                percent = round(dimension.coverage * 100)
                self._bars[index]["value"] = percent
                value_label.configure(
                    text=f"{percent}% ({dimension.covered}/{dimension.total})"
                )
        class_text = ", ".join(
            f"{name}: {count}" for name, count in model.classes.items()
        )
        self.classes.configure(text=f"Evidence classes — {class_text}")
        unresolved = [*model.blocking_gaps, *model.conflicts, *model.known_unknowns]
        self.gaps.configure(
            text="Uncovered / uncertain — " + ("; ".join(unresolved) if unresolved else "none")
        )
