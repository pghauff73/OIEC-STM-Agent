from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from ..commands import CommandRequest
from ..read_models import ReadOnlyEGCFRepository
from ..semantic_terminal import parse_semantic_command


class SemanticTerminalView(ttk.Frame):
    MAX_TRANSCRIPT_CHARACTERS = 200_000

    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_submit: Callable[[CommandRequest], None],
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_submit = on_submit
        ttk.Label(
            self,
            text=(
                "Typed semantic terminal — JSON inputs only; no pipes, redirects, "
                "subshells, or arbitrary process execution."
            ),
            padding=4,
        ).pack(fill="x")
        self.transcript = ScrolledText(self, wrap="word", state="disabled", font="TkFixedFont")
        self.transcript.pack(fill="both", expand=True)
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill="x")
        self.command = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.command)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", self._submit)
        ttk.Button(bar, text="Submit Governed", command=self._submit).pack(side="left", padx=(4, 0))

    def append(self, actor: str, value: object) -> None:
        if not isinstance(value, str):
            value = json.dumps(value, indent=2, ensure_ascii=False, default=str)
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"\n[{actor}]\n{value}\n")
        content = self.transcript.get("1.0", "end-1c")
        if len(content) > self.MAX_TRANSCRIPT_CHARACTERS:
            self.transcript.delete("1.0", f"1.0+{len(content) - self.MAX_TRANSCRIPT_CHARACTERS}c")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _submit(self, event: tk.Event | None = None) -> str:
        del event
        raw = self.command.get().strip()
        if not raw:
            return "break"
        try:
            parsed = parse_semantic_command(self.repository, raw)
        except ValueError as exc:
            self.append("REJECTED", str(exc))
            return "break"
        self.append(
            "CLASSIFIED",
            {
                "command_id": parsed.command_id,
                "capability": parsed.capability_level,
                "risk": parsed.risk,
                "approval": parsed.approval_policy,
                "read_only": parsed.read_only,
                "dry_run": parsed.request().modifiers["dry_run"],
            },
        )
        self.on_submit(parsed.request())
        self.command.set("")
        return "break"
