from __future__ import annotations

import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tools import build_docs_site
from tools.docs_concept_catalog import discover_concepts


class DocumentationSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"
        cls.documents = build_docs_site.discover_documents()
        cls.concepts = discover_concepts()
        cls.manifest = json.loads(
            (cls.docs_root / "site-manifest.json").read_text(encoding="utf-8")
        )

    def test_every_markdown_document_has_html_and_svg(self) -> None:
        self.assertTrue(self.documents)
        for document in self.documents:
            with self.subTest(document=document.relative_path.as_posix()):
                self.assertTrue(document.output_path.is_file())
                figure_path = (
                    self.docs_root
                    / "figures"
                    / document.relative_path.with_suffix(".svg")
                )
                self.assertTrue(figure_path.is_file())
                ET.parse(figure_path)

    def test_every_heading_has_five_five_paragraph_blocks(self) -> None:
        for document in self.documents:
            page = document.output_path.read_text(encoding="utf-8")
            blocks = re.findall(
                r'<section class="essay-block [^"]+"[^>]*>(.*?)</section>',
                page,
                flags=re.DOTALL,
            )
            with self.subTest(document=document.relative_path.as_posix()):
                self.assertEqual(len(blocks), len(document.sections) * 5)
                for block in blocks:
                    paragraphs = re.findall(
                        r'<p data-essay-paragraph="[1-5]">', block
                    )
                    self.assertEqual(len(paragraphs), 5)

    def test_manifest_binds_each_source_hash_and_heading(self) -> None:
        by_source = {
            item["source"]: item for item in self.manifest["documents"]
        }
        self.assertEqual(len(by_source), len(self.documents))
        for document in self.documents:
            source_key = document.relative_path.as_posix()
            with self.subTest(document=source_key):
                item = by_source[source_key]
                self.assertEqual(
                    item["source_sha256"],
                    hashlib.sha256(document.source_path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    [heading["slug"] for heading in item["headings"]],
                    [section.slug for section in document.sections],
                )

    def test_javascript_declares_interactive_svg_and_pixel_crew(self) -> None:
        javascript = (self.docs_root / "assets" / "site.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("setupSectionDiagrams", javascript)
        self.assertIn("activateDocumentMap", javascript)
        self.assertIn("setupGovernedLoop", javascript)
        self.assertIn("setupConceptMaps", javascript)
        self.assertIn("setupConceptAtlas", javascript)
        self.assertIn('"mousemove"', javascript)
        self.assertIn("thought-bubble", javascript)

    def test_every_discovered_concept_has_essay_and_svg(self) -> None:
        self.assertGreaterEqual(len(self.concepts), 100)
        for concept in self.concepts:
            with self.subTest(concept=concept.slug):
                page_path = self.docs_root / "concepts" / f"{concept.slug}.html"
                figure_path = self.docs_root / "figures" / "concepts" / f"{concept.slug}.svg"
                self.assertTrue(page_path.is_file())
                self.assertTrue(figure_path.is_file())
                ET.parse(figure_path)
                page = page_path.read_text(encoding="utf-8")
                blocks = re.findall(
                    r'<section class="essay-block [^"]+"[^>]*>(.*?)</section>',
                    page,
                    flags=re.DOTALL,
                )
                self.assertEqual(len(blocks), 5)
                for block in blocks:
                    self.assertEqual(len(re.findall(r'data-concept-paragraph="[1-5]"', block)), 5)

    def test_manifest_binds_concept_sources_and_governed_loop(self) -> None:
        by_slug = {item["slug"]: item for item in self.manifest["concepts"]}
        self.assertEqual(len(by_slug), len(self.concepts))
        for concept in self.concepts:
            with self.subTest(concept=concept.slug):
                item = by_slug[concept.slug]
                self.assertEqual(item["title"], concept.title)
                for source in item["sources"]:
                    source_path = Path(__file__).resolve().parents[1] / source["path"]
                    self.assertEqual(source["sha256"], hashlib.sha256(source_path.read_bytes()).hexdigest())
        self.assertEqual(
            self.manifest["governed_loop"]["pipeline"],
            ["HRTv1", "OURD", "IURMv1.1.1", "EONv1", "Evidence Gate", "Action", "CFEL"],
        )
        ET.parse(self.docs_root / "figures" / "governed-loop.svg")
        ET.parse(self.docs_root / "figures" / "concept-atlas.svg")

    def test_index_contains_governed_loop_hero_and_concept_atlas(self) -> None:
        page = (self.docs_root / "index.html").read_text(encoding="utf-8")
        for term in ("OURD", "IURM", "EON", "CFEL", "governed-loop.svg", "concepts/index.html"):
            self.assertIn(term, page)
        atlas = (self.docs_root / "concepts" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"{len(self.concepts)} source-derived concepts", atlas)
        self.assertNotIn("125 source-derived concepts", atlas)


if __name__ == "__main__":
    unittest.main()
