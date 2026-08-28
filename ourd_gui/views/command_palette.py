from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..command_palette import CommandPaletteRegistry, PaletteCommand


class CommandPaletteDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, registry: CommandPaletteRegistry) -> None:
        super().__init__(master)
        self.registry = registry
        self._visible_commands: tuple[PaletteCommand, ...] = ()
        self.title("Command Palette")
        self.transient(master)
        self.geometry("720x430")
        self.query = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.query)
        entry.pack(fill="x", padx=10, pady=(10, 6))
        entry.bind("<KeyRelease>", self._refresh)
        entry.bind("<Return>", self._activate)
        entry.bind("<Down>", self._focus_list)
        self.results = tk.Listbox(self, activestyle="dotbox", exportselection=False)
        self.results.pack(fill="both", expand=True, padx=10)
        self.results.bind("<Double-Button-1>", self._activate)
        self.results.bind("<Return>", self._activate)
        self.description = ttk.Label(self, text="", padding=(10, 6), wraplength=680)
        self.description.pack(fill="x")
        self.results.bind("<<ListboxSelect>>", self._selected)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Run", command=self._run_selected).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda event: self.destroy())
        self._refresh()
        entry.focus_set()

    def _refresh(self, event: tk.Event | None = None) -> None:
        del event
        self._visible_commands = self.registry.search(self.query.get())
        self.results.delete(0, "end")
        for command in self._visible_commands:
            self.results.insert("end", f"{command.category}: {command.label}")
        if self._visible_commands:
            self.results.selection_set(0)
            self.results.activate(0)
            self._selected()
        else:
            self.description.configure(text="No matching commands")

    def _focus_list(self, event: tk.Event) -> str:
        del event
        self.results.focus_set()
        return "break"

    def _selected(self, event: tk.Event | None = None) -> None:
        del event
        selection = self.results.curselection()
        if not selection:
            return
        command = self._visible_commands[selection[0]]
        self.description.configure(text=command.description)

    def _activate(self, event: tk.Event | None = None) -> str:
        del event
        self._run_selected()
        return "break"

    def _run_selected(self) -> None:
        selection = self.results.curselection()
        if not selection:
            return
        command = self._visible_commands[selection[0]]
        self.destroy()
        self.registry.execute(command.command_id)
