from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ourd.interaction import ContextDelta, InteractionContextEnvelope, PinnedContextSet

from ..context_projection import context_delta_projection, context_envelope_projection
from ..widgets.json_view import JsonView


class ContextInspectorView(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._envelope: InteractionContextEnvelope | None = None
        self._delta: ContextDelta | None = None
        self._pinned_context = PinnedContextSet()
        self._file_payloads: dict[str, dict] = {}

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.summary = ttk.Label(toolbar, text="No active ICPI context envelope")
        self.summary.pack(side="left", fill="x", expand=True, padx=4)
        self.reveal_previews = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Reveal bounded previews",
            variable=self.reveal_previews,
            command=self.refresh,
        ).pack(side="right", padx=4)

        self.notice = ttk.Label(
            self,
            text=(
                "Read-only projection. Preview bodies are redacted by default and are "
                "never written to GUI journal events."
            ),
            wraplength=760,
            justify="left",
        )
        self.notice.pack(fill="x", padx=4, pady=(0, 4))

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)

        self.summary_details = JsonView(tabs)
        tabs.add(self.summary_details, text="Envelope")

        attachment_frame = ttk.Frame(tabs)
        self.attachments = ttk.Treeview(
            attachment_frame,
            columns=("kind", "value", "status", "files", "truncated"),
            show="headings",
        )
        for column, title, width in (
            ("kind", "Kind", 90),
            ("value", "Reference", 260),
            ("status", "Status", 100),
            ("files", "Files", 70),
            ("truncated", "Truncated", 80),
        ):
            self.attachments.heading(column, text=title)
            self.attachments.column(column, width=width, stretch=column == "value")
        attachment_scroll = ttk.Scrollbar(
            attachment_frame,
            orient="vertical",
            command=self.attachments.yview,
        )
        self.attachments.configure(yscrollcommand=attachment_scroll.set)
        self.attachments.pack(side="left", fill="both", expand=True)
        attachment_scroll.pack(side="right", fill="y")
        tabs.add(attachment_frame, text="Attachments")

        file_frame = ttk.Frame(tabs)
        file_paned = ttk.PanedWindow(file_frame, orient="vertical")
        file_paned.pack(fill="both", expand=True)
        file_list_frame = ttk.Frame(file_paned)
        self.files = ttk.Treeview(
            file_list_frame,
            columns=("path", "size", "media", "hash", "preview", "truncated"),
            show="headings",
        )
        for column, title, width in (
            ("path", "Path", 260),
            ("size", "Bytes", 80),
            ("media", "Media Type", 150),
            ("hash", "SHA-256", 150),
            ("preview", "Preview", 100),
            ("truncated", "Truncated", 80),
        ):
            self.files.heading(column, text=title)
            self.files.column(column, width=width, stretch=column == "path")
        file_scroll = ttk.Scrollbar(
            file_list_frame,
            orient="vertical",
            command=self.files.yview,
        )
        self.files.configure(yscrollcommand=file_scroll.set)
        self.files.pack(side="left", fill="both", expand=True)
        file_scroll.pack(side="right", fill="y")
        self.file_details = JsonView(file_paned, maximum_characters=100_000)
        file_paned.add(file_list_frame, weight=2)
        file_paned.add(self.file_details, weight=3)
        tabs.add(file_frame, text="Files")
        self.files.bind("<<TreeviewSelect>>", self._selected_file)

        delta_frame = ttk.Frame(tabs)
        self.deltas = ttk.Treeview(
            delta_frame,
            columns=("path", "status", "previous", "current"),
            show="headings",
        )
        for column, title, width in (
            ("path", "Path", 300),
            ("status", "Status", 110),
            ("previous", "Previous Bytes", 110),
            ("current", "Current Bytes", 110),
        ):
            self.deltas.heading(column, text=title)
            self.deltas.column(column, width=width, stretch=column == "path")
        delta_scroll = ttk.Scrollbar(
            delta_frame,
            orient="vertical",
            command=self.deltas.yview,
        )
        self.deltas.configure(yscrollcommand=delta_scroll.set)
        self.deltas.pack(side="left", fill="both", expand=True)
        delta_scroll.pack(side="right", fill="y")
        tabs.add(delta_frame, text="Delta")
        self.tabs = tabs
        self.refresh()

    def set_envelope(self, envelope: InteractionContextEnvelope | None) -> None:
        self._envelope = envelope
        self.reveal_previews.set(False)
        self.refresh()

    def set_pinned_context(self, pinned_context: PinnedContextSet) -> None:
        self._pinned_context = pinned_context
        self.refresh()

    def set_context_delta(self, delta: ContextDelta | None) -> None:
        self._delta = delta
        self.refresh()

    def refresh(self) -> None:
        for tree in (self.attachments, self.files, self.deltas):
            for item_id in tree.get_children():
                tree.delete(item_id)
        self._file_payloads = {}
        if self._envelope is None:
            payload = {
                "authoritative": False,
                "message": "No active ICPI context envelope",
                "preview_bodies_persisted": False,
                "pinned_context": {
                    "context_id": self._pinned_context.context_id,
                    "signature": self._pinned_context.signature,
                    "paths": list(self._pinned_context.paths),
                    "count": len(self._pinned_context.paths),
                },
                "context_delta": (
                    context_delta_projection(self._delta)
                    if self._delta is not None
                    else None
                ),
            }
            self.summary.configure(
                text=(
                    "No active ICPI context envelope | "
                    f"{len(self._pinned_context.paths)} pinned paths"
                )
            )
            self.summary_details.set_value(payload)
            self.file_details.set_value(payload)
            return

        payload = context_envelope_projection(
            self._envelope,
            include_preview_text=self.reveal_previews.get(),
        )
        payload["pinned_context"] = {
            "context_id": self._pinned_context.context_id,
            "signature": self._pinned_context.signature,
            "paths": list(self._pinned_context.paths),
            "count": len(self._pinned_context.paths),
        }
        delta_payload = (
            context_delta_projection(self._delta)
            if self._delta is not None
            else None
        )
        payload["context_delta"] = delta_payload
        freshness = delta_payload["freshness"] if delta_payload is not None else "UNCHECKED"
        self.summary.configure(
            text=(
                f"{freshness} | {payload['mode']} | {len(payload['attachments'])} references | "
                f"{len(payload['files'])} files | {len(self._pinned_context.paths)} pinned | "
                f"{payload['total_preview_bytes']} preview bytes"
            )
        )
        self.summary_details.set_value(payload)
        for index, item in enumerate(payload["attachments"]):
            self.attachments.insert(
                "",
                "end",
                iid=f"attachment-{index}",
                values=(
                    item["kind"],
                    item["value"],
                    item["status"],
                    len(item["file_paths"]),
                    "yes" if item["truncated"] else "no",
                ),
            )
        if delta_payload is not None:
            for index, item in enumerate(delta_payload["files"]):
                self.deltas.insert(
                    "",
                    "end",
                    iid=f"delta-{index}",
                    values=(
                        item["path"],
                        item["status"],
                        item["previous_size_bytes"],
                        item["current_size_bytes"],
                    ),
                )
        for index, item in enumerate(payload["files"]):
            item_id = f"file-{index}"
            self._file_payloads[item_id] = item
            digest = item["content_sha256"] or item["hash_status"]
            self.files.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    item["path"],
                    item["size_bytes"],
                    item["media_type"],
                    digest,
                    "redacted" if item["preview_redacted"] else item["preview_kind"],
                    "yes" if item["preview_truncated"] else "no",
                ),
            )
        if self._file_payloads:
            first = next(iter(self._file_payloads))
            self.files.selection_set(first)
            self.files.focus(first)
            self.file_details.set_value(self._file_payloads[first])
        else:
            self.file_details.set_value(
                {
                    "message": "The active envelope contains no projected files",
                    "unresolved_reference_ids": payload["unresolved_reference_ids"],
                }
            )

    def _selected_file(self, event: tk.Event) -> None:
        del event
        selection = self.files.selection()
        if selection:
            self.file_details.set_value(self._file_payloads.get(selection[0], {}))


__all__ = ["ContextInspectorView"]
