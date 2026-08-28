from __future__ import annotations

import io
import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .visual_models import MeshData, normalize_vertices, rotate_point

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - optional visual dependency
    Image = ImageDraw = ImageFilter = ImageOps = None  # type: ignore[assignment]


SCORE_SCALE = 10_000
DEFAULT_COMPARE_SIZE = 256
MAX_COMPARE_SIZE = 1024
MAX_CLASSIFY_IMAGES = 12
VIEW_AXES = {
    "front": (0, 2),  # X / Z, matching the Bezier front view
    "top": (0, 1),    # X / Y
    "side": (1, 2),   # Y / Z
}

METHODS = (
    "mse",
    "ncc",
    "ssim-global",
    "histogram",
    "edge-dice",
    "edge-chamfer",
)

PROFILE_WEIGHTS: dict[str, dict[str, int]] = {
    "balanced": {
        "mse": 15,
        "ncc": 20,
        "ssim-global": 20,
        "histogram": 15,
        "edge-dice": 15,
        "edge-chamfer": 15,
    },
    "appearance": {
        "mse": 20,
        "ncc": 25,
        "ssim-global": 25,
        "histogram": 30,
    },
    "shape": {
        "ncc": 15,
        "ssim-global": 10,
        "edge-dice": 35,
        "edge-chamfer": 40,
    },
}


@dataclass(frozen=True)
class MetricScore:
    method: str
    score_bp: int
    details: Mapping[str, Any]


@dataclass(frozen=True)
class ImageMatchReport:
    left: str
    right: str
    preprocess: str
    compare_size: int
    profile: str
    metrics: tuple[MetricScore, ...]
    composite_bp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "metrics": [asdict(metric) for metric in self.metrics],
        }


@dataclass(frozen=True)
class ThreeViewReport:
    mesh: str
    orientation: str
    yaw_radians: float
    pitch_radians: float
    method: str
    profile: str
    generated_views: Mapping[str, str]
    reference_views: Mapping[str, str]
    reports: Mapping[str, ImageMatchReport]
    aggregate_bp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mesh": self.mesh,
            "orientation": self.orientation,
            "yaw_radians": self.yaw_radians,
            "pitch_radians": self.pitch_radians,
            "method": self.method,
            "profile": self.profile,
            "generated_views": dict(self.generated_views),
            "reference_views": dict(self.reference_views),
            "reports": {name: report.to_dict() for name, report in self.reports.items()},
            "aggregate_bp": self.aggregate_bp,
        }


@dataclass(frozen=True)
class ViewClassificationReport:
    mesh: str
    orientation: str
    method: str
    profile: str
    scores: Mapping[str, Mapping[str, int]]
    assignment: Mapping[str, str]
    aggregate_bp: int
    unassigned: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def require_pillow() -> None:
    if Image is None:
        raise RuntimeError(
            "visual similarity requires Pillow; install with `pip install -e '.[visual]'`"
        )


def _clamp_score(value: float) -> int:
    if not math.isfinite(value):
        return 0
    return max(0, min(SCORE_SCALE, int(round(value * SCORE_SCALE))))


def _open_grayscale(source: Path | Any):
    require_pillow()
    if isinstance(source, Path):
        with Image.open(source) as raw:
            raw.load()
            image = ImageOps.exif_transpose(raw).convert("RGBA")
    elif hasattr(source, "convert"):
        image = source.convert("RGBA")
    else:
        raise TypeError("image source must be a pathlib.Path or Pillow Image")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    background.alpha_composite(image)
    return background.convert("L")


def _edge_image(image):
    edge = image.filter(ImageFilter.FIND_EDGES)
    edge = edge.point(lambda value: 255 if value >= 28 else 0, mode="L")
    if edge.width > 4 and edge.height > 4:
        draw = ImageDraw.Draw(edge)
        draw.rectangle((0, 0, edge.width - 1, edge.height - 1), outline=0, width=2)
    return edge


def _contain(image, size: int):
    canvas = Image.new("L", (size, size), 255)
    copy = image.copy()
    copy.thumbnail((size, size), Image.Resampling.LANCZOS)
    left = (size - copy.width) // 2
    top = (size - copy.height) // 2
    canvas.paste(copy, (left, top))
    return canvas


def prepare_image(source: Path | Any, *, size: int = DEFAULT_COMPARE_SIZE, preprocess: str = "fit"):
    require_pillow()
    size = max(32, min(int(size), MAX_COMPARE_SIZE))
    preprocess = preprocess.casefold()
    if preprocess not in {"fit", "edge-fit", "stretch"}:
        raise ValueError("preprocess must be fit, edge-fit, or stretch")
    image = _open_grayscale(source)
    if preprocess == "stretch":
        return image.resize((size, size), Image.Resampling.LANCZOS)
    if preprocess == "edge-fit":
        edges = _edge_image(image)
        bbox = edges.getbbox()
        if bbox is not None and (bbox[2] - bbox[0]) >= 4 and (bbox[3] - bbox[1]) >= 4:
            image = image.crop(bbox)
    return _contain(image, size)


