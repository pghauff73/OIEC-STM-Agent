from __future__ import annotations

import shlex
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from ..visual_assets import VisualAsset, VisualAssetRegistry
from ..visual_models import BezierScene, load_mesh
from ..widgets.mesh_viewer import MeshViewer
from .bezier_editor import SupervisedBezierEditor
from .image_editor import SupervisedImageEditor


class VisualWorkbenchView(ttk.Frame):
    """Multimodal GUI workbench with a bounded local command line."""

    MAX_TRANSCRIPT = 120_000

    def __init__(
        self,
        master: tk.Misc,
        repository_root: Path,
        *,
        on_insert_chat_reference: Callable[[str], None] | None = None,
        on_chat_send: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository_root = repository_root.resolve()
        self.registry = VisualAssetRegistry(self.repository_root)
        self.on_insert_chat_reference = on_insert_chat_reference or (lambda reference: None)
        self.on_chat_send = on_chat_send or (lambda message: None)
        self.selected_reference = ""

        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Visual Assets").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Input Image", command=self.open_image).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Input 3D", command=self.open_mesh).pack(side="left", padx=2)
        ttk.Button(toolbar, text="New 3D Curve", command=self.new_curve).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Insert Ref in Chat", command=self.insert_selected_reference).pack(side="right", padx=2)
        self.reference_label = ttk.Label(toolbar, text="Reference: none")
        self.reference_label.pack(side="right", padx=8)

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        asset_frame = ttk.Frame(main, padding=4)
        self.assets = ttk.Treeview(
            asset_frame,
            columns=("kind", "file", "bytes"),
            show="tree headings",
            selectmode="browse",
        )
        self.assets.heading("#0", text="Reference")
        self.assets.heading("kind", text="Kind")
        self.assets.heading("file", text="File")
        self.assets.heading("bytes", text="Bytes")
        self.assets.column("#0", width=190)
        self.assets.column("kind", width=70, stretch=False)
        self.assets.column("file", width=180)
        self.assets.column("bytes", width=80, stretch=False)
        scroll = ttk.Scrollbar(asset_frame, orient="vertical", command=self.assets.yview)
        self.assets.configure(yscrollcommand=scroll.set)
        self.assets.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.assets.bind("<<TreeviewSelect>>", self._asset_selected)
        main.add(asset_frame, weight=1)

        right = ttk.Frame(main)
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        self.image_editor = SupervisedImageEditor(
            self.tabs,
            on_register_revision=self._register_image_revision,
        )
        mesh_frame = ttk.Frame(self.tabs)
        mesh_toolbar = ttk.Frame(mesh_frame, padding=4)
        mesh_toolbar.pack(fill="x")
        ttk.Label(
            mesh_toolbar,
            text="Drag to orbit | mouse wheel to zoom | OBJ/STL wireframe preview",
        ).pack(side="left")
        ttk.Button(mesh_toolbar, text="Reset View", command=lambda: self.mesh_viewer.reset_view()).pack(side="right")
        self.mesh_viewer = MeshViewer(mesh_frame)
        self.mesh_viewer.pack(fill="both", expand=True)
        self.bezier_editor = SupervisedBezierEditor(
            self.tabs,
            on_register_scene=self._register_curve_revision,
        )
        self.tabs.add(self.image_editor, text="2D Image Editor")
        self.tabs.add(mesh_frame, text="3D Viewer")
        self.tabs.add(self.bezier_editor, text="3-View Bezier")
        main.add(right, weight=4)

        terminal = ttk.LabelFrame(self, text="Visual CLI", padding=4)
        terminal.pack(fill="x", padx=4, pady=(4, 0))
        self.transcript = ScrolledText(
            terminal,
            height=8,
            wrap="word",
            state="disabled",
            font="TkFixedFont",
        )
        self.transcript.pack(fill="x", expand=True)
        command_bar = ttk.Frame(terminal)
        command_bar.pack(fill="x", pady=(4, 0))
        self.command = tk.StringVar()
        entry = ttk.Entry(command_bar, textvariable=self.command)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", self._submit_command)
        ttk.Button(command_bar, text="Run", command=self._submit_command).pack(side="left", padx=(4, 0))
        ttk.Label(
            command_bar,
            text="help | list | show REF | image ... | curve ... | mesh reset | chat ...",
        ).pack(side="left", padx=8)
        self.refresh_assets()
        self._append("SYSTEM", "Visual CLI ready. Type `help` for commands.")

    def refresh_assets(self) -> None:
        current = self.selected_reference
        for item in self.assets.get_children():
            self.assets.delete(item)
        for asset in self.registry.list():
            self.assets.insert(
                "",
                "end",
                iid=asset.reference,
                text=asset.reference,
                values=(asset.kind, asset.filename, asset.size),
            )
        if current and self.assets.exists(current):
            self.assets.selection_set(current)
            self.assets.see(current)

    def open_image(self, path: str | Path | None = None) -> VisualAsset | None:
        if path is None:
            filename = filedialog.askopenfilename(
                title="Input image",
                filetypes=[
                    ("Images", "*.png *.jpg *.jpeg *.gif *.webp"),
                    ("All files", "*"),
                ],
            )
            if not filename:
                return None
            path = filename
        try:
            asset = self.registry.register_file(Path(path), kind="image")
            self._show_asset(asset)
            self.refresh_assets()
            self._append("IMAGE", f"registered {asset.reference} <- {asset.filename}")
            return asset
        except Exception as exc:
            self._append("ERROR", f"{type(exc).__name__}: {exc}")
            return None

    def open_mesh(self, path: str | Path | None = None) -> VisualAsset | None:
        if path is None:
            filename = filedialog.askopenfilename(
                title="Input 3D object",
                filetypes=[("3D mesh", "*.obj *.stl"), ("All files", "*")],
            )
            if not filename:
                return None
            path = filename
        try:
            asset = self.registry.register_file(Path(path), kind="mesh")
            self._show_asset(asset)
            self.refresh_assets()
            self._append("MESH", f"registered {asset.reference} <- {asset.filename}")
            return asset
        except Exception as exc:
            self._append("ERROR", f"{type(exc).__name__}: {exc}")
            return None

    def new_curve(self, name: str | None = None) -> None:
        curve = self.bezier_editor.add_curve(name)
        self.tabs.select(self.bezier_editor)
        self._append("CURVE", f"staged curve {curve.name} ({curve.curve_id})")

    def insert_selected_reference(self) -> None:
        if not self.selected_reference:
            self._append("ERROR", "select a visual asset first")
            return
        self.on_insert_chat_reference(self.selected_reference)
        self._append("CHAT", f"inserted {self.selected_reference} into Agent Chat")

    def _asset_selected(self, event: tk.Event) -> None:
        del event
        selection = self.assets.selection()
        if not selection:
            return
        try:
            self._show_asset(self.registry.get(selection[0]))
        except Exception as exc:
            self._append("ERROR", f"{type(exc).__name__}: {exc}")

    def _show_asset(self, asset: VisualAsset) -> None:
        self.selected_reference = asset.reference
        self.reference_label.configure(text=f"Reference: {asset.reference}")
        path = self.registry.path_for(asset.reference)
        if asset.kind == "image":
            self.image_editor.load_asset(asset, path)
            self.tabs.select(self.image_editor)
        elif asset.kind == "mesh":
            self.mesh_viewer.set_mesh(load_mesh(path))
            self.tabs.select(self.mesh_viewer.master)
        elif asset.kind == "curve":
            scene = BezierScene.from_json(path.read_text(encoding="utf-8"))
            self.bezier_editor.load_scene(scene, reference=asset.reference)
            self.tabs.select(self.bezier_editor)

    def _register_image_revision(self, content: bytes, filename: str) -> VisualAsset:
        asset = self.registry.register_bytes(
            content,
            filename=filename,
            kind="image",
            media_type="image/png",
        )
        self.selected_reference = asset.reference
        self.refresh_assets()
        self.reference_label.configure(text=f"Reference: {asset.reference}")
        self._append("IMAGE", f"accepted revision -> {asset.reference}")
        return asset

    def _register_curve_revision(self, content: bytes, filename: str) -> VisualAsset:
        asset = self.registry.register_bytes(
            content,
            filename=filename,
            kind="curve",
            media_type="application/vnd.oiec.bezier3d+json",
        )
        self.selected_reference = asset.reference
        self.refresh_assets()
        self.reference_label.configure(text=f"Reference: {asset.reference}")
        self._append("CURVE", f"accepted scene -> {asset.reference}")
        return asset

    def _append(self, actor: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"[{actor}] {text}\n")
        content = self.transcript.get("1.0", "end-1c")
        if len(content) > self.MAX_TRANSCRIPT:
            self.transcript.delete("1.0", f"1.0+{len(content) - self.MAX_TRANSCRIPT}c")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _submit_command(self, event: tk.Event | None = None) -> str:
        del event
        raw = self.command.get().strip()
        if not raw:
            return "break"
        self._append("YOU", raw)
        try:
            argv = shlex.split(raw)
            self._dispatch(argv)
        except Exception as exc:
            self._append("ERROR", f"{type(exc).__name__}: {exc}")
        self.command.set("")
        return "break"

    def _dispatch(self, argv: list[str]) -> None:
        if not argv:
            return
        command = argv[0].casefold()
        if command == "help":
            self._append(
                "HELP",
                "commands:\n"
                "  list [image|mesh|curve]\n"
                "  open-image [PATH]\n"
                "  open-mesh [PATH]\n"
                "  show REF\n"
                "  ref REF                 insert visual reference into Agent Chat\n"
                "  image rotate DEG        stage a supervised rotation\n"
                "  image flip-h|flip-v|grayscale\n"
                "  image accept|revert|export\n"
                "  curve new [NAME]\n"
                "  curve accept|revert|export|import\n"
                "  mesh reset\n"
                "  chat TEXT...            send a governed Agent Chat turn; @img refs become image inputs",
            )
            return
        if command == "list":
            kind = argv[1] if len(argv) > 1 else ""
            for asset in self.registry.list(kind):
                self._append("ASSET", f"{asset.reference} {asset.kind} {asset.filename} {asset.size} bytes")
            return
        if command == "open-image":
            self.open_image(argv[1] if len(argv) > 1 else None)
            return
        if command == "open-mesh":
            self.open_mesh(argv[1] if len(argv) > 1 else None)
            return
        if command == "show":
            if len(argv) != 2:
                raise ValueError("usage: show REF")
            self._show_asset(self.registry.get(argv[1]))
            return
        if command == "ref":
            if len(argv) != 2:
                raise ValueError("usage: ref REF")
            self.registry.get(argv[1])
            self.selected_reference = argv[1]
            self.insert_selected_reference()
            return
        if command == "image":
            self._image_command(argv[1:])
            return
        if command == "curve":
            self._curve_command(argv[1:])
            return
        if command == "mesh" and argv[1:] == ["reset"]:
            self.mesh_viewer.reset_view()
            return
        if command == "chat":
            message = raw_after_command(argv, "chat")
            if not message:
                raise ValueError("usage: chat TEXT...")
            self.on_chat_send(message)
            return
        raise ValueError(f"unknown visual command: {argv[0]}")

    def _image_command(self, args: list[str]) -> None:
        if not args:
            raise ValueError("usage: image rotate|flip-h|flip-v|grayscale|accept|revert|export")
        operation = args[0].casefold()
        if operation == "rotate":
            if len(args) != 2:
                raise ValueError("usage: image rotate DEG")
            self.image_editor.stage("rotate", float(args[1]))
        elif operation == "flip-h":
            self.image_editor.stage("flip_h")
        elif operation == "flip-v":
            self.image_editor.stage("flip_v")
        elif operation == "grayscale":
            self.image_editor.stage("grayscale")
        elif operation == "accept":
            self.image_editor.accept()
        elif operation == "revert":
            self.image_editor.revert()
        elif operation == "export":
            self.image_editor.export_accepted()
        else:
            raise ValueError(f"unknown image operation: {operation}")
        self.tabs.select(self.image_editor)

    def _curve_command(self, args: list[str]) -> None:
        if not args:
            raise ValueError("usage: curve new|accept|revert|export|import")
        operation = args[0].casefold()
        if operation == "new":
            self.new_curve(" ".join(args[1:]) or None)
        elif operation == "accept":
            self.bezier_editor.accept()
        elif operation == "revert":
            self.bezier_editor.revert()
        elif operation == "export":
            self.bezier_editor.export_json()
        elif operation == "import":
            self.bezier_editor.import_json()
        else:
            raise ValueError(f"unknown curve operation: {operation}")
        self.tabs.select(self.bezier_editor)


def raw_after_command(argv: list[str], command: str) -> str:
    if not argv or argv[0].casefold() != command.casefold():
        return ""
    return " ".join(argv[1:]).strip()
