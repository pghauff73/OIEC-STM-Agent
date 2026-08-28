from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from ..visual_models import MeshData, normalize_vertices, rotate_point


class MeshViewer(ttk.Frame):
    """Bounded Tk canvas wireframe viewer for OBJ/STL meshes."""

    MAX_RENDER_EDGES = 25_000

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
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
        self.canvas.bind("<Configure>", lambda event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda event: self._wheel_delta(1))
        self.canvas.bind("<Button-5>", lambda event: self._wheel_delta(-1))

    def set_mesh(self, mesh: MeshData) -> None:
        self.mesh = mesh
        self.vertices = normalize_vertices(mesh.vertices)
        self.status.configure(
            text=f"{mesh.name} | vertices={len(mesh.vertices):,} | edges={len(mesh.edges):,}"
        )
        self.redraw()

    def clear(self) -> None:
        self.mesh = None
        self.vertices = ()
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

    def redraw(self) -> None:
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self._draw_axes(width, height)
        if self.mesh is None or not self.vertices:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Load an OBJ or STL object",
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