def _pixels(image) -> list[float]:
    return [float(value) for value in image.getdata()]


def _mse(left, right) -> MetricScore:
    a = _pixels(left)
    b = _pixels(right)
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / max(1, len(a))
    score = 1.0 - min(1.0, mse / (255.0 * 255.0))
    return MetricScore("mse", _clamp_score(score), {"mse": mse})


def _ncc(left, right) -> MetricScore:
    a = _pixels(left)
    b = _pixels(right)
    count = max(1, len(a))
    mean_a = sum(a) / count
    mean_b = sum(b) / count
    da = [value - mean_a for value in a]
    db = [value - mean_b for value in b]
    numerator = sum(x * y for x, y in zip(da, db))
    denominator = math.sqrt(sum(x * x for x in da) * sum(y * y for y in db))
    correlation = numerator / denominator if denominator > 1e-12 else (1.0 if a == b else 0.0)
    score = max(0.0, min(1.0, correlation))
    return MetricScore("ncc", _clamp_score(score), {"correlation": correlation})


def _ssim_global(left, right) -> MetricScore:
    a = _pixels(left)
    b = _pixels(right)
    count = max(1, len(a))
    mean_a = sum(a) / count
    mean_b = sum(b) / count
    variance_a = sum((value - mean_a) ** 2 for value in a) / count
    variance_b = sum((value - mean_b) ** 2 for value in b) / count
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / count
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    denominator = (mean_a * mean_a + mean_b * mean_b + c1) * (
        variance_a + variance_b + c2
    )
    ssim = (
        ((2.0 * mean_a * mean_b + c1) * (2.0 * covariance + c2)) / denominator
        if denominator > 1e-12
        else 1.0
    )
    score = max(0.0, min(1.0, ssim))
    return MetricScore("ssim-global", _clamp_score(score), {"ssim": ssim})


