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
        cls.relational_objects = build_docs_site.build_relational_objects(
            cls.documents,
            cls.concepts,
        )
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
        self.assertIn("setupRelationalObjectExplorer", javascript)
        self.assertIn("renderRelationalRelations", javascript)
        self.assertIn("setupRelationalSymbolInspector", javascript)
        self.assertIn("setupRelationalTopology", javascript)
        self.assertIn('"mousemove"', javascript)
        self.assertIn("thought-bubble", javascript)

    def test_relational_inventory_covers_every_tree_object(self) -> None:
        categories = {
            build_docs_site.category_for(document)
            for document in self.documents
        }
        folders = {
            document.relative_path.parts[0]
            for document in self.documents
            if len(document.relative_path.parts) > 1
        }
        heading_count = sum(len(document.sections) for document in self.documents)
        expected_count = (
            1
            + len(categories)
            + len(folders)
            + len(self.documents)
            + heading_count
            + len(self.concepts)
        )
        self.assertEqual(expected_count, 267)
        self.assertEqual(len(self.relational_objects), expected_count)
        build_docs_site.validate_relational_objects(self.relational_objects)
        kind_counts = self.manifest["relational_summary"]["kinds"]
        self.assertEqual(
            kind_counts,
            {
                "root": 1,
                "category": len(categories),
                "folder": len(folders),
                "document": len(self.documents),
                "heading": heading_count,
                "concept": len(self.concepts),
            },
        )

    def test_relational_ids_are_stable_under_input_reordering(self) -> None:
        reversed_objects = build_docs_site.build_relational_objects(
            tuple(reversed(self.documents)),
            tuple(reversed(self.concepts)),
        )
        current_ids = {
            (relational_object.kind, relational_object.source_key): relational_object.object_id
            for relational_object in self.relational_objects
        }
        reversed_ids = {
            (relational_object.kind, relational_object.source_key): relational_object.object_id
            for relational_object in reversed_objects
        }
        self.assertEqual(current_ids, reversed_ids)

    def test_every_relational_object_has_one_matching_svg_symbol(self) -> None:
        manifest_objects = {
            item["object_id"]: item
            for item in self.manifest["relational_objects"]
        }
        self.assertEqual(len(manifest_objects), len(self.relational_objects))
        for relational_object in self.relational_objects:
            with self.subTest(object_id=relational_object.object_id):
                item = manifest_objects[relational_object.object_id]
                self.assertEqual(item, build_docs_site.relational_record(relational_object))
                symbol_path = self.docs_root / item["symbol"]
                self.assertTrue(symbol_path.is_file())
                root = ET.parse(symbol_path).getroot()
                self.assertEqual(root.attrib["data-object-id"], relational_object.object_id)
                self.assertEqual(root.attrib["data-object-kind"], relational_object.kind)
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
                symbol_group = root.find(".//*[@id='object-symbol']")
                self.assertIsNotNone(symbol_group)

    def test_relational_relations_are_closed_and_canonical(self) -> None:
        object_ids = {
            relational_object.object_id
            for relational_object in self.relational_objects
        }
        canonical_relations = []
        for relation in self.manifest["relational_relations"]:
            self.assertIn(relation["source_id"], object_ids)
            self.assertIn(relation["target_id"], object_ids)
            if relation["canonical"]:
                canonical_relations.append(relation)
        self.assertEqual(len(canonical_relations), len(self.relational_objects) - 1)
        canonical_by_source = {
            relation["source_id"]: relation
            for relation in canonical_relations
        }
        for relational_object in self.relational_objects:
            if relational_object.kind == "root":
                self.assertNotIn(relational_object.object_id, canonical_by_source)
            else:
                self.assertEqual(
                    canonical_by_source[relational_object.object_id]["target_id"],
                    relational_object.parent_id,
                )
        summary = self.manifest["relational_summary"]
        self.assertEqual(summary["object_count"], len(self.relational_objects))
        self.assertEqual(summary["symbol_count"], len(self.relational_objects))
        self.assertEqual(summary["relation_count"], len(self.manifest["relational_relations"]))
        sprite_root = ET.parse(self.docs_root / summary["sprite_figure"]).getroot()
        sprite_ids = {
            symbol.attrib["id"]
            for symbol in sprite_root.findall("{http://www.w3.org/2000/svg}defs/{http://www.w3.org/2000/svg}symbol")
        }
        self.assertEqual(sprite_ids, object_ids)
        ET.parse(self.docs_root / summary["topology_figure"])

    def test_index_tree_references_every_relational_object(self) -> None:
        page = (self.docs_root / "index.html").read_text(encoding="utf-8")
        represented_ids = set(
            re.findall(r'data-relational-object="([^"]+)"', page)
        )
        expected_ids = {
            relational_object.object_id
            for relational_object in self.relational_objects
        }
        self.assertEqual(represented_ids, expected_ids)
        sprite_uses = set(
            re.findall(r'figures/relational-symbols\.svg#([^"<]+)', page)
        )
        self.assertEqual(sprite_uses, expected_ids)
        for relational_object in self.relational_objects:
            with self.subTest(object_id=relational_object.object_id):
                self.assertIn(relational_object.symbol_path, page)
        self.assertIn("window.RELATIONAL_OBJECTS", page)
        self.assertIn("INVARIANT RELATIONAL OBJECT BUS", page)
        self.assertIn("relational-topology.svg", page)

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
