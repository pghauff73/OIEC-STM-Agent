from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ..workspace import Workspace
from .models import ExtractedSource, SourceDocument
from .pdf import extract_pdf
from .signatures import content_sha256


INGESTION_ADAPTER_VERSION = "1.0.0"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.parts)


def _paragraph_offsets(text: str) -> tuple[tuple[int, int], ...]:
    offsets: list[tuple[int, int]] = []
    paragraph_start: int | None = None
    cursor = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if paragraph_start is None:
                paragraph_start = cursor
        elif paragraph_start is not None:
            end = cursor
            while end > paragraph_start and text[end - 1].isspace():
                end -= 1
            offsets.append((paragraph_start, end))
            paragraph_start = None
        cursor += len(line)
    if paragraph_start is not None:
        end = len(text)
        while end > paragraph_start and text[end - 1].isspace():
            end -= 1
        offsets.append((paragraph_start, end))
    return tuple(offsets)


def _markdown_sections(text: str) -> tuple[tuple[str, int], ...]:
    return tuple(
        (match.group(2).strip(), match.start())
        for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, flags=re.MULTILINE)
    )


def _metadata_from_text(path: Path, text: str) -> dict[str, Any]:
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    heading = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if heading:
        title = heading.group(1).strip()
    return {"title": title, "authors": (), "language": "und"}


def ingest_source(
    workspace: Workspace,
    path: str,
    *,
    allow_ocr: bool = False,
    ocr_language: str = "eng",
    license_or_access_note: str = "",
) -> ExtractedSource:
    canonical = workspace.canonical(path)
    resolved = workspace.resolve(canonical)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(canonical)
    raw = resolved.read_bytes()
    digest = content_sha256(raw)
    suffix = resolved.suffix.casefold()
    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    extraction_created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    pages = ()
    page_label_map = ()
    metadata: dict[str, Any]
    ocr_status = "not_requested"
    ocr_engine = ""
    ocr_engine_version = ""
    if suffix == ".pdf":
        (
            pages,
            page_label_map,
            pdf_metadata,
            ocr_status,
            ocr_engine,
            ocr_engine_version,
        ) = extract_pdf(resolved, allow_ocr=allow_ocr, ocr_language=ocr_language)
        document_text = "\n\f\n".join(page.text for page in pages)
        metadata = {
            "title": str(pdf_metadata.get("title") or resolved.stem),
            "authors": tuple(
                part.strip()
                for part in re.split(r"[;,]", str(pdf_metadata.get("author") or ""))
                if part.strip()
            ),
            "issued_date": str(pdf_metadata.get("creationDate") or ""),
            "publisher": str(pdf_metadata.get("producer") or ""),
            "language": "und",
        }
        adapter = "pymupdf"
    elif suffix in {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}:
        document_text = raw.decode("utf-8", errors="strict")
        metadata = _metadata_from_text(resolved, document_text)
        adapter = "utf8-text"
    elif suffix in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(raw.decode("utf-8", errors="replace"))
        document_text = parser.text()
        metadata = _metadata_from_text(resolved, document_text)
        adapter = "html.parser"
    else:
        raise ValueError(f"unsupported formal-writing source format: {suffix or '(none)'}")
    document = SourceDocument(
        source_uri_or_path=canonical,
        workspace_relative_path=canonical,
        media_type=media_type,
        content_sha256=digest,
        byte_size=len(raw),
        title=str(metadata.get("title", "")),
        authors=tuple(metadata.get("authors", ())),
        issued_date=str(metadata.get("issued_date", "")),
        publisher=str(metadata.get("publisher", "")),
        language=str(metadata.get("language", "und")),
        page_count=len(pages),
        page_label_map=page_label_map,
        ingestion_adapter=adapter,
        ingestion_adapter_version=INGESTION_ADAPTER_VERSION,
        extraction_created_at=extraction_created_at,
        ocr_status=ocr_status,
        ocr_engine=ocr_engine,
        ocr_engine_version=ocr_engine_version,
        license_or_access_note=license_or_access_note,
        metadata_provenance=(
            ("title", adapter),
            ("authors", adapter),
            ("content_sha256", "workspace bytes"),
        ),
    )
    return ExtractedSource(
        document=document,
        document_text=document_text,
        pages=pages,
        section_offsets=_markdown_sections(document_text) if suffix in {".md", ".markdown"} else (),
        paragraph_offsets=_paragraph_offsets(document_text),
    )


__all__ = ["INGESTION_ADAPTER_VERSION", "ingest_source"]
