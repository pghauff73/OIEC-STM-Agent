from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class ObjectLink(ttk.Button):
    def __init__(
        self,
        master: tk.Misc,
        object_id: str,
        command: Callable[[str], None],
        *,
        text: str = "",
    ) -> None:
        self.object_id = object_id
        super().__init__(
            master,
            text=text or object_id,
            command=lambda: command(self.object_id),
            style="Toolbutton",
        )

