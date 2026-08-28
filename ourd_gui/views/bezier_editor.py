from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
from typing import Callable

from ..visual_assets import VisualAsset
from ..visual_models import BezierCurve3D, BezierScene, Vec3, sample_bezier


VIEW_AXES = {
    "Front X/Z": (0, 2),
    "Top X/Y": (0, 1),
    "Side Y/Z": (1, 2),
}


class _BezierProjectionCanvas(tk.Canvas):
    GRID_STEP = 1.0

    def __init__(
        self,
        master: tk.Misc,
        *,
        view_name: str,
        get_curve: Callable[[], BezierCurve3D | None],
        on_point_changed: Callable[[int, Vec3], None],
    ) -> None:
        super().__init__(master, background="#11151a", highlightthickness=0)
        self.view_name = view_name
        self.axes = VIEW_AXES[view_name]
        self.get_curve = get_curve
        self.on_point_changed = on_point_changed
        self.scale = 70.0
        self._drag_index: int | None = None
        self.bind("<Configure>", lambda event: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda event: self._wheel_delta(1))
        self.bind("<Button-5>", lambda event: self._wheel_delta(-1))

    def _origin(self) -> tuple[float, float]:
        return self.winfo_width() / 2.0, self.winfo_height() / 2.0

    def world_to_screen(self, point: Vec3) -> tuple[float, float]:
        horizontal, vertical = self.axes
        origin_x, origin_y = self._origin()
        return (
            origin_x + point[horizontal] * self.scale,
            origin_y - point[vertical] * self.scale,
        )

    def screen_to_world(self, x: float, y: float, original: Vec3) -> Vec3:
        horizontal, vertical = self.axes
        origin_x, origin_y = self._origin()
        values = list(original)
        values[horizontal] = (x - origin_x) / self.scale
        values[vertical] = -(y - origin_y) / self.scale
        return float(values[0]), float(values[1]), float(values[2])

    def _press(self, event: tk.Event) -> None:
        curve = self.get_curve()
        if curve is None:
            return
        nearest = None
        nearest_distance = 14.0
        for index, point in enumerate(curve.control_points):
            x, y = self.world_to_screen(point)
            distance = ((x - event.x) ** 2 + (y - event.y) ** 2) ** 0.5
            if distance < nearest_distance:
                nearest = index
                nearest_distance = distance
        self._drag_index = nearest

    def _drag(self, event: tk.Event) -> None:
        curve = self.get_curve()
        if curve is None or self._drag_index is None:
            return
        point = self.screen_to_world(
            float(event.x),
            float(event.y),
            curve.control_points[self._drag_index],
        )
        self.on_point_changed(self._drag_index, point)

    def _wheel(self, event: tk.Event) -> None:
        self._wheel_delta(1 if getattr(event, "delta", 0) > 0 else -1)

    def _wheel_delta(self, direction: int) -> None:
        self.scale = max(15.0, min(350.0, self.scale * (1.12 if direction > 0 else 0.89)))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        origin_x, origin_y = self._origin()
        step = max(12.0, self.scale * self.GRID_STEP)
        x = origin_x % step
        while x < width:
            self.create_line(x, 0, x, height, fill="#202730")
            x += step
        y = origin_y % step
        while y < height:
            self.create_line(0, y, width, y, fill="#202730")
            y += step
        self.create_line(0, origin_y, width, origin_y, fill="#59636f", width=2)
        self.create_line(origin_x, 0, origin_x, height, fill="#59636f", width=2)
        self.create_text(8, 8, anchor="nw", text=self.view_name, fill="#d6dde5")
        curve = self.get_curve()
        if curve is None:
            self.create_text(width / 2, height / 2, text="No curve selected", fill="#8e99a5")
            return
        control_screen = [self.world_to_screen(point) for point in curve.control_points]
        self.create_line(*[coordinate for point in control_screen for coordinate in point], fill="#707d8a", dash=(4, 4))
        samples = [self.world_to_screen(point) for point in sample_bezier(curve, 64)]
        if len(samples) >= 2:
            self.create_line(*[coordinate for point in samples for coordinate in point], fill="#8cc4ff", width=3, smooth=False)
        for index, (x, y) in enumerate(control_screen):
            radius = 6 if index in {0, 3} else 5
            self.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#f0c674", outline="#141414", width=1)
            self.create_text(x + 10, y - 10, text=f"P{index}", fill="#f0c674", anchor="sw")