def _histogram(left, right) -> MetricScore:
    bins = 64
    hist_a = [0.0] * bins
    hist_b = [0.0] * bins
    for value in left.getdata():
        hist_a[min(bins - 1, int(value) * bins // 256)] += 1.0
    for value in right.getdata():
        hist_b[min(bins - 1, int(value) * bins // 256)] += 1.0
    dot = sum(x * y for x, y in zip(hist_a, hist_b))
    norm = math.sqrt(sum(x * x for x in hist_a) * sum(y * y for y in hist_b))
    cosine = dot / norm if norm > 1e-12 else 0.0
    return MetricScore("histogram", _clamp_score(cosine), {"cosine": cosine, "bins": bins})


def _edge_mask(image) -> list[bool]:
    edge = _edge_image(image)
    edge = edge.filter(ImageFilter.MaxFilter(3))
    return [value > 0 for value in edge.getdata()]


def _edge_dice(left, right) -> MetricScore:
    a = _edge_mask(left)
    b = _edge_mask(right)
    count_a = sum(a)
    count_b = sum(b)
    intersection = sum(x and y for x, y in zip(a, b))
    if count_a + count_b == 0:
        dice = 1.0
    else:
        dice = 2.0 * intersection / (count_a + count_b)
    return MetricScore(
        "edge-dice",
        _clamp_score(dice),
        {"dice": dice, "edge_pixels_left": count_a, "edge_pixels_right": count_b},
    )


def _distance_transform(mask: Sequence[bool], width: int, height: int) -> list[float]:
    infinity = float(width + height + 1)
    distance = [0.0 if value else infinity for value in mask]
    root2 = math.sqrt(2.0)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            current = distance[index]
            if x > 0:
                current = min(current, distance[index - 1] + 1.0)
            if y > 0:
                current = min(current, distance[index - width] + 1.0)
                if x > 0:
                    current = min(current, distance[index - width - 1] + root2)
                if x + 1 < width:
                    current = min(current, distance[index - width + 1] + root2)
            distance[index] = current
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            index = y * width + x
            current = distance[index]
            if x + 1 < width:
                current = min(current, distance[index + 1] + 1.0)
            if y + 1 < height:
                current = min(current, distance[index + width] + 1.0)
                if x > 0:
                    current = min(current, distance[index + width - 1] + root2)
                if x + 1 < width:
                    current = min(current, distance[index + width + 1] + root2)
            distance[index] = current
    return distance


def _edge_chamfer(left, right) -> MetricScore:
    mask_a = _edge_mask(left)
    mask_b = _edge_mask(right)
    width, height = left.size
    indices_a = [index for index, value in enumerate(mask_a) if value]
    indices_b = [index for index, value in enumerate(mask_b) if value]
    if not indices_a and not indices_b:
        return MetricScore("edge-chamfer", SCORE_SCALE, {"mean_distance": 0.0})
    if not indices_a or not indices_b:
        return MetricScore("edge-chamfer", 0, {"mean_distance": float(width + height)})
    distance_to_b = _distance_transform(mask_b, width, height)
    distance_to_a = _distance_transform(mask_a, width, height)
    mean_a = sum(distance_to_b[index] for index in indices_a) / len(indices_a)
    mean_b = sum(distance_to_a[index] for index in indices_b) / len(indices_b)
    mean_distance = (mean_a + mean_b) / 2.0
    scale = max(2.0, min(width, height) * 0.035)
    similarity = math.exp(-mean_distance / scale)
    return MetricScore(
        "edge-chamfer",
        _clamp_score(similarity),
        {"mean_distance": mean_distance, "distance_scale": scale},
    )


_METRIC_FUNCTIONS = {
    "mse": _mse,
    "ncc": _ncc,
    "ssim-global": _ssim_global,
    "histogram": _histogram,
    "edge-dice": _edge_dice,
    "edge-chamfer": _edge_chamfer,
}


def compare_images(
    left_source: Path | Any,
    right_source: Path | Any,
    *,
    left_name: str = "left",
    right_name: str = "right",
    method: str = "all",
    profile: str = "balanced",
    preprocess: str = "fit",
    size: int = DEFAULT_COMPARE_SIZE,
) -> ImageMatchReport:
    require_pillow()
    profile = profile.casefold()
    if profile not in PROFILE_WEIGHTS:
        raise ValueError(f"unknown match profile: {profile}")
    method = method.casefold()
    if method != "all" and method not in METHODS:
        raise ValueError(f"unknown match method: {method}")
    size = max(32, min(int(size), MAX_COMPARE_SIZE))
    left = prepare_image(left_source, size=size, preprocess=preprocess)
    right = prepare_image(right_source, size=size, preprocess=preprocess)
    selected = METHODS if method == "all" else (method,)
    metrics = tuple(_METRIC_FUNCTIONS[name](left, right) for name in selected)
    if method == "all":
        weights = PROFILE_WEIGHTS[profile]
        weighted = [
            (metric.score_bp, weights.get(metric.method, 0))
            for metric in metrics
            if weights.get(metric.method, 0) > 0
        ]
        total_weight = sum(weight for _, weight in weighted)
        composite = (
            int(round(sum(score * weight for score, weight in weighted) / total_weight))
            if total_weight
            else 0
        )
    else:
        composite = metrics[0].score_bp
    return ImageMatchReport(
        left=left_name,
        right=right_name,
        preprocess=preprocess,
        compare_size=size,
        profile=profile,
        metrics=metrics,
        composite_bp=composite,
    )


def image_to_png_bytes(image) -> bytes:
    require_pillow()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_mesh_view(
    mesh: MeshData,
    view: str,
    *,
    size: int = 512,
    yaw: float = 0.0,
    pitch: float = 0.0,
    line_width: int = 2,
):
    require_pillow()
    view = view.casefold()
    if view not in VIEW_AXES:
        raise ValueError(f"unknown orthographic view: {view}")
    size = max(64, min(int(size), MAX_COMPARE_SIZE))
    line_width = max(1, min(int(line_width), 8))
    vertices = normalize_vertices(mesh.vertices)
    if yaw or pitch:
        vertices = tuple(rotate_point(point, yaw, pitch) for point in vertices)
    horizontal, vertical = VIEW_AXES[view]
    projected = [(point[horizontal], point[vertical]) for point in vertices]
    image = Image.new("L", (size, size), 255)
    if not projected:
        return image
    minimum_x = min(point[0] for point in projected)
    maximum_x = max(point[0] for point in projected)
    minimum_y = min(point[1] for point in projected)
    maximum_y = max(point[1] for point in projected)
    extent = max(maximum_x - minimum_x, maximum_y - minimum_y, 1e-9)
    padding = max(8, int(size * 0.06))
    scale = (size - 2 * padding) / extent
    center_x = (minimum_x + maximum_x) / 2.0
    center_y = (minimum_y + maximum_y) / 2.0
    screen = [
        (
            size / 2.0 + (x - center_x) * scale,
            size / 2.0 - (y - center_y) * scale,
        )
        for x, y in projected
    ]
    draw = ImageDraw.Draw(image)
    edges = mesh.edges
    if len(edges) > 50_000:
        stride = max(1, len(edges) // 50_000)
        edges = edges[::stride]
    for left, right in edges:
        if 0 <= left < len(screen) and 0 <= right < len(screen):
            draw.line((screen[left], screen[right]), fill=0, width=line_width)
    return image


def render_mesh_three_views(
    mesh: MeshData,
    *,
    size: int = 512,
    yaw: float = 0.0,
    pitch: float = 0.0,
) -> dict[str, Any]:
    return {
        view: render_mesh_view(mesh, view, size=size, yaw=yaw, pitch=pitch)
        for view in VIEW_AXES
    }


def match_three_views(
    mesh: MeshData,
    reference_sources: Mapping[str, Path | Any],
    *,
    mesh_name: str,
    generated_names: Mapping[str, str],
    reference_names: Mapping[str, str],
    orientation: str = "world",
    yaw: float = 0.0,
    pitch: float = 0.0,
    method: str = "all",
    profile: str = "shape",
    preprocess: str = "edge-fit",
    size: int = DEFAULT_COMPARE_SIZE,
) -> ThreeViewReport:
    missing = set(VIEW_AXES) - set(reference_sources)
    if missing:
        raise ValueError(f"missing three-view references: {sorted(missing)}")
    generated = render_mesh_three_views(mesh, size=max(size, 256), yaw=yaw, pitch=pitch)
    reports: dict[str, ImageMatchReport] = {}
    for view in VIEW_AXES:
        reports[view] = compare_images(
            generated[view],
            reference_sources[view],
            left_name=generated_names.get(view, f"generated:{view}"),
            right_name=reference_names.get(view, f"reference:{view}"),
            method=method,
            profile=profile,
            preprocess=preprocess,
            size=size,
        )
    aggregate = int(round(sum(report.composite_bp for report in reports.values()) / 3.0))
    return ThreeViewReport(
        mesh=mesh_name,
        orientation=orientation,
        yaw_radians=float(yaw),
        pitch_radians=float(pitch),
        method=method,
        profile=profile,
        generated_views=dict(generated_names),
        reference_views=dict(reference_names),
        reports=reports,
        aggregate_bp=aggregate,
    )


def classify_images_to_three_views(
    mesh: MeshData,
    candidates: Mapping[str, Path | Any],
    *,
    mesh_name: str,
    orientation: str = "world",
    yaw: float = 0.0,
    pitch: float = 0.0,
    method: str = "all",
    profile: str = "shape",
    preprocess: str = "edge-fit",
    size: int = DEFAULT_COMPARE_SIZE,
) -> ViewClassificationReport:
    if not candidates:
        raise ValueError("at least one candidate image is required")
    if len(candidates) > MAX_CLASSIFY_IMAGES:
        raise ValueError(f"view classification accepts at most {MAX_CLASSIFY_IMAGES} images")
    generated = render_mesh_three_views(mesh, size=max(size, 256), yaw=yaw, pitch=pitch)
    scores: dict[str, dict[str, int]] = {}
    for reference, source in sorted(candidates.items()):
        scores[reference] = {}
        for view, generated_image in generated.items():
            report = compare_images(
                generated_image,
                source,
                left_name=f"generated:{view}",
                right_name=reference,
                method=method,
                profile=profile,
                preprocess=preprocess,
                size=size,
            )
            scores[reference][view] = report.composite_bp

    references = list(sorted(candidates))
    views = tuple(VIEW_AXES)
    best_score = -1
    best_assignment: dict[str, str] = {}
    if len(references) >= 3:
        for chosen in itertools.permutations(references, 3):
            total = sum(scores[reference][view] for view, reference in zip(views, chosen))
            candidate_assignment = {view: reference for view, reference in zip(views, chosen)}
            signature = tuple(candidate_assignment[view] for view in views)
            best_signature = tuple(best_assignment.get(view, "") for view in views)
            if total > best_score or (total == best_score and signature < best_signature):
                best_score = total
                best_assignment = candidate_assignment
        divisor = 3
    else:
        for chosen_views in itertools.permutations(views, len(references)):
            total = sum(scores[reference][view] for reference, view in zip(references, chosen_views))
            candidate_assignment = {view: reference for reference, view in zip(references, chosen_views)}
            signature = tuple(sorted(candidate_assignment.items()))
            best_signature = tuple(sorted(best_assignment.items()))
            if total > best_score or (total == best_score and signature < best_signature):
                best_score = total
                best_assignment = candidate_assignment
        divisor = len(references)
    aggregate = int(round(best_score / max(1, divisor))) if best_score >= 0 else 0
    assigned_references = set(best_assignment.values())
    unassigned = tuple(reference for reference in references if reference not in assigned_references)
    return ViewClassificationReport(
        mesh=mesh_name,
        orientation=orientation,
        method=method,
        profile=profile,
        scores=scores,
        assignment=best_assignment,
        aggregate_bp=aggregate,
        unassigned=unassigned,
    )


def report_json(report: Any) -> bytes:
    if hasattr(report, "to_dict"):
        payload = report.to_dict()
    elif hasattr(report, "__dataclass_fields__"):
        payload = asdict(report)
    else:
        payload = report
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
