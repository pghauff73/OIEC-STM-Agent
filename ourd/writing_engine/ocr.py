from __future__ import annotations

from typing import Any


class OCRUnavailableError(RuntimeError):
    pass


def ocr_pdf_page(page: Any, *, language: str = "eng", dpi: int = 300) -> tuple[str, str, str]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise OCRUnavailableError(
            "OCR requires the optional Pillow and pytesseract dependencies"
        ) from exc
    pixmap = page.get_pixmap(dpi=max(72, int(dpi)), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    text = pytesseract.image_to_string(image, lang=language)
    version = str(pytesseract.get_tesseract_version())
    return text, "tesseract", version


__all__ = ["OCRUnavailableError", "ocr_pdf_page"]
