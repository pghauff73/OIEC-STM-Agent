#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.persistence import atomic_write_text


FIXTURE_ID = "ICPI-PAGE-REFERENCE-v1"
FIXED_GENERATED_AT = "2026-08-31T00:00:00Z"
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
DEFAULT_OUTPUT = ROOT / "benchmarks" / "icpi" / "page-reference-v1"


@dataclass(frozen=True)
class PageExpectation:
    source_id: str
    physical_page: int
    printed_page_label: str
    marker: str
    claim: str
    concept: str
    reasoning: str
    limitation: str
    accepted_paraphrase_concepts: tuple[str, ...]
    raster_only: bool = False

    @property
    def literal_text(self) -> str:
        return "\n".join(
            (
                self.marker,
                f"CLAIM: {self.claim}",
                f"CONCEPT: {self.concept}",
                f"REASONING: {self.reasoning}",
                f"LIMITATION: {self.limitation}",
                f"PRINTED PAGE: {self.printed_page_label}",
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "physical_page": self.physical_page,
            "printed_page_label": self.printed_page_label,
            "marker": self.marker,
            "literal_text": self.literal_text,
            "claim": self.claim,
            "concept": self.concept,
            "reasoning": self.reasoning,
            "limitation": self.limitation,
            "accepted_paraphrase_concepts": list(self.accepted_paraphrase_concepts),
            "raster_only": self.raster_only,
        }


def _expectations() -> tuple[PageExpectation, ...]:
    source_a = (
        (
            "A-01",
            "Evidence claims require an observable source anchor.",
            "source anchoring",
            "An anchor permits a reader to recover the supporting passage independently.",
            "An anchor proves location, not the truth of the claim.",
            ("traceable evidence", "recoverable source location"),
        ),
        (
            "A-02",
            "A paraphrase must preserve the source qualification.",
            "qualified paraphrase",
            "Removing a qualifier changes the proposition and overstates the evidence.",
            "Equivalent wording may still be disputed by a domain reviewer.",
            ("qualification preservation", "semantic fidelity"),
        ),
        (
            "A-03",
            "Page labels and physical page indices are distinct identifiers.",
            "page identity",
            "Front matter and custom numbering can separate printed labels from file order.",
            "Some documents omit printed labels entirely.",
            ("printed versus physical pages", "page-label distinction"),
        ),
        (
            "A-04",
            "Reference confidence must fall when extraction is incomplete.",
            "bounded confidence",
            "Incomplete text prevents a complete comparison between the draft and source.",
            "Lower confidence does not identify which missing sentence matters.",
            ("uncertainty disclosure", "incomplete extraction"),
        ),
    )
    source_b = (
        (
            "B-01",
            "A concept label summarizes the role of a passage.",
            "concept identification",
            "The label groups the passage by function rather than copying its wording.",
            "A passage can legitimately support more than one concept.",
            ("passage function", "concept classification"),
        ),
        (
            "B-02",
            "Reasoning links evidence to a conclusion through explicit warrants.",
            "argument warrant",
            "Making the warrant explicit exposes assumptions that can be reviewed.",
            "Not every warrant is stated by the source author.",
            ("evidence-to-claim link", "explicit warrant"),
        ),
        (
            "B-03",
            "Quotation and paraphrase require separate provenance records.",
            "reference mode",
            "A quotation preserves exact words while a paraphrase records a semantic transformation.",
            "Both modes can still misrepresent surrounding context.",
            ("quotation versus paraphrase", "transformation provenance"),
        ),
        (
            "B-04",
            "Conflicting sources should remain visible in a formal report.",
            "source disagreement",
            "Visible disagreement prevents a synthesized conclusion from appearing unanimous.",
            "The presence of disagreement does not decide which source is stronger.",
            ("conflict disclosure", "balanced synthesis"),
        ),
        (
            "B-05",
            "A reference audit must bind findings to the current source bytes.",
            "hash-bound audit",
            "Content hashes reveal whether cited material changed after analysis.",
            "A hash cannot establish authorship or publication quality.",
            ("source hash binding", "current snapshot evidence"),
        ),
    )
    scanned = (
        (
            "S-01",
            "Raster pages require OCR before text-level reference checks.",
            "OCR dependency",
            "A raster image has pixels but no native character sequence for passage matching.",
            "OCR can confuse characters and page layout.",
            ("raster text extraction", "OCR requirement"),
        ),
        (
            "S-02",
            "OCR-derived quotations require lower confidence than native text.",
            "OCR uncertainty",
            "Recognition errors can alter exact wording even when the visible page is unchanged.",
            "Manual review may still be required for critical quotations.",
            ("recognition confidence", "manual quotation review"),
        ),
    )
    pages: list[PageExpectation] = []
    for index, values in enumerate(source_a, 1):
        pages.append(PageExpectation("source-a", index, f"A-{index}", *values))
    for index, values in enumerate(source_b, 1):
        pages.append(PageExpectation("source-b", index, str(10 + index), *values))
    for index, values in enumerate(scanned, 1):
        pages.append(
            PageExpectation(
                "scanned",
                index,
                f"SCAN-{index}",
                *values,
                raster_only=True,
            )
        )
    return tuple(pages)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(objects: Sequence[bytes]) -> bytes:
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    chunks = [header]
    offsets = [0]
    cursor = len(header)
    for object_id, body in enumerate(objects, 1):
        chunk = f"{object_id} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        offsets.append(cursor)
        chunks.append(chunk)
        cursor += len(chunk)
    xref_offset = cursor
    xref = [f"xref\n0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:])
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return b"".join([*chunks, *xref, trailer])


def build_text_pdf(pages: Sequence[PageExpectation]) -> bytes:
    objects: list[bytes] = [b"", b""]
    font_id = len(objects) + 1
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for page in pages:
        lines = page.literal_text.splitlines()
        commands = ["BT", "/F1 9 Tf", "72 720 Td", "14 TL"]
        for line_index, line in enumerate(lines):
            if line_index:
                commands.append("T*")
            commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        content_id = len(objects) + 1
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")
    return _pdf(objects)


def _load_font(size: int):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to build raster-only page fixtures") from exc
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size), candidate
    return ImageFont.load_default(), None


def render_scanned_page(page: PageExpectation) -> tuple[bytes, bytes, str]:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to build raster-only page fixtures") from exc
    font, font_path = _load_font(20)
    image = Image.new("L", (PAGE_WIDTH, PAGE_HEIGHT), color=255)
    draw = ImageDraw.Draw(image)
    y = 72
    for line in page.literal_text.splitlines():
        words = line.split()
        current = ""
        wrapped: list[str] = []
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= PAGE_WIDTH - 120:
                current = candidate
            else:
                wrapped.append(current)
                current = word
        if current:
            wrapped.append(current)
        for wrapped_line in wrapped:
            draw.text((60, y), wrapped_line, fill=0, font=font)
            y += 28
        y += 10
    raw = image.tobytes()
    import io

    png = io.BytesIO()
    image.save(png, format="PNG", optimize=False, compress_level=9)
    font_hash = hashlib.sha256(font_path.read_bytes()).hexdigest() if font_path else "builtin"
    return raw, png.getvalue(), font_hash


def build_scanned_pdf(rendered_pages: Sequence[bytes]) -> bytes:
    objects: list[bytes] = [b"", b""]
    page_ids: list[int] = []
    for index, raw in enumerate(rendered_pages, 1):
        compressed = zlib.compress(raw, level=9)
        image_id = len(objects) + 1
        objects.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {PAGE_WIDTH} /Height {PAGE_HEIGHT} "
                f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(compressed)} >>\nstream\n"
            ).encode("ascii")
            + compressed
            + b"\nendstream"
        )
        content = f"q\n{PAGE_WIDTH} 0 0 {PAGE_HEIGHT} 0 0 cm\n/Im{index} Do\nQ".encode("ascii")
        content_id = len(objects) + 1
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /XObject << /Im{index} {image_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")
    return _pdf(objects)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_fixture(output_root: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    expectations = _expectations()
    grouped = {
        source_id: tuple(page for page in expectations if page.source_id == source_id)
        for source_id in ("source-a", "source-b", "scanned")
    }
    files: dict[str, bytes] = {
        "source-a.pdf": build_text_pdf(grouped["source-a"]),
        "source-b.pdf": build_text_pdf(grouped["source-b"]),
    }
    scanned_raw: list[bytes] = []
    font_hashes: set[str] = set()
    for page in grouped["scanned"]:
        raw, png, font_hash = render_scanned_page(page)
        scanned_raw.append(raw)
        font_hashes.add(font_hash)
        files[f"page-images/scanned-page-{page.physical_page}.png"] = png
    files["scanned.pdf"] = build_scanned_pdf(scanned_raw)
    expected_payload = {
        "schema_version": 1,
        "fixture_id": FIXTURE_ID,
        "pages": [page.to_dict() for page in expectations],
    }
    files["expected-pages.json"] = (
        json.dumps(expected_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    readme = (
        "# ICPI Page Reference Fixture v1\n\n"
        "Deterministic page-accuracy corpus generated by "
        "`tools/icpi_page_reference_fixture.py`.\n\n"
        "- `source-a.pdf`: four native-text pages.\n"
        "- `source-b.pdf`: five native-text pages with printed labels 11-15.\n"
        "- `scanned.pdf`: two image-only pages with no PDF text operators.\n"
        "- `expected-pages.json`: exact text, concepts, reasoning, and limitations.\n"
        "- `manifest.json`: SHA-256 bindings and generation metadata.\n\n"
        "Regenerate with `python tools/icpi_page_reference_fixture.py`.\n"
    )
    files["README.md"] = readme.encode("utf-8")
    for relative_path, content in sorted(files.items()):
        atomic_write_bytes(output_root / relative_path, content)
    bindings = {
        relative_path: {
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
        }
        for relative_path, content in sorted(files.items())
    }
    manifest_unsigned = {
        "schema_version": 1,
        "fixture_id": FIXTURE_ID,
        "generated_at": FIXED_GENERATED_AT,
        "page_geometry": {"width": PAGE_WIDTH, "height": PAGE_HEIGHT},
        "page_counts": {"source-a": 4, "source-b": 5, "scanned": 2},
        "font_sha256": sorted(font_hashes),
        "files": bindings,
    }
    manifest = {
        **manifest_unsigned,
        "manifest_payload_sha256": sha256_bytes(
            canonical_json(manifest_unsigned).encode("utf-8")
        ),
    }
    atomic_write_text(
        output_root / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return manifest


def validate_fixture(output_root: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    output_root = output_root.expanduser().resolve()
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    for relative_path, binding in dict(manifest["files"]).items():
        content = (output_root / relative_path).read_bytes()
        if sha256_bytes(content) != binding["sha256"]:
            raise ValueError(f"fixture hash mismatch: {relative_path}")
        if len(content) != binding["size_bytes"]:
            raise ValueError(f"fixture size mismatch: {relative_path}")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_payload_sha256"}
    expected_manifest_hash = sha256_bytes(canonical_json(unsigned).encode("utf-8"))
    if manifest.get("manifest_payload_sha256") != expected_manifest_hash:
        raise ValueError("fixture manifest payload hash mismatch")
    expected = json.loads((output_root / "expected-pages.json").read_text(encoding="utf-8"))
    pages = list(expected.get("pages", []))
    observed_counts: dict[str, int] = {}
    for page in pages:
        source_id = str(page["source_id"])
        observed_counts[source_id] = observed_counts.get(source_id, 0) + 1
    if observed_counts != manifest["page_counts"]:
        raise ValueError(f"fixture page counts mismatch: {observed_counts!r}")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic ICPI page-reference fixtures.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = validate_fixture(args.output) if args.validate_only else build_fixture(args.output)
    if not args.validate_only:
        validate_fixture(args.output)
    print(
        json.dumps(
            {
                "fixture_id": manifest["fixture_id"],
                "output": str(args.output.resolve()),
                "page_counts": manifest["page_counts"],
                "manifest_payload_sha256": manifest["manifest_payload_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_OUTPUT",
    "FIXTURE_ID",
    "PageExpectation",
    "build_fixture",
    "build_scanned_pdf",
    "build_text_pdf",
    "main",
    "render_scanned_page",
    "validate_fixture",
]
