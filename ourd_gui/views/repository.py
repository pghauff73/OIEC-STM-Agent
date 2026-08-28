from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from ourd.workspace import DEFAULT_IGNORES, Workspace


def visible_repository_paths(
    repository_root: Path,
    *,
    show_internal_state: bool,
) -> tuple[str, ...]:
    workspace = Workspace(repository_root)
    if not show_internal_state:
        return tuple(
            workspace.rel(path)
            for path in sorted(workspace.iter_files(), key=lambda item: workspace.rel(item))
        )
    ignored = DEFAULT_IGNORES - {workspace.internal_name}
    paths: list[str] = []
    for path in repository_root.resolve().rglob("*"):
        if not path.is_file():
            continue
        try:
            relative_parts = path.resolve(strict=False).relative_to(workspace.root).parts
        except ValueError:
            continue
        if any(part in ignored or part.endswith(".egg-info") for part in relative_parts):
            continue
        paths.append(workspace.rel(path, allow_internal=True))
    return tuple(sorted(paths))


class RepositoryView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository_root: Path,
        on_select: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.workspace = Workspace(repository_root)
        self.repository_root = repository_root.resolve()
        self.on_select = on_select
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.show_internal_state = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Show .ourd-agent state",
            variable=self.show_internal_state,
            command=self.refresh,
        ).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="right", padx=4)
        self.tree = ttk.Treeview(self, show="tree")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        directories: dict[str, str] = {"": ""}
        for relative in visible_repository_paths(
            self.repository_root,
            show_internal_state=self.show_internal_state.get(),
        ):
            parent_key = ""
            parts = relative.split("/")
            for index, part in enumerate(parts):
                key = "/".join(parts[: index + 1])
                if key in directories:
                    parent_key = key
                    continue
                is_file = index == len(parts) - 1
                self.tree.insert(parent_key, "end", iid=key, text=part, open=False)
                if not is_file:
                    directories[key] = key
                parent_key = key

    def set_show_internal_state(self, enabled: bool) -> None:
        self.show_internal_state.set(bool(enabled))
        self.refresh()

    def internal_state_enabled(self) -> bool:
        return bool(self.show_internal_state.get())

    def _selected(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection and self.on_select is not None:
            self.on_select(selection[0])
