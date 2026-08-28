from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ourd.egcf.models import AlgorithmDefinition, QualificationRecord

from ..read_models import ReadOnlyEGCFRepository
from ..widgets.json_view import JsonView


class AlgorithmsView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
        on_show_evidence: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        self.on_show_evidence = on_show_evidence
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Search").pack(side="left", padx=4)
        self.query = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        entry.bind("<KeyRelease>", lambda event: self.refresh())
        ttk.Button(toolbar, text="Show Evidence", command=self._show_evidence).pack(side="right", padx=4)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("status", "capability", "risk", "qualification", "evidence"),
            show="tree headings",
        )
        self.tree.heading("#0", text="Algorithm")
        self.tree.heading("status", text="Status")
        self.tree.heading("capability", text="Capability")
        self.tree.heading("risk", text="Risk")
        self.tree.heading("qualification", text="Qualification")
        self.tree.heading("evidence", text="Evidence")
        self.details = JsonView(paned)
        paned.add(self.tree, weight=2)
        paned.add(self.details, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._records: dict[str, AlgorithmDefinition] = {}
        self._qualifications: dict[str, tuple[QualificationRecord, ...]] = {}
        self._selected_id = ""
        self.refresh()

    def refresh(self) -> None:
        needle = self.query.get().strip().lower()
        self._records.clear()
        self._qualifications.clear()
        self._selected_id = ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        qualifications_by_algorithm: dict[tuple[str, str], list[QualificationRecord]] = {}
        for item in self.repository.list("qualification"):
            if not isinstance(item, QualificationRecord):
                continue
            qualifications_by_algorithm.setdefault(
                (item.algorithm_id, item.algorithm_digest),
                [],
            ).append(item)
        for record in self.repository.list("algorithm-definition"):
            if not isinstance(record, AlgorithmDefinition):
                continue
            qualifications = tuple(
                qualifications_by_algorithm.get(
                    (record.algorithm_id, record.implementation_digest),
                    (),
                )
            )
            qualification_status = (
                qualifications[-1].status if qualifications else "UNQUALIFIED"
            )
            evidence_count = len(
                {
                    identifier
                    for qualification in qualifications
                    for identifier in qualification.evidence_ids
                }
            )
            haystack = " ".join(
                [
                    record.algorithm_id,
                    record.status,
                    record.capability_level,
                    record.implementation_kind,
                    record.risk_floor,
                    record.rollback_class,
                    qualification_status,
                    " ".join(record.invariants),
                    " ".join(record.command_ids),
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            self._records[record.object_id] = record
            self._qualifications[record.object_id] = qualifications
            self.tree.insert(
                "",
                "end",
                iid=record.object_id,
                text=record.algorithm_id,
                values=(
                    record.status,
                    record.capability_level,
                    record.risk_floor,
                    qualification_status,
                    evidence_count,
                ),
            )

    def _selected(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        object_id = selection[0]
        self._selected_id = object_id
        record = self._records[object_id]
        qualifications = self._qualifications.get(object_id, ())
        self.details.set_value(
            {
                "object_id": object_id,
                "payload": asdict(record),
                "qualifications": [asdict(item) for item in qualifications],
                "evidence_ids": list(
                    dict.fromkeys(
                        identifier
                        for qualification in qualifications
                        for identifier in qualification.evidence_ids
                    )
                ),
                "benchmark_count": sum(len(item.benchmarks) for item in qualifications),
                "test_count": sum(len(item.tests) for item in qualifications),
            }
        )
        if self.on_object_selected is not None:
            self.on_object_selected(object_id)

    def _show_evidence(self) -> None:
        if not self._selected_id or self.on_show_evidence is None:
            return
        identifiers = tuple(
            dict.fromkeys(
                identifier
                for qualification in self._qualifications.get(self._selected_id, ())
                for identifier in qualification.evidence_ids
            )
        )
        self.on_show_evidence(identifiers)
