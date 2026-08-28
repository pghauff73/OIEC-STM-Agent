from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..visual_models import MeshData, normalize_vertices, rotate_point

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional visual dependency
    Image = ImageTk = None  # type: ignore[assignment]


class MeshViewer(ttk.Frame):
    """Bounded Tk mesh viewer with surface/color and texture-map inspection."""

    MAX_RENDER_EDGES = 25_000
    MAX_RENDER_FACES = 8_000
    TEXTURE_PREVIEW_SIDE = 150

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        controls = ttk.Frame(self, padding=(2, 2))
        controls.pack(fill="x")
        self.show_surfaces = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls,
            text="Surfaces",
            variable=self.show_surfaces,
            command=self.redraw,
        ).pack(side="left")
        self.show_texture_preview = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls,
            text="Texture map",
            variable=self.show_texture_preview,
            command=self.redraw,
        ).pack(side="left", padx=(8, 0))
        self.canvas = tk.Canvas(self, background="#101317", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(self, text="No 3D object loaded", anchor="w")
        self.status.pack(fill="x")
        self.mesh: MeshData | None = None
        self.vertices = ()
        self.yaw = math.radians(-25)
        self.pitch = math.radians(20)
        self.zoom = 0.86
        self._drag_origin: tuple[int, int] | None = None
        self._texture_photo = None
        self.canvas.bind("<Configure>", lambda event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_delta(1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_delta(-1))

    def set_mesh(self, mesh: MeshData) -> None:
        self.mesh = mesh
        self.vertices = normalize_vertices(mesh.vertices)
        texture_mapping = "yes" if mesh.has_texture_mapping else "no"
        colors = "yes" if mesh.has_vertex_colors else "no"
        self.status.configure(
            text=(
                f"{mesh.name} | {mesh.format_name or 'mesh'} {mesh.encoding or ''} | "
                f"vertices={len(mesh.vertices):,} faces={len(mesh.faces):,} "
                f"edges={len(mesh.edges):,} uv={len(mesh.texcoords):,} "
                f"materials={len(mesh.materials):,} textures={len(mesh.texture_paths):,} | "
                f"UV-mapped={texture_mapping} vertex-color={colors}"
            )
        )
        self.redraw()

    def clear(self) -> None:
        self.mesh = None
        self.vertices = ()
        self._texture_photo = None
        self.canvas.delete("all")
        self.status.configure(text="No 3D object loaded")

    def reset_view(self) -> None:
        self.yaw = math.radians(-25)
        self.pitch = math.radians(20)
        self.zoom = 0.86
        self.redraw()

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_origin = (int(event.x), int(event.y))

    def _drag(self, event: tk.Event) -> None:
        if self._drag_origin is None:
            self._drag_origin = (int(event.x), int(event.y))
            return
        old_x, old_y = self._drag_origin
        self.yaw += (event.x - old_x) * 0.01
        self.pitch += (event.y - old_y) * 0.01
        self.pitch = max(-math.pi / 2.0, min(math.pi / 2.0, self.pitch))
        self._drag_origin = (int(event.x), int(event.y))
        self.redraw()

    def _wheel(self, event: tk.Event) -> None:
        delta = 1 if getattr(event, "delta", 0) > 0 else -1
        self._wheel_delta(delta)

    def _wheel_delta(self, delta: int) -> None:
        self.zoom = max(0.15, min(4.0, self.zoom * (1.12 if delta > 0 else 0.89)))
        self.redraw()

    @staticmethod
    def _hex(color: tuple[int, int, int, int]) -> str:
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    def _face_color(self, face) -> str:
        assert self.mesh is not None
        material_map = {material.name: material for material in self.mesh.materials}
        if face.material and face.material in material_map:
            return self._hex(material_map[face.material].diffuse)
        colors = [
            self.mesh.vertex_colors[index]
            for index in face.vertex_indices
            if 0 <= index < len(self.mesh.vertex_colors)
            and self.mesh.vertex_colors[index] is not None
        ]
        if colors:
            rgba = tuple(
                int(round(sum(color[channel] for color in colors if color is not None) / len(colors)))
                for channel in range(4)
            )
            return self._hex(rgba)  # type: ignore[arg-type]
        return "#27313a"

    def redraw(self) -> None:
        self.canvas.delete("all")
        self._texture_photo = None
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self._draw_axes(width, height)
        if self.mesh is None or not self.vertices:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Load an OBJ, STL, or PLY object",
                fill="#aab3bd",
            )
            return
        transformed = [rotate_point(point, self.yaw, self.pitch) for point in self.vertices]
        scale = min(width, height) * 0.34 * self.zoom
        projected: list[tuple[float, float]] = []
        for x, y, z in transformed:
            perspective = 3.5 / max(1.0, 3.5 + z)
            projected.append(
                (width / 2.0 + x * scale * perspective, height / 2.0 - y * scale * perspective)
            )

        if self.show_surfaces.get() and self.mesh.faces:
            faces = list(self.mesh.faces)
            if len(faces) > self.MAX_RENDER_FACES:
                stride = max(1, len(faces) // self.MAX_RENDER_FACES)
                faces = faces[::stride]
            ordered = []
            for face in faces:
                valid = [index for index in face.vertex_indices if 0 <= index < len(projected)]
                if len(valid) < 3:
                    continue
                depth = sum(transformed[index][2] for index in valid) / len(valid)
                ordered.append((depth, face, valid))
            ordered.sort(reverse=True, key=lambda item: item[0])
            for _, face, valid in ordered:
                coordinates = [coordinate for index in valid for coordinate in projected[index]]
                self.canvas.create_polygon(
                    *coordinates,
                    fill=self._face_color(face),
                    outline="#56616c",
                    width=1,
                )

        edges = self.mesh.edges
        if len(edges) > self.MAX_RENDER_EDGES:
            stride = max(1, len(edges) // self.MAX_RENDER_EDGES)
            edges = edges[::stride]
        for left, right in edges:
            if left >= len(projected) or right >= len(projected):
                continue
            x1, y1 = projected[left]
            x2, y2 = projected[right]
            self.canvas.create_line(x1, y1, x2, y2, fill="#c3cbd4")
        self._draw_texture_preview(width)
        self._draw_warnings(width, height)

    def _draw_texture_preview(self, width: int) -> None:
        if (
            self.mesh is None
            or not self.mesh.texture_paths
            or not self.show_texture_preview.get()
        ):
            return
        texture_path = Path(self.mesh.texture_paths[0])
        if Image is None or ImageTk is None:
            self.canvas.create_text(
                width - 12,
                12,
                anchor="ne",
                text=f"Texture loaded: {texture_path.name}\nInstall [visual] for preview",
                fill="#f0c674",
                justify="right",
            )
            return
        try:
            with Image.open(texture_path) as source:
                source.load()
                image = source.convert("RGB")
            image.thumbnail((self.TEXTURE_PREVIEW_SIDE, self.TEXTURE_PREVIEW_SIDE))
            self._texture_photo = ImageTk.PhotoImage(image)
            self.canvas.create_image(
                width - 12,
                12,
                anchor="ne",
                image=self._texture_photo,
            )
            self.canvas.create_text(
                width - 12,
                18 + image.height,
                anchor="ne",
                text=(
                    f"{texture_path.name}\n"
                    f"UVs preserved: {'yes' if self.mesh.has_texture_mapping else 'no'}\n"
                    "map preview (not UV-rasterized on Tk surface)"
                ),
                fill="#f0c674",
                justify="right",
            )
        except OSError:
            self.canvas.create_text(
                width - 12,
                12,
                anchor="ne",
                text=f"Texture unavailable: {texture_path.name}",
                fill="#ff8a80",
                justify="right",
            )

    def _draw_warnings(self, width: int, height: int) -> None:
        if self.mesh is None or not self.mesh.warnings:
            return
        text = "\n".join(self.mesh.warnings[:3])
        if len(self.mesh.warnings) > 3:
            text += f"\n+{len(self.mesh.warnings) - 3} more"
        self.canvas.create_text(
            width - 12,
            height - 12,
            anchor="se",
            text=text,
            fill="#ffb86c",
            justify="right",
        )

    def _draw_axes(self, width: int, height: int) -> None:
        origin_x = 34
        origin_y = height - 34
        length = 24
        self.canvas.create_line(origin_x, origin_y, origin_x + length, origin_y, fill="#e37d7d", width=2)
        self.canvas.create_text(origin_x + length + 8, origin_y, text="X", fill="#e37d7d")
        self.canvas.create_line(origin_x, origin_y, origin_x, origin_y - length, fill="#7dcf92", width=2)
        self.canvas.create_text(origin_x, origin_y - length - 8, text="Y", fill="#7dcf92")
        self.canvas.create_line(origin_x, origin_y, origin_x + 15, origin_y + 15, fill="#79aef2", width=2)
        self.canvas.create_text(origin_x + 22, origin_y + 20, text="Z", fill="#79aef2")
