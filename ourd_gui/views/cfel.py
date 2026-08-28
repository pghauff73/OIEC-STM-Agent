from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ourd.egcf.models import FailureRecord

from ..read_models import ReadOnlyEGCFRepository
from .record_browser import RecordBrowser


class CFELView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
        on_create_regression: Callable[[FailureRecord], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_create_regression = on_create_regression
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.status = ttk.Label(
            toolbar,
            text="Failures remain append-only; retries require changed evidence or candidate identity.",
        )
        self.status.pack(side="left", padx=4, pady=4)
        ttk.Button(toolbar, text="Show Root Cause", command=self._show_root_cause).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Show Previous Failures", command=self._show_previous).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Create Regression Test", command=self._create_regression).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Compare Retry", command=self._compare_retry).pack(side="left", padx=2)
        self.browser = RecordBrowser(
            self,
            repository,
            ["failure", "rollback"],
            title="CFEL Failures and Recovery",
            on_object_selected=on_object_selected,
        )
        self.browser.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self.browser.refresh()

    def _failure(self) -> FailureRecord | None:
        record = self.browser.selected_record()
        return record if isinstance(record, FailureRecord) else None

    def _show_root_cause(self) -> None:
        failure = self._failure()
        if failure is None:
            return
        self.browser.show_details(
            {
                "failure_id": failure.object_id,
                "root_cause_hypothesis": {
                    "active_dimension": failure.active_dimension,
                    "frozen_dimensions": failure.frozen_dimensions,
                    "observed": failure.observed,
                    "expected": failure.expected,
                },
                "status": failure.status,
                "evidence_ids": failure.evidence_ids,
                "note": "Hypothesis only; deterministic verification remains required.",
            }
        )

    def _show_previous(self) -> None:
        failure = self._failure()
        if failure is None:
            return
        self.browser.query.set(failure.subject_id)
        self.browser.refresh()

    def _create_regression(self) -> None:
        failure = self._failure()
        if failure is not None and self.on_create_regression is not None:
            self.on_create_regression(failure)

    def _compare_retry(self) -> None:
        failure = self._failure()
        if failure is None:
            return
        related = [
            record
            for record in self.repository.list("failure")
            if isinstance(record, FailureRecord) and record.subject_id == failure.subject_id
        ]
        related.sort(key=lambda item: (item.retry_count, item.created_at, item.object_id))
        self.browser.show_details(
            {
                "subject_id": failure.subject_id,
                "retry_comparison": [asdict(record) for record in related],
                "changed_dimensions": sorted({record.active_dimension for record in related}),
                "retry_count": len(related),
            }
        )