class SupervisedBezierEditor(ttk.Frame):
    """Synchronized front/top/side cubic Bezier editor with staged revisions."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_register_scene: Callable[[bytes, str], VisualAsset] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_register_scene = on_register_scene
        self.accepted = BezierScene(curves=[BezierCurve3D.default()])
        self.working = self.accepted.clone()
        self.selected_curve_id = self.working.curves[0].curve_id
        self.pending = False
        self.reference = ""

        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Add Curve", command=self.add_curve).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete", command=self.delete_curve).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Import JSON", command=self.import_json).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export Accepted", command=self.export_json).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Accept Revision", command=self.accept).pack(side="right", padx=2)
        ttk.Button(toolbar, text="Revert Revision", command=self.revert).pack(side="right", padx=2)

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, padding=4)
        self.curve_list = tk.Listbox(left, exportselection=False, width=24)
        self.curve_list.pack(fill="both", expand=True)
        self.curve_list.bind("<<ListboxSelect>>", self._curve_selected)
        body.add(left, weight=1)

        views = ttk.Frame(body)
        views.columnconfigure(0, weight=1)
        views.columnconfigure(1, weight=1)
        views.columnconfigure(2, weight=1)
        views.rowconfigure(0, weight=1)
        self.canvases: list[_BezierProjectionCanvas] = []
        for column, view_name in enumerate(VIEW_AXES):
            frame = ttk.LabelFrame(views, text=view_name)
            frame.grid(row=0, column=column, sticky="nsew", padx=2, pady=2)
            canvas = _BezierProjectionCanvas(
                frame,
                view_name=view_name,
                get_curve=self.current_curve,
                on_point_changed=self._point_changed,
            )
            canvas.pack(fill="both", expand=True)
            self.canvases.append(canvas)
        body.add(views, weight=5)

        inspector = ttk.Frame(self, padding=4)
        inspector.pack(fill="x")
        self.point_labels = [ttk.Label(inspector, text="") for _ in range(4)]
        for label in self.point_labels:
            label.pack(side="left", padx=(0, 14))
        self.status = ttk.Label(self, text="Accepted revision 0", anchor="w")
        self.status.pack(fill="x", padx=4, pady=2)
        self._refresh_curve_list()
        self._refresh_all()

    def current_curve(self) -> BezierCurve3D | None:
        for curve in self.working.curves:
            if curve.curve_id == self.selected_curve_id:
                return curve
        return self.working.curves[0] if self.working.curves else None

    def _set_current_curve(self, curve: BezierCurve3D) -> None:
        for index, candidate in enumerate(self.working.curves):
            if candidate.curve_id == curve.curve_id:
                self.working.curves[index] = curve
                return
        raise KeyError(curve.curve_id)

    def _point_changed(self, index: int, point: Vec3) -> None:
        curve = self.current_curve()
        if curve is None:
            return
        self._set_current_curve(curve.with_point(index, point))
        self.pending = True
        self._refresh_all()

    def add_curve(self, name: str | None = None) -> BezierCurve3D:
        if name is None:
            name = simpledialog.askstring("Add 3D Bezier curve", "Curve name:")
        name = (name or f"Curve {len(self.working.curves) + 1}").strip()
        curve = BezierCurve3D.default(name)
        self.working.curves.append(curve)
        self.selected_curve_id = curve.curve_id
        self.pending = True
        self._refresh_curve_list()
        self._refresh_all()
        return curve

    def delete_curve(self) -> None:
        if not self.working.curves:
            return
        self.working.curves = [curve for curve in self.working.curves if curve.curve_id != self.selected_curve_id]
        self.selected_curve_id = self.working.curves[0].curve_id if self.working.curves else ""
        self.pending = True
        self._refresh_curve_list()
        self._refresh_all()

    def _curve_selected(self, event: tk.Event) -> None:
        del event
        selection = self.curve_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self.working.curves):
            self.selected_curve_id = self.working.curves[index].curve_id
            self._refresh_all()

    def accept(self) -> VisualAsset | None:
        if not self.pending:
            self.status.configure(text="No pending 3D curve edits to accept.")
            return None
        self.working.revision = self.accepted.revision + 1
        self.accepted = self.working.clone()
        self.pending = False
        asset = None
        if self.on_register_scene is not None:
            asset = self.on_register_scene(
                self.accepted.to_json().encode("utf-8"),
                f"bezier-scene-r{self.accepted.revision}.bezier3d.json",
            )
            self.reference = asset.reference
        self.status.configure(
            text=f"Accepted revision {self.accepted.revision} | {self.reference or 'not registered'}"
        )
        self._refresh_all()
        return asset

    def revert(self) -> None:
        self.working = self.accepted.clone()
        self.selected_curve_id = self.working.curves[0].curve_id if self.working.curves else ""
        self.pending = False
        self._refresh_curve_list()
        self.status.configure(text=f"Reverted to accepted revision {self.accepted.revision}")
        self._refresh_all()

    def load_scene(self, scene: BezierScene, *, reference: str = "") -> None:
        self.accepted = scene.clone()
        self.working = scene.clone()
        self.reference = reference
        self.selected_curve_id = scene.curves[0].curve_id if scene.curves else ""
        self.pending = False
        self._refresh_curve_list()
        self.status.configure(text=f"Loaded revision {scene.revision} | {reference}")
        self._refresh_all()

    def import_json(self) -> None:
        filename = filedialog.askopenfilename(
            title="Import 3D Bezier scene",
            filetypes=[("Bezier 3D JSON", "*.json"), ("All files", "*")],
        )
        if not filename:
            return
        scene = BezierScene.from_json(Path(filename).read_text(encoding="utf-8"))
        self.load_scene(scene)

    def export_json(self) -> Path | None:
        filename = filedialog.asksaveasfilename(
            title="Export accepted 3D Bezier scene",
            defaultextension=".bezier3d.json",
            filetypes=[("Bezier 3D JSON", "*.json"), ("JSON", "*.json")],
        )
        if not filename:
            return None
        path = Path(filename)
        path.write_text(self.accepted.to_json(), encoding="utf-8")
        self.status.configure(text=f"Exported accepted revision {self.accepted.revision} to {path}")
        return path

    def _refresh_curve_list(self) -> None:
        self.curve_list.delete(0, "end")
        selected_index = -1
        for index, curve in enumerate(self.working.curves):
            self.curve_list.insert("end", curve.name)
            if curve.curve_id == self.selected_curve_id:
                selected_index = index
        if selected_index >= 0:
            self.curve_list.selection_set(selected_index)
            self.curve_list.see(selected_index)

    def _refresh_all(self) -> None:
        curve = self.current_curve()
        for canvas in self.canvases:
            canvas.redraw()
        if curve is None:
            for label in self.point_labels:
                label.configure(text="")
        else:
            for index, point in enumerate(curve.control_points):
                self.point_labels[index].configure(
                    text=f"P{index}=({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})"
                )
        if self.pending:
            self.status.configure(
                text=f"PENDING supervision | accepted r{self.accepted.revision} | drag control points in any view"
            )
