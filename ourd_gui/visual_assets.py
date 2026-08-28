from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


IMAGE_REFERENCE_RE = re.compile(r"@img:([0-9a-f]{12,64})\b", re.IGNORECASE)
MESH_REFERENCE_RE = re.compile(r"@mesh:([0-9a-f]{12,64})\b", re.IGNORECASE)
CURVE_REFERENCE_RE = re.compile(r"@curve:([0-9a-f]{12,64})\b", re.IGNORECASE)
MATCH_REFERENCE_RE = re.compile(r"@match:([0-9a-f]{12,64})\b", re.IGNORECASE)

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SUPPORTED_MESH_SUFFIXES = {".obj", ".stl"}
MAX_ASSET_BYTES = 64 * 1024 * 1024


def _reference_prefix(kind: str) -> str:
    return {
        "image": "img",
        "mesh": "mesh",
        "curve": "curve",
        "report": "match",
    }.get(kind, "asset")


@dataclass(frozen=True)
class VisualAsset:
    reference: str
    kind: str
    sha256: str
    filename: str
    media_type: str
    size: int
    stored_path: str
    source_path: str = ""


class VisualAssetRegistry:
    """Content-addressed GUI asset registry under the protected state directory.

    User-selected visual files are copied into .ourd-agent/gui-assets. The
    registry is GUI bookkeeping rather than model mutation authority. Models see
    only explicit references selected by the user.
    """

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.root = self.repository_root / ".ourd-agent" / "gui-assets"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self._assets: dict[str, VisualAsset] = {}
        self._load()

    def _load(self) -> None:
        if not self.index_path.is_file():
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for reference, value in payload.items():
            if not isinstance(value, dict):
                continue
            try:
                asset = VisualAsset(**value)
            except TypeError:
                continue
            if asset.reference == reference:
                self._assets[reference] = asset

    def _save(self) -> None:
        payload = {
            reference: asdict(asset)
            for reference, asset in sorted(self._assets.items())
        }
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.index_path)

    @staticmethod
    def _digest_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_ASSET_BYTES:
                    raise ValueError(
                        f"visual asset exceeds bounded size limit ({MAX_ASSET_BYTES} bytes)"
                    )
                digest.update(block)
        return digest.hexdigest(), size

    def register_file(self, path: Path, *, kind: str | None = None) -> VisualAsset:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        suffix = source.suffix.casefold()
        inferred_kind = kind or (
            "image"
            if suffix in SUPPORTED_IMAGE_SUFFIXES
            else "mesh"
            if suffix in SUPPORTED_MESH_SUFFIXES
            else "file"
        )
        if inferred_kind == "image" and suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"unsupported image type: {suffix or '(none)'}")
        if inferred_kind == "mesh" and suffix not in SUPPORTED_MESH_SUFFIXES:
            raise ValueError(f"unsupported mesh type: {suffix or '(none)'}")
        digest, size = self._digest_file(source)
        reference = f"@{_reference_prefix(inferred_kind)}:{digest[:16]}"
        destination = self.root / f"{digest}{suffix}"
        if not destination.exists():
            shutil.copyfile(source, destination)
        media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        asset = VisualAsset(
            reference=reference,
            kind=inferred_kind,
            sha256=digest,
            filename=source.name,
            media_type=media_type,
            size=size,
            stored_path=destination.relative_to(self.repository_root).as_posix(),
            source_path=str(source),
        )
        self._assets[reference] = asset
        self._save()
        return asset

    def register_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        kind: str,
        media_type: str = "application/octet-stream",
    ) -> VisualAsset:
        if len(content) > MAX_ASSET_BYTES:
            raise ValueError("visual asset exceeds bounded size limit")
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(filename).suffix.casefold()
        reference = f"@{_reference_prefix(kind)}:{digest[:16]}"
        destination = self.root / f"{digest}{suffix}"
        if not destination.exists():
            destination.write_bytes(content)
        asset = VisualAsset(
            reference=reference,
            kind=kind,
            sha256=digest,
            filename=filename,
            media_type=media_type,
            size=len(content),
            stored_path=destination.relative_to(self.repository_root).as_posix(),
        )
        self._assets[reference] = asset
        self._save()
        return asset

    def list(self, kind: str = "") -> tuple[VisualAsset, ...]:
        assets = [asset for asset in self._assets.values() if not kind or asset.kind == kind]
        return tuple(sorted(assets, key=lambda asset: (asset.kind, asset.filename, asset.reference)))

    def get(self, reference: str) -> VisualAsset:
        normalized = reference.strip()
        asset = self._assets.get(normalized)
        if asset is None:
            raise KeyError(f"unknown visual reference: {reference}")
        path = self.repository_root / asset.stored_path
        if not path.is_file():
            raise FileNotFoundError(path)
        return asset

    def path_for(self, reference: str) -> Path:
        asset = self.get(reference)
        return (self.repository_root / asset.stored_path).resolve()

    def image_references_in(self, text: str) -> tuple[str, ...]:
        references = []
        for digest in IMAGE_REFERENCE_RE.findall(text):
            prefix = f"@img:{digest.lower()}"
            matches = [reference for reference in self._assets if reference.lower().startswith(prefix)]
            if len(matches) == 1 and matches[0] not in references:
                references.append(matches[0])
        return tuple(references)

    def describe_references(self, text: str) -> tuple[str, ...]:
        descriptions: list[str] = []
        for reference, asset in sorted(self._assets.items()):
            if reference in text:
                descriptions.append(
                    f"{reference}: kind={asset.kind}, filename={asset.filename}, "
                    f"sha256={asset.sha256}, bytes={asset.size}"
                )
        return tuple(descriptions)

    def multimodal_user_item(self, text: str) -> dict:
        """Build a Responses-compatible current user item for explicit image refs."""

        image_refs = self.image_references_in(text)
        descriptions = self.describe_references(text)
        if not image_refs:
            enriched = text
            if descriptions:
                enriched += "\n\nVISUAL REFERENCES\n" + "\n".join(descriptions)
            return {"role": "user", "content": enriched}

        content: list[dict[str, str]] = []
        enriched_text = text
        if descriptions:
            enriched_text += "\n\nVISUAL REFERENCES\n" + "\n".join(descriptions)
        content.append({"type": "input_text", "text": enriched_text})
        for reference in image_refs:
            asset = self.get(reference)
            path = self.path_for(reference)
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            media_type = asset.media_type
            if not media_type.startswith("image/"):
                media_type = mimetypes.guess_type(asset.filename)[0] or "image/png"
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{encoded}",
                }
            )
        return {"role": "user", "content": content}

    def references(self) -> Sequence[str]:
        return tuple(sorted(self._assets))
