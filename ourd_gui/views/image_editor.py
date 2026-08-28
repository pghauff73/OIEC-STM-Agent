from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from ..visual_assets import VisualAsset

try:
    from PIL import Image, ImageEnhance, ImageOps, ImageTk
except ImportError:  # pragma: no cover - optional dependency
    Image = ImageEnhance = ImageOps = ImageTk = None  # type: ignore[assignment]


class SupervisedImageEditor(ttk.Frame):
    """Non-destructive raster editor with explicit accept/revert supervision."""

    MAX_PREVIEW_SIDE = 1600

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_register_revision: Callable[[bytes, str], VisualAsset] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_register_revision = on_register_revision
        self.asset: VisualAsset | None = None
        self.path: Path | None = None
        self.accepted = None
        self.working = None
        self._photo = None
        self.pending_ops: list[str] = []
        self._crop_start: tuple[int, int] | None = None
        self._crop_rect: int | None = None
        self._display_box: tuple[float, float, float] | None = None

        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(fill="x")
        self.rotate_left = ttk.Button(toolbar, text="Rotate -90", command=lambda: self.stage("rotate", -90))
        self.rotate_left.pack(side="left", padx=2)
        self.rotate_right = ttk.Button(toolbar, text="Rotate +90", command=lambda: self.stage("rotate", 90))
        self.rotate_right.pack(side="left", padx=2)
        self.flip_h = ttk.Button(toolbar, text="Flip H", command=lambda: self.stage("flip_h"))
        self.flip_h.pack(side="left", padx=2)
        self.flip_v = ttk.Button(toolbar, text="Flip V", command=lambda: self.stage("flip_v"))
        self.flip_v.pack(side="left", padx=2)
        self.gray = ttk.Button(toolbar, text="Grayscale", command=lambda: self.stage("grayscale"))
        self.gray.pack(side="left", padx=2)
        self.crop_button = ttk.Button(toolbar, text="Crop Selection", command=self._apply_crop)
        self.crop_button.pack(side="left", padx=2)
        ttk.Button(toolbar, text="Accept", command=self.accept).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Revert", command=self.revert).pack(side="right", padx=2)

        controls = ttk.Frame(self, padding=(4, 0, 4, 4))
        controls.pack(fill="x")
        ttk.Label(controls, text="Brightness").pack(side="left")
        self.brightness = tk.DoubleVar(value=1.0)
        brightness_scale = ttk.Scale(
            controls,
            from_=0.2,
            to=2.0,
            variable=self.brightness,
            command=lambda value: self._preview_enhancement(),
        )
        brightness_scale.pack(side="left", fill="x", expand=True, padx=(4, 12))
        ttk.Label(controls, text="Contrast").pack(side="left")
        self.contrast = tk.DoubleVar(value=1.0)
        contrast_scale = ttk.Scale(
            controls,
            from_=0.2,
            to=2.0,
            variable=self.contrast,
            command=lambda value: self._preview_enhancement(),
        )
        contrast_scale.pack(side="left", fill="x", expand=True, padx=(4, 12))
        ttk.Button(controls, text="Stage Tone", command=self._commit_enhancement).pack(side="left")

        self.canvas = tk.Canvas(self, background="#11151a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._crop_begin)
        self.canvas.bind("<B1-Motion>", self._crop_drag)
        self.status = ttk.Label(
            self,
            text=(
                "Install Pillow with `pip install -e '.[visual]'` for raster editing."
                if Image is None
                else "Load an image. Drag to mark a crop rectangle."
            ),
            anchor="w",
        )
        self.status.pack(fill="x", padx=4, pady=2)
        self._set_edit_enabled(Image is not None)

    @property
    def available(self) -> bool:
        return Image is not None

    def _set_edit_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (
            self.rotate_left,
            self.rotate_right,
            self.flip_h,
            self.flip_v,
            self.gray,
            self.crop_button,
        ):
            button.configure(state=state)

    def load_asset(self, asset: VisualAsset, path: Path) -> None:
        self.asset = asset
        self.path = path
        self.pending_ops.clear()
        self.brightness.set(1.0)
        self.contrast.set(1.0)
        if Image is None:
            self.accepted = self.working = None
            try:
                self._photo = tk.PhotoImage(file=str(path))
                self.canvas.delete("all")
                self.canvas.create_image(8, 8, anchor="nw", image=self._photo)
                self.status.configure(text=f"{asset.reference} | passive preview only without Pillow")
            except tk.TclError:
                self.status.configure(text=f"{asset.reference} | preview requires Pillow for {path.suffix}")
            return
        with Image.open(path) as source:
            source.load()
            self.accepted = source.convert("RGBA")
        self.working = self.accepted.copy()
        self.status.configure(text=f"{asset.reference} | accepted revision 0 | no pending edits")
        self.redraw()

    def stage(self, operation: str, value: float | None = None) -> None:
        if Image is None or self.working is None:
            return
        if operation == "rotate":
            self.working = self.working.rotate(float(value or 0.0), expand=True)
            self.pending_ops.append(f"rotate({float(value or 0.0):g})")
        elif operation == "flip_h":
            self.working = ImageOps.mirror(self.working)
            self.pending_ops.append("flip_h")
        elif operation == "flip_v":
            self.working = ImageOps.flip(self.working)
            self.pending_ops.append("flip_v")
        elif operation == "grayscale":
            self.working = ImageOps.grayscale(self.working).convert("RGBA")
            self.pending_ops.append("grayscale")
        else:
            raise ValueError(f"unknown image edit operation: {operation}")
        self._clear_crop()
        self._update_status()
        self.redraw()

    def _preview_enhancement(self) -> None:
        if Image is None or self.working is None:
            return
        self.redraw(enhancement_preview=True)

    def _enhanced(self):
        if Image is None or self.working is None:
            return None
        image = self.working
        brightness = max(0.2, min(2.0, float(self.brightness.get())))
        contrast = max(0.2, min(2.0, float(self.contrast.get())))
        if abs(brightness - 1.0) > 1e-6:
            image = ImageEnhance.Brightness(image).enhance(brightness)
        if abs(contrast - 1.0) > 1e-6:
            image = ImageEnhance.Contrast(image).enhance(contrast)
        return image

    def _commit_enhancement(self) -> None:
        enhanced = self._enhanced()
        if enhanced is None:
            return
        brightness = float(self.brightness.get())
        contrast = float(self.contrast.get())
        if abs(brightness - 1.0) <= 1e-6 and abs(contrast - 1.0) <= 1e-6:
            return
        self.working = enhanced
        self.pending_ops.append(f"tone(brightness={brightness:.2f},contrast={contrast:.2f})")
        self.brightness.set(1.0)
        self.contrast.set(1.0)
        self._update_status()
        self.redraw()

    def _crop_begin(self, event: tk.Event) -> None:
        if Image is None or self.working is None or self._display_box is None:
            return
        self._crop_start = (int(event.x), int(event.y))
        self._clear_crop(delete_only=True)

    def _crop_drag(self, event: tk.Event) -> None:
        if self._crop_start is None:
            return
        if self._crop_rect is not None:
            self.canvas.delete(self._crop_rect)
        x0, y0 = self._crop_start
        self._crop_rect = self.canvas.create_rectangle(
            x0,
            y0,
            event.x,
            event.y,
            outline="#f0c674",
            width=2,
            dash=(5, 3),
        )

    def _apply_crop(self) -> None:
        if Image is None or self.working is None or self._crop_rect is None or self._display_box is None:
            self.status.configure(text="Drag a crop rectangle over the image first.")
            return
        x0, y0, x1, y1 = self.canvas.coords(self._crop_rect)
        image_left, image_top, scale = self._display_box
        left = int((min(x0, x1) - image_left) / scale)
        right = int((max(x0, x1) - image_left) / scale)
        top = int((min(y0, y1) - image_top) / scale)
        bottom = int((max(y0, y1) - image_top) / scale)
        left = max(0, min(left, self.working.width - 1))
        right = max(left + 1, min(right, self.working.width))
        top = max(0, min(top, self.working.height - 1))
        bottom = max(top + 1, min(bottom, self.working.height))
        self.working = self.working.crop((left, top, right, bottom))
        self.pending_ops.append(f"crop({left},{top},{right},{bottom})")
        self._clear_crop()
        self._update_status()
        self.redraw()

    def _clear_crop(self, *, delete_only: bool = False) -> None:
        if self._crop_rect is not None:
            self.canvas.delete(self._crop_rect)
        self._crop_rect = None
        if not delete_only:
            self._crop_start = None

    def accept(self) -> VisualAsset | None:
        if Image is None or self.working is None:
            return None
        if not self.pending_ops:
            self.status.configure(text="No pending image edits to accept.")
            return None
        self.accepted = self.working.copy()
        pending = tuple(self.pending_ops)
        self.pending_ops.clear()
        buffer = io.BytesIO()
        self.accepted.save(buffer, format="PNG")
        revision = None
        if self.on_register_revision is not None:
            stem = Path(self.asset.filename if self.asset else "image").stem
            revision = self.on_register_revision(buffer.getvalue(), f"{stem}-revision.png")
            self.asset = revision
        reference = revision.reference if revision is not None else (self.asset.reference if self.asset else "")
        self.status.configure(text=f"Accepted: {', '.join(pending)} | {reference}")
        self.redraw()
        return revision

    def revert(self) -> None:
        if Image is None or self.accepted is None:
            return
        self.working = self.accepted.copy()
        self.pending_ops.clear()
        self.brightness.set(1.0)
        self.contrast.set(1.0)
        self._clear_crop()
        self.status.configure(text="Pending image edits reverted to last accepted revision.")
        self.redraw()

    def export_accepted(self) -> Path | None:
        if Image is None or self.accepted is None:
            return None
        destination = filedialog.asksaveasfilename(
            title="Export accepted image revision",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if not destination:
            return None
        path = Path(destination)
        self.accepted.save(path, format="PNG")
        self.status.configure(text=f"Exported accepted revision to {path}")
        return path

    def _update_status(self) -> None:
        reference = self.asset.reference if self.asset is not None else "no-ref"
        pending = ", ".join(self.pending_ops) if self.pending_ops else "none"
        self.status.configure(text=f"{reference} | PENDING supervision | edits: {pending}")

    def redraw(self, *, enhancement_preview: bool = False) -> None:
        if Image is None or self.working is None:
            return
        self.canvas.delete("image")
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        source = self._enhanced() if enhancement_preview else self.working
        if source is None:
            return
        max_width = min(width - 20, self.MAX_PREVIEW_SIDE)
        max_height = min(height - 20, self.MAX_PREVIEW_SIDE)
        scale = min(max_width / source.width, max_height / source.height, 1.0)
        display = source
        if scale < 1.0:
            display = source.resize(
                (max(1, int(source.width * scale)), max(1, int(source.height * scale))),
                Image.Resampling.LANCZOS,
            )
        self._photo = ImageTk.PhotoImage(display)
        left = (width - display.width) / 2.0
        top = (height - display.height) / 2.0
        self.canvas.create_image(left, top, anchor="nw", image=self._photo, tags=("image",))
        self._display_box = (left, top, scale)
