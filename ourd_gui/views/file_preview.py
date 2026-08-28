from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from ourd.errors import PolicyError
from ourd.workspace import Workspace


class FilePreviewView(ttk.Frame):
    MAX_BYTES = 1_000_000
    MAX_LINES = 20_000

    def __init__(self, master: tk.Misc, repository_root: Path) -> None:
        super().__init__(master)
        self.workspace = Workspace(repository_root)
        self.summary = ttk.Label(self, text="No file selected", padding=4)
        self.summary.pack(fill="x")
        self.preview = ScrolledText(self, wrap="none", state="disabled", font="TkFixedFont")
        self.preview.pack(fill="both", expand=True)

    def show_file(self, relative_path: str, *, allow_internal: bool = False) -> None:
        try:
            path = self.workspace.resolve(relative_path, allow_internal=allow_internal)
            content = path.read_bytes()
        except (OSError, ValueError, PolicyError) as exc:
            self._set_text(f"Preview unavailable: {type(exc).__name__}: {exc}\n")
            return
        digest = hashlib.sha256(content).hexdigest()
        self.summary.configure(
            text=f"{relative_path} | {len(content)} bytes | sha256 {digest[:16]}"
        )
        if len(content) > self.MAX_BYTES:
            self._set_text("Preview blocked: file exceeds bounded preview size.\n")
            return
        if b"\0" in content[:8192]:
            self._set_text("Binary file: passive text preview disabled.\n")
            return
        lines = content.decode("utf-8", errors="replace").splitlines()
        if len(lines) > self.MAX_LINES:
            lines = [*lines[: self.MAX_LINES], "... preview line limit reached ..."]
        self._set_text("\n".join(lines) + ("\n" if lines else ""))

    def _set_text(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")
