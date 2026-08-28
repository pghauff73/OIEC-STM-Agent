from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..read_models import ReadOnlyEGCFRepository
from .capabilities import CapabilityLadderView
from .record_browser import RecordBrowser


class GovernanceView(ttk.Notebook):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.invariants = RecordBrowser(
            self,
            repository,
            ["invariant"],
            title="Invariants",
            on_object_selected=on_object_selected,
        )
        self.decisions = RecordBrowser(
            self,
            repository,
            ["decision", "supersedence"],
            title="Decisions",
            on_object_selected=on_object_selected,
        )
        self.confidence = RecordBrowser(
            self,
            repository,
            ["confidence-assessment", "assurance-case"],
            title="Confidence and Assurance",
            on_object_selected=on_object_selected,
        )
        self.capability_ladder = CapabilityLadderView(self, repository)
        self.capabilities = RecordBrowser(
            self,
            repository,
            ["capability-spec", "capability-grant"],
            title="Capabilities",
            on_object_selected=on_object_selected,
        )
        self.add(self.invariants, text="Invariants")
        self.add(self.decisions, text="Decisions")
        self.add(self.confidence, text="Assurance")
        self.add(self.capability_ladder, text="Capability Ladder")
        self.add(self.capabilities, text="Capability Records")

    def set_plan(self, plan) -> None:
        self.capability_ladder.set_plan(plan)

    def refresh(self) -> None:
        self.invariants.refresh()
        self.decisions.refresh()
        self.confidence.refresh()
        self.capability_ladder.refresh()
        self.capabilities.refresh()
