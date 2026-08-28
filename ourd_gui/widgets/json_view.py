from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from ..redaction import safe_projection


class JsonView(ttk.Frame):
    def __init__(self, master: tk.Misc, *, maximum_characters: int = 250_000):
        super().__init__(master)
        self.maximum_characters = maximum_characters
        self.text = ScrolledText(self, wrap="none", height=12, font="TkFixedFont")
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")

    def set_value(self, value: Any) -> None:
        content = json.dumps(
            safe_projection(value),
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        if len(content) > self.maximum_characters:
            content = (
                content[: self.maximum_characters]
                + f"\n\n[truncated after {self.maximum_characters} characters]"
            )
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
