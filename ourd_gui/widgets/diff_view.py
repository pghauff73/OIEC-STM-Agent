from __future__ import annotations

import tkinter as tk
from tkinter.scrolledtext import ScrolledText


def diff_line_kind(line: str) -> str:
    if line.startswith("+++") or line.startswith("---"):
        return "header"
    if line.startswith("@@"):
        return "hunk"
    if line.startswith("+"):
        return "added"
    if line.startswith("-"):
        return "removed"
    return "context"


class DiffView(ScrolledText):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, wrap="none", state="disabled", font="TkFixedFont")
        self.tag_configure("header", foreground="#4257a6")
        self.tag_configure("hunk", foreground="#6b4f9b")
        self.tag_configure("added", foreground="#176b2c")
        self.tag_configure("removed", foreground="#8a1c1c")
        self.tag_configure("context", foreground="#202124")

    def set_diff(self, value: str) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        for line in value.splitlines(keepends=True):
            self.insert("end", line, diff_line_kind(line))
        if value and not value.endswith("\n"):
            self.insert("end", "\n", "context")
        self.configure(state="disabled")
