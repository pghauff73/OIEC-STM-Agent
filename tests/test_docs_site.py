from __future__ import annotations

import hashlib
import html
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

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

    def assert_logic_records_follow_topology(
        self,
        records: list[tuple[str, str, str, str, str, str, str]],
    ) -> None:
        expected_nodes = build_docs_site.flattened_essay_logic_nodes()
        self.assertEqual(len(records), len(expected_nodes))
        for index, (record, expected) in enumerate(zip(records, expected_nodes), start=1):
            _, node_id, stage, topic, order, predecessor, successor = record
            expected_stage, expected_node_id, expected_topic = expected
            self.assertEqual(node_id, expected_node_id)
            self.assertEqual(html.unescape(stage), expected_stage)
            self.assertEqual(html.unescape(topic), expected_topic)
            self.assertEqual(int(order), index)
            self.assertEqual(
                predecessor,
                build_docs_site.ESSAY_LOGIC_ORDER[index - 2] if index > 1 else "",
            )
            self.assertEqual(
                successor,
                build_docs_site.ESSAY_LOGIC_ORDER[index]
                if index < len(build_docs_site.ESSAY_LOGIC_ORDER)
                else "",
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
                    paragraphs = re.findall(r'data-essay-paragraph="[1-5]"', block)
                    self.assertEqual(len(paragraphs), 5)

    def test_every_heading_essay_is_claim_led_beginner_defined_and_decisive(self) -> None:
        forbidden = re.compile(
            r"\b(?:introduction|introductory|body movement|body section|final conclusion|this conclusion|evidence conclusion)\b",
            flags=re.IGNORECASE,
        )
        expected_labels = [
            "Claim to prove",
            "How it works",
            "What proves it",
            "What could defeat it",
            "Winning position",
        ]
        for document in self.documents:
            page = document.output_path.read_text(encoding="utf-8")
            labels = re.findall(
                r'<section class="essay-block [^"]+" aria-label="([^"]+)">',
                page,
            )
            with self.subTest(document=document.relative_path.as_posix()):
                self.assertEqual(
                    labels,
                    expected_labels * len(document.sections),
                )
                essay_sequences = re.findall(
                    r'<div class="essay-sequence">(.*?)</div>',
                    page,
                    flags=re.DOTALL,
                )
                self.assertEqual(len(essay_sequences), len(document.sections))
                for section, sequence in zip(document.sections, essay_sequences):
                    self.assertIsNone(forbidden.search(sequence))
                    self.assertIn("Claim to prove:", sequence)
                    self.assertIn("The winning position", sequence)
                    vocabulary = build_docs_site.generate_essay_blocks(
                        document,
                        section,
                    )[0][1]
                    for acronym in build_docs_site.detected_acronyms(
                        f"{section.title}\n{section.markdown}"
                    ):
                        self.assertIn(
                            f"<strong>{html.escape(acronym)}</strong> means",
                            vocabulary,
                        )

    def test_detected_source_acronyms_have_explicit_definitions(self) -> None:
        for document in self.documents:
            for section in document.sections:
                for acronym in build_docs_site.detected_acronyms(
                    f"{section.title}\n{section.markdown}"
                ):
                    with self.subTest(
                        document=document.relative_path.as_posix(),
                        section=section.slug,
                        acronym=acronym,
                    ):
                        definition = build_docs_site.definition_for(acronym)
                        self.assertTrue(definition.strip())
                        if (
                            acronym not in build_docs_site.GLOSSARY
                            and acronym not in build_docs_site.CONSTANT_DEFINITIONS
                        ):
                            self.assertIn(
                                "project-specific identifier",
                                definition.casefold(),
                            )

    def test_document_citations_are_topic_matched_and_closed(self) -> None:
        for document in self.documents:
            page = document.output_path.read_text(encoding="utf-8")
            rendered_ids = set(re.findall(r'id="(ref-[^"]+)"', page))
            cited_ids = set(
                re.findall(r'class="citation-chip" href="#([^"]+)"', page)
            )
            expected_reference_ids = {
                f"ref-{reference_id}"
                for section in document.sections
                for reference_id in build_docs_site.topic_reference_ids(
                    f"{document.title}\n{section.title}\n{section.markdown}"
                )
            }
            with self.subTest(document=document.relative_path.as_posix()):
                self.assertIn("ref-S1", rendered_ids)
                self.assertTrue(cited_ids <= rendered_ids)
                self.assertEqual(
                    {item for item in rendered_ids if item.startswith("ref-R")},
                    expected_reference_ids,
                )

    def test_document_logic_topology_covers_every_paragraph_once(self) -> None:
        paragraph_pattern = re.compile(
            r'<p id="([^"]+)" data-essay-paragraph="[1-5]" '
            r'data-logic-node="([^"]+)" data-logic-stage="([^"]+)" '
            r'data-logic-topic="([^"]+)" data-logic-order="(\d+)" '
            r'data-logic-predecessor="([^"]*)" data-logic-successor="([^"]*)">'
        )
        for document in self.documents:
            page = document.output_path.read_text(encoding="utf-8")
            records = paragraph_pattern.findall(page)
            map_targets = re.findall(r'data-logic-target="([^"]+)"', page)
            with self.subTest(document=document.relative_path.as_posix()):
                self.assertEqual(len(records), len(document.sections) * 25)
                self.assertEqual(len(map_targets), len(document.sections) * 25)
                self.assertEqual(
                    {record[0] for record in records},
                    set(map_targets),
                )
                for section in document.sections:
                    expected_ids = {
                        build_docs_site.logic_paragraph_id(section.slug, node_id)
                        for node_id in build_docs_site.ESSAY_LOGIC_ORDER
                    }
                    section_records = [
                        record
                        for record in records
                        if record[0] in expected_ids
                    ]
                    self.assert_logic_records_follow_topology(section_records)

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
        self.assertIn("setupEssayLogicMaps", javascript)
        self.assertIn("is-logic-complete", javascript)
        self.assertIn("activeLogicNode", javascript)
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

    def test_every_concept_essay_is_claim_led_beginner_defined_and_decisive(self) -> None:
        forbidden = re.compile(
            r"\b(?:introduction|introductory|body movement|body section|final conclusion|this conclusion|evidence conclusion)\b",
            flags=re.IGNORECASE,
        )
        for concept in self.concepts:
            page_path = self.docs_root / "concepts" / f"{concept.slug}.html"
            page = page_path.read_text(encoding="utf-8")
            sequence = re.search(
                r'<article class="concept-essay">.*?<div class="essay-sequence">(.*?)</div></article>',
                page,
                flags=re.DOTALL,
            )
            with self.subTest(concept=concept.slug):
                self.assertIsNotNone(sequence)
                essay = sequence.group(1)
                self.assertIsNone(forbidden.search(essay))
                self.assertIn("Claim to prove:", essay)
                self.assertIn("The winning position", essay)
                vocabulary = build_docs_site.generate_concept_essay_blocks(concept)[0][1]
                concept_text = "\n".join(
                    (
                        concept.title,
                        concept.definition,
                        concept.thesis,
                        concept.inputs,
                        concept.controls,
                        concept.evidence,
                        concept.outcome,
                    )
                )
                for acronym in build_docs_site.detected_acronyms(concept_text):
                    self.assertIn(
                        f"<strong>{html.escape(acronym)}</strong> means",
                        vocabulary,
                    )
                rendered_ids = set(re.findall(r'id="(ref-[^"]+)"', page))
                cited_ids = set(
                    re.findall(r'class="citation-chip" href="#([^"]+)"', page)
                )
                expected = {
                    f"ref-{reference_id}"
                    for reference_id in build_docs_site.concept_citations(concept)
                }
                self.assertTrue(cited_ids <= rendered_ids)
                self.assertEqual(
                    {item for item in rendered_ids if item.startswith("ref-R")},
                    expected,
                )

    def test_concept_logic_topology_covers_every_paragraph_once(self) -> None:
        for concept in self.concepts:
            page = (
                self.docs_root / "concepts" / f"{concept.slug}.html"
            ).read_text(encoding="utf-8")
            records = re.findall(
                r'<p id="([^"]+)" data-concept-paragraph="[1-5]" '
                r'data-logic-node="([^"]+)" data-logic-stage="([^"]+)" '
                r'data-logic-topic="([^"]+)" data-logic-order="(\d+)" '
                r'data-logic-predecessor="([^"]*)" data-logic-successor="([^"]*)">',
                page,
            )
            map_targets = re.findall(r'data-logic-target="([^"]+)"', page)
            with self.subTest(concept=concept.slug):
                self.assertEqual(len(records), 25)
                self.assertEqual(
                    {record[0] for record in records},
                    set(map_targets),
                )
                self.assert_logic_records_follow_topology(records)

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
        self.assertEqual(
            self.manifest["essay_contract"],
            {
                "paragraphs_per_essay": 25,
                "stages": 5,
                "ordering": "topological",
                "entry_node": "claim-proposition",
                "final_node": "verdict-winner",
                "final_requirement": "Summarise the tested claim and name the winning position.",
            },
        )
        self.assertEqual(
            self.manifest["essay_logic_topology"],
            [
                {
                    "stage": stage,
                    "nodes": [
                        {"id": node_id, "topic": topic}
                        for node_id, topic in nodes
                    ],
                }
                for stage, nodes in build_docs_site.ESSAY_LOGIC_TOPOLOGY
            ],
        )
        self.assertEqual(
            self.manifest["essay_logic_edges"],
            [
                {"source": source, "target": target}
                for source, target in build_docs_site.ESSAY_LOGIC_EDGES
            ],
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

    def test_every_local_page_and_anchor_link_resolves(self) -> None:
        repository_root = self.docs_root.parent.resolve()
        html_id_cache: dict[Path, set[str]] = {}

        def html_ids(path: Path) -> set[str]:
            if path not in html_id_cache:
                page = path.read_text(encoding="utf-8")
                html_id_cache[path] = set(re.findall(r'id="([^"]+)"', page))
            return html_id_cache[path]

        missing = []
        for page_path in sorted(self.docs_root.rglob("*.html")):
            page = page_path.read_text(encoding="utf-8")
            hrefs = re.findall(r'<a\b[^>]*href="([^"]+)"', page)
            for href in hrefs:
                if href.startswith(("http://", "https://", "mailto:", "javascript:")):
                    continue
                raw_path, separator, fragment = href.partition("#")
                target = (
                    (page_path.parent / unquote(raw_path)).resolve()
                    if raw_path
                    else page_path.resolve()
                )
                if not target.exists() or repository_root not in (target, *target.parents):
                    missing.append((page_path.relative_to(self.docs_root).as_posix(), href))
                    continue
                if (
                    separator
                    and target.suffix.lower() == ".html"
                    and unquote(fragment) not in html_ids(target)
                ):
                    missing.append((page_path.relative_to(self.docs_root).as_posix(), href))

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
