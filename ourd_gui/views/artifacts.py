from __future__ import annotations

import json
import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from ourd.egcf.models import ArtifactRecord

from ..artifact_models import compare_geometry, inspect_artifact
from ..read_models import ReadOnlyEGCFRepository
from ..redaction import safe_projection


TEXT_MEDIA = {
    "application/json",
    "application/xml",
    "application/yaml",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "image/svg+xml",
}


class ArtifactWorkbenchView(ttk.Frame):
    MAX_PREVIEW_BYTES = 1_000_000
    MAX_INSPECTION_BYTES = 5_000_000

    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        on_object_selected: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="Passive previews only; originals remain immutable.",
        ).pack(side="left", padx=4, pady=4)
        ttk.Button(toolbar, text="Compare Selected", command=self._compare_selected).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="right", padx=4)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            paned,
            columns=("media", "size", "sources"),
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading("#0", text="Artifact")
        self.tree.heading("media", text="Media Type")
        self.tree.heading("size", text="Bytes")
        self.tree.heading("sources", text="Sources")
        self.tree.column("sources", width=70, stretch=False)
        preview_frame = ttk.Frame(paned)
        self.image = ttk.Label(preview_frame, text="", anchor="center")
        self.image.pack(fill="both", expand=False, padx=4, pady=4)
        self.preview = ScrolledText(
            preview_frame,
            wrap="none",
            state="disabled",
            font="TkFixedFont",
        )
        self.preview.pack(fill="both", expand=True)
        paned.add(self.tree, weight=2)
        paned.add(preview_frame, weight=3)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self._records: dict[str, ArtifactRecord] = {}
        self._photo: tk.PhotoImage | None = None
        self.refresh()

    def refresh(self) -> None:
        self._records.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        records = [
            record
            for record in self.repository.list("artifact")
            if isinstance(record, ArtifactRecord)
        ]
        records.sort(key=lambda item: (item.created_at, item.object_id), reverse=True)
        for record in records:
            self._records[record.object_id] = record
            self.tree.insert(
                "",
                "end",
                iid=record.object_id,
                text=record.sha256[:16],
                values=(record.media_type, record.size, len(record.source_ids)),
            )

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _clear_image(self) -> None:
        self._photo = None
        self.image.configure(image="", text="")

    def _selected(self, event: tk.Event) -> None:
        del event
        selection = self.tree.selection()
        if not selection:
            return
        object_id = selection[0]
        record = self._records[object_id]
        self._clear_image()
        metadata = {"object_id": object_id, "payload": asdict(record)}
        try:
            path = self.repository.artifact_content_path(record)
            if record.size > self.MAX_INSPECTION_BYTES:
                self._set_preview(
                    json.dumps(metadata, indent=2)
                    + "\n\nInspection blocked: artifact exceeds bounded inspection size."
                )
            else:
                content = path.read_bytes()
                inspection = inspect_artifact(record.media_type, path, content)
                metadata["inspection"] = asdict(inspection)
                rendered = json.dumps(safe_projection(metadata), indent=2)
                if inspection.preview_mode == "image" and path.suffix.casefold() in {
                    ".png",
                    ".gif",
                }:
                    try:
                        self._photo = tk.PhotoImage(file=str(path))
                        self.image.configure(image=self._photo, text="")
                    except tk.TclError as exc:
                        rendered += f"\n\nImage preview unavailable: {exc}"
                if record.size > self.MAX_PREVIEW_BYTES:
                    rendered += "\n\nContent preview blocked: artifact exceeds text preview size."
                elif record.media_type == "application/json":
                    try:
                        payload = json.loads(content.decode("utf-8"))
                        passive_content = json.dumps(safe_projection(payload), indent=2)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        passive_content = "[invalid JSON content]"
                    rendered += "\n\n--- Passive Content ---\n" + passive_content
                elif record.media_type in TEXT_MEDIA or record.media_type.startswith("text/"):
                    rendered += "\n\n--- Passive Content ---\n" + content.decode(
                        "utf-8", errors="replace"
                    )
                elif inspection.preview_mode == "geometry-metadata":
                    rendered += "\n\nGeometry metadata is bounded and read-only."
                else:
                    rendered += "\n\nNo active binary renderer is enabled for this media type."
                self._set_preview(rendered)
        except OSError as exc:
            self._set_preview(json.dumps(metadata, indent=2) + f"\n\nPreview unavailable: {exc}")
        if self.on_object_selected is not None:
            self.on_object_selected(object_id)

    def _inspect_record(self, record: ArtifactRecord):
        path = self.repository.artifact_content_path(record)
        if record.size > self.MAX_INSPECTION_BYTES:
            raise ValueError("artifact exceeds bounded inspection size")
        content = path.read_bytes()
        return inspect_artifact(record.media_type, path, content)

    def _compare_selected(self) -> None:
        selection = self.tree.selection()
        if len(selection) != 2:
            self._set_preview("Select exactly two artifacts for before/after comparison.\n")
            return
        left = self._records[selection[0]]
        right = self._records[selection[1]]
        try:
            comparison = compare_geometry(
                self._inspect_record(left),
                self._inspect_record(right),
            )
        except (OSError, ValueError) as exc:
            self._set_preview(f"Geometry comparison unavailable: {exc}\n")
            return
        self._clear_image()
        self._set_preview(
            json.dumps(
                safe_projection({
                    "before": {"object_id": left.object_id, "provenance": left.provenance},
                    "after": {"object_id": right.object_id, "provenance": right.provenance},
                    "comparison": comparison,
                    "comparison_is_metadata_only": True,
                }),
                indent=2,
            )
        )
