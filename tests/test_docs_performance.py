from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from tools import build_docs_site


class DocumentationPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"

    def test_homepage_payload_and_dom_budgets(self) -> None:
        path = self.docs_root / "index.html"
        page = path.read_text(encoding="utf-8")
        self.assertLessEqual(path.stat().st_size, 350 * 1024)
        self.assertLessEqual(len(re.findall(r"<[A-Za-z][^>]*>", page)), 1500)
        self.assertNotIn("window.RELATIONAL_OBJECTS", page)
        self.assertNotIn('class="relational-row', page)
        self.assertLessEqual(page.count("<object"), 4)

    def test_repeated_generation_is_byte_identical(self) -> None:
        def tree_hash() -> str:
            digest = hashlib.sha256()
            for path in sorted(self.docs_root.rglob("*")):
                if path.is_file() and path.suffix in {".html", ".svg", ".json"}:
                    digest.update(path.relative_to(self.docs_root).as_posix().encode())
                    digest.update(path.read_bytes())
            return digest.hexdigest()

        build_docs_site.build("2026-08-30")
        first = tree_hash()
        build_docs_site.build("2026-08-30")
        self.assertEqual(tree_hash(), first)


if __name__ == "__main__":
    unittest.main()
