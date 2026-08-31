from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.h1_count = 0
        self.references: list[tuple[str, str]] = []
        self.external_scripts: list[str] = []
        self.external_styles: list[str] = []
        self.has_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.has_main = True

        for attribute in ("href", "src", "data"):
            value = values.get(attribute)
            if value:
                self.references.append((attribute, value))

        if tag == "script" and values.get("src", "").startswith(("http://", "https://")):
            self.external_scripts.append(values["src"])
        if (
            tag == "link"
            and "stylesheet" in values.get("rel", "").split()
            and values.get("href", "").startswith(("http://", "https://"))
        ):
            self.external_styles.append(values["href"])


class FormalWritingSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.site = cls.root / "docs" / "formal-writing"
        cls.index = cls.site / "index.html"
        cls.html = cls.index.read_text(encoding="utf-8")
        cls.parser = _SiteParser()
        cls.parser.feed(cls.html)
        cls.manifest = json.loads(
            (cls.site / "source-manifest.json").read_text(encoding="utf-8")
        )

    def test_required_artifacts_exist(self) -> None:
        expected = {
            "index.html",
            "README.md",
            "source-manifest.json",
            "assets/formal.css",
            "assets/formal.js",
            "figures/governed-pipeline.svg",
            "figures/argument-topology.svg",
            "figures/evidence-boundary.svg",
        }
        self.assertEqual(expected, set(self.manifest["artifacts"]))
        for relative in sorted(expected):
            with self.subTest(relative=relative):
                self.assertTrue((self.site / relative).is_file(), relative)

    def test_document_structure_is_unambiguous(self) -> None:
        self.assertEqual(1, self.parser.h1_count)
        self.assertTrue(self.parser.has_main)
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))
        for required_id in {
            "top",
            "thesis",
            "architecture",
            "writing",
            "operation",
            "method",
            "sources",
        }:
            self.assertIn(required_id, self.parser.ids)

    def test_all_local_references_resolve(self) -> None:
        missing: list[str] = []
        for _attribute, value in self.parser.references:
            parsed = urlsplit(value)
            if parsed.scheme in {"http", "https", "mailto", "tel", "data"}:
                continue
            if not parsed.path:
                continue
            target = (self.site / parsed.path).resolve()
            if not target.exists():
                missing.append(value)
        self.assertEqual([], sorted(set(missing)))

    def test_no_remote_executable_or_stylesheet_dependency(self) -> None:
        self.assertEqual([], self.parser.external_scripts)
        self.assertEqual([], self.parser.external_styles)

    def test_manifest_source_and_claim_ids_are_unique_and_bound(self) -> None:
        sources = self.manifest["sources"]
        source_ids = [source["source_id"] for source in sources]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertGreaterEqual(len([s for s in sources if s["class"] == "project"]), 9)

        known = set(source_ids)
        claim_ids: set[str] = set()
        for claim in self.manifest["claims"]:
            self.assertNotIn(claim["claim_id"], claim_ids)
            claim_ids.add(claim["claim_id"])
            self.assertTrue(claim["source_ids"])
            self.assertLessEqual(set(claim["source_ids"]), known)

    def test_project_source_links_are_exact_snapshot_urls(self) -> None:
        base_commit = self.manifest["base_commit"]
        hrefs = {
            value
            for attribute, value in self.parser.references
            if attribute == "href"
        }
        project_urls = {
            value for value in hrefs if value.startswith("https://github.com/")
        }

        for source in self.manifest["sources"]:
            if source["class"] != "project":
                continue
            expected = (
                "https://github.com/pghauff73/OIEC-STM-Agent/blob/"
                f"{base_commit}/{source['repository_path']}"
            )
            with self.subTest(source_id=source["source_id"], expected=expected):
                self.assertIn(expected, project_urls)

        unsafe_relative_sources = {
            "../../README.md",
            "../../OIEC_STMV1_2_IMPLEMENTATION_REPORT.md",
            "../WRITING_MODE.md",
            "../../COMPLETE_IMPLEMENTATION_STRATEGY.md",
            "../../ourd/formal_writing.py",
            "../FORMAL_WRITING_RESEARCH.md",
            "../ACRONYM_GLOSSARY.md",
            "../../ourd/cli.py",
            "../../ourd/writing.py",
        }
        self.assertTrue(unsafe_relative_sources.isdisjoint(hrefs))

    def test_project_source_blob_hashes_match_declared_commit_and_worktree(self) -> None:
        if os.environ.get("OIEC_FORMAL_SITE_SKIP_SOURCE_HASH") == "1":
            self.skipTest("source hash verification disabled for an isolated site fixture")

        base_commit = self.manifest["base_commit"]
        for source in self.manifest["sources"]:
            if source["class"] != "project":
                continue

            path = self.root / source["repository_path"]
            declared = source["git_blob_sha"]
            with self.subTest(source_id=source["source_id"], path=path):
                self.assertTrue(path.is_file())

                committed = subprocess.run(
                    [
                        "git",
                        "rev-parse",
                        f"{base_commit}:{source['repository_path']}",
                    ],
                    cwd=self.root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self.assertEqual(declared, committed)

                payload = path.read_bytes()
                header = f"blob {len(payload)}\0".encode("ascii")
                working_tree = hashlib.sha1(header + payload).hexdigest()
                self.assertEqual(declared, working_tree)

    def test_workflow_tracks_executable_writing_sources(self) -> None:
        workflow = (
            self.root / ".github" / "workflows" / "formal-writing-site.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", workflow)
        for path in ("ourd/formal_writing.py", "ourd/cli.py", "ourd/writing.py"):
            with self.subTest(path=path):
                self.assertEqual(2, workflow.count(f'- "{path}"'))

    def test_svg_figures_are_accessible_and_static(self) -> None:
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        for path in sorted((self.site / "figures").glob("*.svg")):
            with self.subTest(path=path.name):
                document = ET.parse(path)
                svg = document.getroot()
                self.assertTrue(svg.tag.endswith("svg"))
                self.assertTrue(svg.get("viewBox"))
                title = svg.find("svg:title", namespace)
                description = svg.find("svg:desc", namespace)
                self.assertIsNotNone(title)
                self.assertIsNotNone(description)
                self.assertTrue((title.text or "").strip())
                self.assertTrue((description.text or "").strip())
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("<script", text.lower())
                self.assertNotRegex(text, r"https?://(?!www\.w3\.org/2000/svg)")

    def test_browser_script_is_bounded_and_offline(self) -> None:
        script = (self.site / "assets" / "formal.js").read_text(encoding="utf-8")
        forbidden = (
            r"\beval\s*\(",
            r"\bFunction\s*\(",
            r"\bfetch\s*\(",
            r"\bXMLHttpRequest\b",
            r"\bWebSocket\b",
            r"\bdocument\.write\s*\(",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(script, pattern)

    def test_epistemic_labels_match_runtime_scope(self) -> None:
        self.assertIn("Qualified editorial inference K1", self.html)
        self.assertIn("Machine-checkable topology", self.html)
        self.assertNotIn("<h3>Machine-checked topology</h3>", self.html)
        self.assertRegex(
            self.html,
            r"generated essays are not automatically constructed or\s+validated",
        )
        self.assertRegex(
            self.html,
            r"conclusion that these controls\s+impose process cost",
        )

    def test_no_placeholder_or_certification_language(self) -> None:
        self.assertNotRegex(
            self.html,
            re.compile(r"\b(?:TODO|TBD|lorem ipsum|example\.com)\b", re.IGNORECASE),
        )
        self.assertIn("No certification claim", self.html)
        self.assertIn("does not convert", self.html)
        self.assertIn("not a verbatim runtime API", self.html)


if __name__ == "__main__":
    unittest.main()
