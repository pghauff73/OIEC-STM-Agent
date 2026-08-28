from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Mapping

from ..widgets.json_view import JsonView


class ApprovalDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        summary: Mapping[str, Any],
        *,
        on_approve: Callable[[str, str], None],
        on_reject: Callable[[], None] | None = None,
        on_inspect_evidence: Callable[[], None] | None = None,
        on_inspect_rollback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Scoped Approval")
        self.transient(master)
        self.grab_set()
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.approver = tk.StringVar(value="user")
        self.authority = tk.StringVar()
        header = ttk.Frame(self, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Exact governed action",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(side="left")
        ttk.Label(
            header,
            text=f"{summary.get('capability_level', '')} / {summary.get('risk', '')}",
        ).pack(side="right")
        scope = summary.get("scope", [])
        evidence = summary.get("evidence_ids", [])
        unresolved = summary.get("unresolved", [])
        ttk.Label(
            self,
            text=(
                f"Targets/scopes: {len(scope)}   Evidence: {len(evidence)}   "
                f"Unresolved: {len(unresolved)}   Rollback: "
                f"{'available' if summary.get('rollback_graph') else 'none'}"
            ),
            padding=(10, 0, 10, 6),
        ).pack(fill="x")
        details = JsonView(self, maximum_characters=100_000)
        details.pack(fill="both", expand=True, padx=10)
        details.set_value(dict(summary))
        form = ttk.Frame(self)
        form.pack(fill="x", padx=10, pady=8)
        ttk.Label(form, text="Approver").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.approver).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(form, text="Authority statement").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.authority).grid(row=1, column=1, sticky="ew", padx=4)
        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Approve Scoped", command=self._approve).pack(side="left")
        ttk.Button(buttons, text="Reject", command=self._reject).pack(side="left", padx=4)
        if on_inspect_evidence is not None:
            ttk.Button(buttons, text="Inspect Evidence", command=on_inspect_evidence).pack(side="left", padx=4)
        if on_inspect_rollback is not None:
            ttk.Button(buttons, text="Inspect Rollback", command=on_inspect_rollback).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.geometry("760x620")

    def _approve(self) -> None:
        approver = self.approver.get().strip()
        authority = self.authority.get().strip()
        if not approver or not authority:
            self.bell()
            return
        self.on_approve(approver, authority)
        self.destroy()

    def _reject(self) -> None:
        if self.on_reject is not None:
            self.on_reject()
        self.destroy()
