from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools import build_docs_site


class DocumentationAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"

    def test_generated_pages_declare_language_and_viewport(self) -> None:
        for path in sorted(self.docs_root.rglob("*.html")):
            page = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(self.docs_root).as_posix()):
                self.assertRegex(page, r'<html lang="en"')
                self.assertIn('name="viewport"', page)
                self.assertRegex(page, r"<title>[^<]+</title>")

    def test_objects_have_fallback_links_and_buttons_have_types(self) -> None:
        for path in sorted(self.docs_root.rglob("*.html")):
            page = path.read_text(encoding="utf-8")
            for object_markup in re.findall(r"<object\b.*?</object>", page, flags=re.DOTALL):
                self.assertIn("<a ", object_markup, path.as_posix())
            for opening in re.findall(r"<button\b[^>]*>", page):
                self.assertIn('type="button"', opening, path.as_posix())

    def test_learn_pages_preserve_no_javascript_fallback(self) -> None:
        pages = [self.docs_root / "tutorial" / "00_WELCOME.html", self.docs_root / "concepts" / "ourd.html"]
        for path in pages:
            page = path.read_text(encoding="utf-8")
            self.assertIn("JavaScript is optional", page)
            self.assertIn('data-view-content="learn"', page)
            self.assertIn('data-view-content="technical"', page)

    def test_every_page_binds_version_date_and_source_snapshot(self) -> None:
        expected_snapshot = build_docs_site.source_snapshot_digest()
        expected_version = build_docs_site.documentation_version()
        for path in sorted(self.docs_root.rglob("*.html")):
            page = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(self.docs_root).as_posix()):
                self.assertIn(f'data-docs-version="{expected_version}"', page)
                self.assertIn(
                    f'data-source-snapshot="sha256:{expected_snapshot}"', page
                )
                self.assertIn('data-build-date="2026-08-30"', page)

    def test_learning_styles_declare_motion_print_and_mobile_fallbacks(self) -> None:
        styles = (self.docs_root / "assets" / "styles.css").read_text(
            encoding="utf-8"
        )
        for contract in (
            "@keyframes careful-sequence",
            "@media (prefers-reduced-motion: no-preference)",
            "@media (prefers-reduced-motion: reduce)",
            "@media print",
            "@media (max-width: 980px)",
            "@media (max-width: 680px)",
        ):
            self.assertIn(contract, styles)


if __name__ == "__main__":
    unittest.main()
