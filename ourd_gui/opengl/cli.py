from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..visual_assets import VisualAsset, VisualAssetRegistry
from ..visual_models import load_mesh
from .math3d import RenderCamera
from .renderer import OpenGLUnavailable, RENDER_MODES
from .service import OpenGLRenderService


class OpenGLVisualCLI:
    def __init__(
        self,
        registry: VisualAssetRegistry,
        mesh_viewer,
        *,
        append: Callable[[str, str], None],
        refresh_assets: Callable[[], None],
        show_asset: Callable[[VisualAsset], None],
    ) -> None:
        self.registry = registry
        self.mesh_viewer = mesh_viewer
        self.append = append
        self.refresh_assets = refresh_assets
        self.show_asset = show_asset
        self._service: OpenGLRenderService | None = None

    @staticmethod
    def handles(command: str) -> bool:
        return command.casefold() in {"gl-info", "render", "render-3view"}

    def close(self) -> None:
        if self._service is not None:
            self._service.close()
            self._service = None

    def _renderer(self) -> OpenGLRenderService:
        if self._service is None:
            self._service = OpenGLRenderService()
        return self._service

    def dispatch(self, argv: list[str]) -> None:
        if not argv:
            return
        command = argv[0].casefold()
        positional, options = _split_options(argv[1:])
        if command == "gl-info":
            self._info(positional, options)
        elif command == "render":
            self._render(positional, options)
        elif command == "render-3view":
            self._render_three(positional, options)
        else:
            raise ValueError(f"unknown OpenGL command: {argv[0]}")

    def _mesh(self, reference: str):
        asset = self.registry.get(reference)
        if asset.kind != "mesh":
            raise ValueError(f"{reference} is {asset.kind}, expected mesh")
        return asset, load_mesh(self.registry.path_for(reference))

    def _info(self, positional: list[str], options: dict[str, str]) -> None:
        if positional or options:
            raise ValueError("usage: gl-info")
        capabilities = self._renderer().capabilities()
        self.append("OPENGL", json.dumps(capabilities.to_dict(), indent=2))

    def _render(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) != 1:
            raise ValueError(
                "usage: render MESH [mode=textured|material|vertex-color|wireframe|silhouette|normal|depth] "
                "[view=perspective|front|top|side] [size=512] [orientation=world|camera]"
            )
        asset, mesh = self._mesh(positional[0])
        mode = options.get("mode", "textured").casefold()
        if mode not in RENDER_MODES:
            raise ValueError(f"unknown render mode: {mode}")
        view = options.get("view", "perspective").casefold()
        if view not in {"perspective", "front", "top", "side"}:
            raise ValueError("view must be perspective, front, top, or side")
        size = max(32, min(int(options.get("size", "512")), 4096))
        orientation = options.get("orientation", "world").casefold()
        if orientation not in {"world", "camera"}:
            raise ValueError("orientation must be world or camera")
        model_yaw = float(self.mesh_viewer.yaw) if orientation == "camera" and view != "perspective" else 0.0
        model_pitch = float(self.mesh_viewer.pitch) if orientation == "camera" and view != "perspective" else 0.0
        camera = (
            RenderCamera(
                view="perspective",
                yaw=float(self.mesh_viewer.yaw),
                pitch=float(self.mesh_viewer.pitch),
                distance=max(1.2, 3.6 / max(0.15, float(self.mesh_viewer.zoom))),
            )
            if view == "perspective"
            else RenderCamera(view=view, ortho_scale=max(0.3, 1.15 / max(0.15, float(self.mesh_viewer.zoom))))
        )
        frame = self._renderer().render(
            mesh,
            cache_key=asset.reference,
            mode=mode,
            width=size,
            height=size,
            camera=camera,
            model_yaw=model_yaw,
            model_pitch=model_pitch,
        )
        rendered = self.registry.register_bytes(
            frame.to_png_bytes(),
            filename=f"{Path(asset.filename).stem}-gl-{view}-{mode}.png",
            kind="image",
            media_type="image/png",
        )
        self.refresh_assets()
        self.show_asset(rendered)
        self.append(
            "OPENGL RENDER",
            f"{asset.reference} -> {rendered.reference} | mode={mode} view={view} "
            f"size={size} backend={frame.backend}",
        )

    def _render_three(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) != 1:
            raise ValueError(
                "usage: render-3view MESH [mode=textured|material|vertex-color|wireframe|silhouette|normal|depth] "
                "[size=512] [orientation=world|camera]"
            )
        asset, mesh = self._mesh(positional[0])
        mode = options.get("mode", "textured").casefold()
        if mode not in RENDER_MODES:
            raise ValueError(f"unknown render mode: {mode}")
        size = max(32, min(int(options.get("size", "512")), 4096))
        orientation = options.get("orientation", "world").casefold()
        if orientation not in {"world", "camera"}:
            raise ValueError("orientation must be world or camera")
        yaw = float(self.mesh_viewer.yaw) if orientation == "camera" else 0.0
        pitch = float(self.mesh_viewer.pitch) if orientation == "camera" else 0.0
        frames = self._renderer().render_three_views(
            mesh,
            cache_key=asset.reference,
            mode=mode,
            size=size,
            model_yaw=yaw,
            model_pitch=pitch,
        )
        references: dict[str, str] = {}
        stem = Path(asset.filename).stem
        for view, frame in frames.items():
            image_asset = self.registry.register_bytes(
                frame.to_png_bytes(),
                filename=f"{stem}-gl-{orientation}-{view}-{mode}.png",
                kind="image",
                media_type="image/png",
            )
            references[view] = image_asset.reference
        report = self.registry.register_bytes(
            (json.dumps(
                {
                    "type": "opengl_three_view_render",
                    "mesh": asset.reference,
                    "mode": mode,
                    "orientation": orientation,
                    "size": size,
                    "yaw_radians": yaw,
                    "pitch_radians": pitch,
                    "views": references,
                    "capabilities": self._renderer().capabilities().to_dict(),
                },
                indent=2,
                sort_keys=True,
            ) + "\n").encode("utf-8"),
            filename="opengl-three-view.json",
            kind="report",
            media_type="application/json",
        )
        self.refresh_assets()
        self.append(
            "OPENGL 3VIEW",
            " | ".join(f"{view}={reference}" for view, reference in references.items())
            + f" | report={report.reference}",
        )


def _split_options(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    options: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            positional.append(token)
            continue
        name, value = token.split("=", 1)
        name = name.strip().casefold()
        value = value.strip()
        if not name or not value:
            raise ValueError(f"invalid option: {token}")
        if name in options:
            raise ValueError(f"duplicate option: {name}")
        options[name] = value
    return positional, options
