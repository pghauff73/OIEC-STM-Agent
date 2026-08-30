from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.docs_learning_catalog import INVENTION_TIMELINE, TASK_ROUTES


class DocumentationInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"
        cls.javascript = (cls.docs_root / "assets" / "site.js").read_text(encoding="utf-8")

    def test_new_interactions_are_declared(self) -> None:
        for name in (
            "setupDocumentationViews",
            "setupTeacherMode",
            "setupVocabularyMemory",
            "setupIntentSearch",
            "setupTutorialSandboxes",
            "setupAcronymInspector",
            "setupStatusDecoder",
            "setupCommandBuilder",
            "setupProviderWizard",
            "setupSharedSvgCards",
        ):
            self.assertIn(name, self.javascript)

    def test_embedded_tool_catalogs_are_valid_json(self) -> None:
        pages_and_ids = (
            ("tools.html", "command-recipes"),
            ("tools.html", "rejected-recipes"),
            ("glossary.html", "acronym-catalog"),
            ("status-decoder.html", "status-catalog"),
        )
        for page_name, element_id in pages_and_ids:
            page = (self.docs_root / page_name).read_text(encoding="utf-8")
            match = re.search(
                rf'<script type="application/json" id="{element_id}">(.*?)</script>',
                page,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match)
            json.loads(match.group(1))

    def test_tools_cover_provider_capability_gui_and_explanation_routes(self) -> None:
        page = (self.docs_root / "tools.html").read_text(encoding="utf-8")
        for term in (
            "PROVIDER SETUP WIZARD",
            "OpenAI-compatible service",
            "CAPABILITY WORKSHOP",
            "GUI FIRST LAUNCH",
            "Trace This Term",
            "Break the invariant",
            "Failure museum",
        ):
            self.assertIn(term, page)
        for capability in range(6):
            self.assertIn(f"<strong>C{capability}</strong>", page)
        for step in ("Repository.", "Ask.", "Inspect.", "Evidence.", "Decide."):
            self.assertIn(step, page)

    def test_intent_routes_cover_natural_language_failure_and_provider_queries(self) -> None:
        by_id = {route.route_id: route for route in TASK_ROUTES}
        self.assertIn("repeating failed action", by_id["understand-failure"].search_terms)
        self.assertIn("local model", by_id["use-ollama"].search_terms)
        homepage = (self.docs_root / "index.html").read_text(encoding="utf-8")
        self.assertIn('placeholder="agent keeps repeating a failed action"', homepage)
        for route in TASK_ROUTES:
            self.assertIn(f'data-intent-terms="{" ".join(route.search_terms)}"', homepage)

    def test_timeline_and_failure_museum_are_source_bound(self) -> None:
        timeline = (self.docs_root / "timeline.html").read_text(encoding="utf-8")
        for entry in INVENTION_TIMELINE:
            self.assertIn(f'id="timeline-{entry.entry_id}"', timeline)
            for source_path in entry.source_paths:
                self.assertTrue(Path(source_path).is_file(), source_path)
                self.assertIn(source_path, timeline)
        museum = (self.docs_root / "failure-museum.html").read_text(encoding="utf-8")
        self.assertIn("DETERMINISTIC REFUSAL", museum)
        self.assertIn("Why it stopped:", museum)
        self.assertIn("Evidence needed:", museum)


if __name__ == "__main__":
    unittest.main()
