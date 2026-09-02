from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.docs_visual_grammar import EDGE_ROLE_NAMES, NODE_ROLE_NAMES, VISUAL_GRAMMAR_VERSION


class DocumentationVisualGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"

    def test_every_generated_svg_declares_accessible_visual_grammar(self) -> None:
        paths = sorted((self.docs_root / "figures").rglob("*.svg"))
        self.assertGreaterEqual(len(paths), 1384)
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        for path in paths:
            with self.subTest(path=path.relative_to(self.docs_root).as_posix()):
                root = ET.parse(path).getroot()
                self.assertEqual(root.attrib.get("data-visual-grammar"), str(VISUAL_GRAMMAR_VERSION))
                self.assertTrue(root.attrib.get("data-visual-role"))
                self.assertIsNotNone(root.find("svg:title", namespace))
                self.assertIsNotNone(root.find("svg:desc", namespace))
                nodes = ([root] if "data-doc-node" in root.attrib else []) + root.findall(".//*[@data-doc-node]")
                self.assertTrue(nodes)
                for node in nodes:
                    self.assertIn(node.attrib.get("data-node-role"), NODE_ROLE_NAMES)
                    self.assertEqual(node.attrib.get("tabindex"), "0")

    def test_tutorial_diagrams_use_typed_edges(self) -> None:
        for path in sorted((self.docs_root / "figures" / "tutorial").glob("*.svg")):
            root = ET.parse(path).getroot()
            for edge in root.findall(".//*[@data-verification]"):
                self.assertIn(edge.attrib["data-verification"], EDGE_ROLE_NAMES)
                self.assertTrue(edge.attrib.get("data-relation"))


if __name__ == "__main__":
    unittest.main()
