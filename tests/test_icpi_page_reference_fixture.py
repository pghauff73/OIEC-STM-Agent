from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ourd.writing_engine.pdf import PDFCapabilityError, extract_pdf
from tools.icpi_page_reference_fixture import build_fixture, validate_fixture


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class IcpiPageReferenceFixtureTests(unittest.TestCase):
    def test_fixture_generation_is_byte_identical_and_hash_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            first = build_fixture(root)
            first_hashes = tree_hashes(root)
            second = build_fixture(root)
            second_hashes = tree_hashes(root)
            self.assertEqual(first, second)
            self.assertEqual(first_hashes, second_hashes)
            self.assertEqual(first, validate_fixture(root))

    def test_fixture_has_exact_page_contract_and_raster_only_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            manifest = build_fixture(root)
            self.assertEqual(
                {"source-a": 4, "source-b": 5, "scanned": 2},
                manifest["page_counts"],
            )
            expected = json.loads((root / "expected-pages.json").read_text(encoding="utf-8"))
            self.assertEqual(11, len(expected["pages"]))
            self.assertEqual(2, sum(bool(page["raster_only"]) for page in expected["pages"]))
            self.assertIn(b"BT", (root / "source-a.pdf").read_bytes())
            self.assertNotIn(b"BT", (root / "scanned.pdf").read_bytes())
            self.assertNotIn(b"S-01", (root / "scanned.pdf").read_bytes())

    def test_real_pdf_and_ocr_adapters_preserve_page_contract(self) -> None:
        if importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
            self.skipTest("PyMuPDF is unavailable")
        if importlib.util.find_spec("pytesseract") is None or shutil.which("tesseract") is None:
            self.skipTest("pytesseract or tesseract is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            build_fixture(root)
            expected = json.loads((root / "expected-pages.json").read_text(encoding="utf-8"))
            expected_by_source = {
                source_id: [
                    page for page in expected["pages"] if page["source_id"] == source_id
                ]
                for source_id in ("source-a", "source-b", "scanned")
            }
            for source_id, expected_count in (("source-a", 4), ("source-b", 5)):
                pages, labels, _, ocr_status, _, _ = extract_pdf(root / f"{source_id}.pdf")
                self.assertEqual(expected_count, len(pages))
                self.assertEqual("not_required", ocr_status)
                self.assertEqual(
                    tuple((index, str(index + 1)) for index in range(expected_count)),
                    labels,
                )
                for page, page_expectation in zip(pages, expected_by_source[source_id]):
                    self.assertEqual("native", page.text_layer_kind)
                    self.assertIn(page_expectation["claim"], page.text)
                    self.assertIn(page_expectation["concept"], page.text)
                    self.assertIn(page_expectation["reasoning"], page.text)
            with self.assertRaisesRegex(PDFCapabilityError, "explicit OCR permission"):
                extract_pdf(root / "scanned.pdf")
            pages, labels, _, ocr_status, ocr_engine, ocr_version = extract_pdf(
                root / "scanned.pdf",
                allow_ocr=True,
            )
            self.assertEqual(2, len(pages))
            self.assertEqual(((0, "1"), (1, "2")), labels)
            self.assertEqual("performed", ocr_status)
            self.assertEqual("tesseract", ocr_engine)
            self.assertTrue(ocr_version)
            self.assertTrue(all(page.text_layer_kind == "ocr" for page in pages))
            self.assertIn("S-01", pages[0].text)
            self.assertIn("OCR dependency", pages[0].text)
            self.assertIn("S-02", pages[1].text)
            self.assertIn("OCR uncertainty", pages[1].text)


if __name__ == "__main__":
    unittest.main()
