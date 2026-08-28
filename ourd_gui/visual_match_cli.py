from __future__ import annotations

from pathlib import Path
from typing import Callable

from .visual_assets import VisualAsset, VisualAssetRegistry
from .visual_models import load_mesh
from .visual_similarity import (
    DEFAULT_COMPARE_SIZE,
    METHODS,
    PROFILE_WEIGHTS,
    classify_images_to_three_views,
    compare_images,
    image_to_png_bytes,
    match_three_views,
    render_mesh_three_views,
    report_json,
)


class VisualMatchCLI:
    """Deterministic similarity commands for the GUI visual CLI."""

    def __init__(
        self,
        registry: VisualAssetRegistry,
        mesh_viewer,
        *,
        append: Callable[[str, str], None],
        refresh_assets: Callable[[], None],
    ) -> None:
        self.registry = registry
        self.mesh_viewer = mesh_viewer
        self.append = append
        self.refresh_assets = refresh_assets

    @staticmethod
    def handles(command: str) -> bool:
        return command.casefold() in {
            "match",
            "match-matrix",
            "mesh-views",
            "match-3view",
            "classify-3view",
        }

    def dispatch(self, argv: list[str]) -> None:
        if not argv:
            return
        command = argv[0].casefold()
        positional, options = _split_options(argv[1:])
        if command == "match":
            self._match(positional, options)
        elif command == "match-matrix":
            self._match_matrix(positional, options)
        elif command == "mesh-views":
            self._mesh_views(positional, options)
        elif command == "match-3view":
            self._match_three(positional, options)
        elif command == "classify-3view":
            self._classify_three(positional, options)
        else:
            raise ValueError(f"unknown match command: {argv[0]}")

    def _image(self, reference: str) -> tuple[VisualAsset, Path]:
        asset = self.registry.get(reference)
        if asset.kind != "image":
            raise ValueError(f"{reference} is {asset.kind}, expected image")
        return asset, self.registry.path_for(reference)

    def _mesh(self, reference: str):
        asset = self.registry.get(reference)
        if asset.kind != "mesh":
            raise ValueError(f"{reference} is {asset.kind}, expected mesh")
        return asset, load_mesh(self.registry.path_for(reference))

    def _orientation(self, options: dict[str, str]) -> tuple[str, float, float]:
        orientation = options.get("orientation", "world").casefold()
        if orientation == "world":
            return orientation, 0.0, 0.0
        if orientation == "camera":
            return orientation, float(self.mesh_viewer.yaw), float(self.mesh_viewer.pitch)
        raise ValueError("orientation must be world or camera")

    @staticmethod
    def _common(options: dict[str, str], *, default_profile: str) -> tuple[str, str, str, int]:
        method = options.get("method", "all").casefold()
        profile = options.get("profile", default_profile).casefold()
        preprocess = options.get("preprocess", "edge-fit" if profile == "shape" else "fit").casefold()
        size = int(options.get("size", DEFAULT_COMPARE_SIZE))
        if method != "all" and method not in METHODS:
            raise ValueError(f"method must be all or one of {', '.join(METHODS)}")
        if profile not in PROFILE_WEIGHTS:
            raise ValueError(f"profile must be one of {', '.join(PROFILE_WEIGHTS)}")
        return method, profile, preprocess, size

    def _register_report(self, payload: object, filename: str) -> VisualAsset:
        asset = self.registry.register_bytes(
            report_json(payload),
            filename=filename,
            kind="report",
            media_type="application/json",
        )
        self.refresh_assets()
        self.append("REPORT", f"{asset.reference} <- {filename}")
        return asset

    def _register_views(
        self,
        mesh_asset: VisualAsset,
        mesh,
        *,
        orientation: str,
        yaw: float,
        pitch: float,
        size: int,
    ) -> dict[str, VisualAsset]:
        images = render_mesh_three_views(mesh, size=size, yaw=yaw, pitch=pitch)
        stem = Path(mesh_asset.filename).stem
        assets: dict[str, VisualAsset] = {}
        for view, image in images.items():
            assets[view] = self.registry.register_bytes(
                image_to_png_bytes(image),
                filename=f"{stem}-{orientation}-{view}.png",
                kind="image",
                media_type="image/png",
            )
        self.refresh_assets()
        return assets

    def _match(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) != 2:
            raise ValueError(
                "usage: match IMG1 IMG2 [method=all] [profile=balanced] "
                "[preprocess=fit|edge-fit|stretch] [size=256]"
            )
        method, profile, preprocess, size = self._common(options, default_profile="balanced")
        left_asset, left_path = self._image(positional[0])
        right_asset, right_path = self._image(positional[1])
        report = compare_images(
            left_path,
            right_path,
            left_name=left_asset.reference,
            right_name=right_asset.reference,
            method=method,
            profile=profile,
            preprocess=preprocess,
            size=size,
        )
        report_asset = self._register_report(report, "image-match.json")
        self.append(
            "MATCH",
            f"{left_asset.reference} vs {right_asset.reference} | "
            f"{_score_text(report.composite_bp)} | {_metrics_text(report)} | {report_asset.reference}",
        )

    def _match_matrix(self, positional: list[str], options: dict[str, str]) -> None:
        if not 2 <= len(positional) <= 12:
            raise ValueError(
                "usage: match-matrix IMG1 IMG2 [IMG3 ...] [method=all] "
                "[profile=balanced] [preprocess=fit] [size=256]"
            )
        method, profile, preprocess, size = self._common(options, default_profile="balanced")
        assets = [self._image(reference) for reference in positional]
        matrix: dict[str, dict[str, int]] = {asset.reference: {} for asset, _ in assets}
        pair_reports = []
        for index, (left_asset, left_path) in enumerate(assets):
            matrix[left_asset.reference][left_asset.reference] = 10_000
            for right_asset, right_path in assets[index + 1 :]:
                report = compare_images(
                    left_path,
                    right_path,
                    left_name=left_asset.reference,
                    right_name=right_asset.reference,
                    method=method,
                    profile=profile,
                    preprocess=preprocess,
                    size=size,
                )
                matrix[left_asset.reference][right_asset.reference] = report.composite_bp
                matrix[right_asset.reference][left_asset.reference] = report.composite_bp
                pair_reports.append(report.to_dict())
        payload = {
            "type": "image_similarity_matrix",
            "method": method,
            "profile": profile,
            "preprocess": preprocess,
            "size": size,
            "matrix_bp": matrix,
            "pairs": pair_reports,
        }
        report_asset = self._register_report(payload, "image-match-matrix.json")
        ordered = [asset.reference for asset, _ in assets]
        lines = ["similarity matrix (%):"]
        lines.append("             " + " ".join(reference[-6:].rjust(7) for reference in ordered))
        for reference in ordered:
            values = " ".join(f"{matrix[reference][other] / 100:6.1f}" for other in ordered)
            lines.append(f"{reference[-6:]:>11} {values}")
        lines.append(f"report={report_asset.reference}")
        self.append("MATCH", "\n".join(lines))

    def _mesh_views(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) != 1:
            raise ValueError("usage: mesh-views MESH [orientation=world|camera] [size=512]")
        mesh_asset, mesh = self._mesh(positional[0])
        orientation, yaw, pitch = self._orientation(options)
        size = int(options.get("size", "512"))
        views = self._register_views(
            mesh_asset,
            mesh,
            orientation=orientation,
            yaw=yaw,
            pitch=pitch,
            size=size,
        )
        payload = {
            "type": "mesh_three_views",
            "mesh": mesh_asset.reference,
            "orientation": orientation,
            "yaw_radians": yaw,
            "pitch_radians": pitch,
            "views": {view: asset.reference for view, asset in views.items()},
        }
        report_asset = self._register_report(payload, "mesh-three-views.json")
        self.append(
            "3VIEW",
            " | ".join(f"{view}={asset.reference}" for view, asset in views.items())
            + f" | report={report_asset.reference}",
        )

    def _match_three(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) != 1:
            raise ValueError(
                "usage: match-3view MESH front=IMG top=IMG side=IMG "
                "[orientation=world|camera] [method=all] [profile=shape] "
                "[preprocess=edge-fit] [size=256]"
            )
        required = {view: options.get(view, "") for view in ("front", "top", "side")}
        missing = [view for view, reference in required.items() if not reference]
        if missing:
            raise ValueError(f"missing three-view options: {', '.join(missing)}")
        method, profile, preprocess, size = self._common(options, default_profile="shape")
        mesh_asset, mesh = self._mesh(positional[0])
        orientation, yaw, pitch = self._orientation(options)
        reference_assets = {view: self._image(reference)[0] for view, reference in required.items()}
        reference_paths = {
            view: self.registry.path_for(asset.reference)
            for view, asset in reference_assets.items()
        }
        generated = self._register_views(
            mesh_asset,
            mesh,
            orientation=orientation,
            yaw=yaw,
            pitch=pitch,
            size=max(256, size),
        )
        report = match_three_views(
            mesh,
            reference_paths,
            mesh_name=mesh_asset.reference,
            generated_names={view: asset.reference for view, asset in generated.items()},
            reference_names={view: asset.reference for view, asset in reference_assets.items()},
            orientation=orientation,
            yaw=yaw,
            pitch=pitch,
            method=method,
            profile=profile,
            preprocess=preprocess,
            size=size,
        )
        report_asset = self._register_report(report, "three-view-match.json")
        per_view = " | ".join(
            f"{view}={_score_text(view_report.composite_bp)}"
            for view, view_report in report.reports.items()
        )
        self.append(
            "3VIEW MATCH",
            f"aggregate={_score_text(report.aggregate_bp)} | {per_view} | {report_asset.reference}",
        )

    def _classify_three(self, positional: list[str], options: dict[str, str]) -> None:
        if len(positional) < 2:
            raise ValueError(
                "usage: classify-3view MESH IMG1 [IMG2 ... IMG12] "
                "[orientation=world|camera] [method=all] [profile=shape] "
                "[preprocess=edge-fit] [size=256]"
            )
        method, profile, preprocess, size = self._common(options, default_profile="shape")
        mesh_asset, mesh = self._mesh(positional[0])
        orientation, yaw, pitch = self._orientation(options)
        candidate_assets = [self._image(reference)[0] for reference in positional[1:]]
        candidates = {
            asset.reference: self.registry.path_for(asset.reference)
            for asset in candidate_assets
        }
        generated = self._register_views(
            mesh_asset,
            mesh,
            orientation=orientation,
            yaw=yaw,
            pitch=pitch,
            size=max(256, size),
        )
        report = classify_images_to_three_views(
            mesh,
            candidates,
            mesh_name=mesh_asset.reference,
            orientation=orientation,
            yaw=yaw,
            pitch=pitch,
            method=method,
            profile=profile,
            preprocess=preprocess,
            size=size,
        )
        payload = report.to_dict()
        payload["generated_views"] = {view: asset.reference for view, asset in generated.items()}
        report_asset = self._register_report(payload, "three-view-classification.json")
        assignments = " | ".join(
            f"{view}={reference}"
            for view, reference in sorted(report.assignment.items())
        )
        self.append(
            "3VIEW CLASSIFY",
            f"{assignments} | aggregate={_score_text(report.aggregate_bp)} | "
            f"unassigned={list(report.unassigned)} | {report_asset.reference}",
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


def _score_text(score_bp: int) -> str:
    return f"{score_bp / 100:.2f}%"


def _metrics_text(report) -> str:
    return ", ".join(
        f"{metric.method}={_score_text(metric.score_bp)}"
        for metric in report.metrics
    )
