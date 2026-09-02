from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

from .models import PageRecord, TextBlock, TextLine, TextWord
from .ocr import ocr_pdf_page
from .page_labels import normalize_page_labels
from .signatures import content_sha256


class PDFCapabilityError(RuntimeError):
    pass


MAX_PDF_PAGES = 2_000
MAX_OCR_PAGES = 200
MAX_OCR_SECONDS = 300.0


def _fitz() -> Any:
    try:
        import pymupdf  # type: ignore

        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore

            return fitz
        except ImportError as exc:
            raise PDFCapabilityError(
                "PDF extraction requires the optional PyMuPDF dependency"
            ) from exc


def extract_pdf(
    path: Path,
    *,
    allow_ocr: bool = False,
    ocr_language: str = "eng",
) -> tuple[tuple[PageRecord, ...], tuple[tuple[int, str], ...], dict[str, Any], str, str, str]:
    fitz = _fitz()
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFCapabilityError(f"PDF could not be opened: {exc}") from exc
    if getattr(document, "needs_pass", False):
        document.close()
        raise PDFCapabilityError("encrypted PDF requires a password and was rejected")
    if document.page_count > MAX_PDF_PAGES:
        page_count = document.page_count
        document.close()
        raise PDFCapabilityError(
            f"PDF page count exceeds the {MAX_PDF_PAGES}-page extraction limit: {page_count}"
        )
    metadata = dict(document.metadata or {})
    labels = []
    pages: list[PageRecord] = []
    ocr_status = "not_required"
    ocr_engine = ""
    ocr_engine_version = ""
    ocr_page_count = 0
    ocr_started = monotonic()
    source_id = f"source:{content_sha256(path.read_bytes())}"
    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        labels.append(str(page.get_label() or page_index + 1))
        raw_blocks = page.get_text("blocks")
        raw_words = page.get_text("words")
        native_text = page.get_text("text") or ""
        text_layer_kind = "native"
        confidence = 10_000
        page_text = native_text
        if len(native_text.strip()) < 8:
            if not allow_ocr:
                document.close()
                raise PDFCapabilityError(
                    f"page {page_index + 1} has no usable text layer; retry with explicit OCR permission"
                )
            ocr_page_count += 1
            if ocr_page_count > MAX_OCR_PAGES:
                document.close()
                raise PDFCapabilityError(
                    f"OCR page count exceeds the {MAX_OCR_PAGES}-page limit"
                )
            if monotonic() - ocr_started > MAX_OCR_SECONDS:
                document.close()
                raise PDFCapabilityError(
                    f"OCR processing exceeded the {MAX_OCR_SECONDS:.0f}-second time budget"
                )
            page_text, ocr_engine, ocr_engine_version = ocr_pdf_page(
                page,
                language=ocr_language,
            )
            ocr_status = "performed"
            text_layer_kind = "ocr"
            confidence = 7_000
            raw_blocks = ()
            raw_words = ()
        blocks = tuple(
            TextBlock(
                index=index,
                text=str(block[4]).strip(),
                bbox=tuple(float(value) for value in block[:4]),
            )
            for index, block in enumerate(raw_blocks)
            if len(block) >= 5 and str(block[4]).strip()
        )
        line_texts = page_text.splitlines()
        lines = tuple(
            TextLine(index=index, text=text)
            for index, text in enumerate(line_texts)
            if text.strip()
        )
        words = tuple(
            TextWord(
                index=index,
                text=str(word[4]),
                bbox=tuple(float(value) for value in word[:4]),
                block_index=int(word[5]) if len(word) > 5 else 0,
                line_index=int(word[6]) if len(word) > 6 else 0,
            )
            for index, word in enumerate(raw_words)
            if len(word) >= 5 and str(word[4]).strip()
        )
        pages.append(
            PageRecord(
                source_document_id=source_id,
                physical_page_index=page_index,
                physical_page_number=page_index + 1,
                display_page_label=labels[-1],
                width=float(page.rect.width),
                height=float(page.rect.height),
                coordinate_space="PDF points, top-left origin",
                rotation=int(page.rotation),
                text_layer_kind=text_layer_kind,
                extraction_confidence=confidence,
                page_text_sha256=content_sha256(page_text),
                text=page_text,
                blocks=blocks,
                lines=lines,
                words=words,
            )
        )
    page_label_map = normalize_page_labels(labels, document.page_count)
    document.close()
    return (
        tuple(pages),
        page_label_map,
        metadata,
        ocr_status,
        ocr_engine,
        ocr_engine_version,
    )


__all__ = [
    "MAX_OCR_PAGES",
    "MAX_OCR_SECONDS",
    "MAX_PDF_PAGES",
    "PDFCapabilityError",
    "extract_pdf",
]
