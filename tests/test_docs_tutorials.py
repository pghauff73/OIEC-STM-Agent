from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.docs_learning_catalog import CASE_STUDIES, TASK_ROUTES, TUTORIALS


class DocumentationTutorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.docs_root = Path(__file__).resolve().parents[1] / "docs"
        payload = json.loads((cls.docs_root / "tutorial" / "fixtures" / "core-learning.json").read_text(encoding="utf-8"))
        cls.fixture_ids = {record["fixture_id"] for record in payload["fixtures"]}
        cls.fixture_ids.update(record["refusal_id"] for record in payload["refusals"])

    def test_every_lesson_has_generated_modes_diagram_and_fixtures(self) -> None:
        for lesson in TUTORIALS:
            page_path = Path(lesson.source_path).with_suffix(".html")
            page = page_path.read_text(encoding="utf-8")
            self.assertIn('data-doc-view="learn"', page)
            self.assertIn('data-view-content="technical"', page)
            self.assertIn("Teacher mode", page)
            self.assertIn("Documentation evidence", page)
            self.assertTrue(set(lesson.fixture_ids) <= self.fixture_ids)
            figure = self.docs_root / "figures" / "tutorial" / f"{lesson.lesson_id.lower()}.svg"
            self.assertTrue(figure.is_file())

    def test_task_routes_and_case_studies_are_generated(self) -> None:
        self.assertTrue((self.docs_root / "tasks" / "index.html").is_file())
        self.assertTrue((self.docs_root / "case-studies" / "index.html").is_file())
        for record in (*TASK_ROUTES, *CASE_STUDIES):
            page = Path(record.source_path).with_suffix(".html")
            self.assertTrue(page.is_file())
            self.assertRegex(page.read_text(encoding="utf-8"), r'data-view-content="(?:learn|technical)"')

    def test_refusal_lessons_publish_break_the_invariant_fixtures(self) -> None:
        for lesson_id, refusal_id in (
            ("T07", "write-with-yolo"),
            ("T10", "adapt-two-dimensions"),
            ("T12", "promote-without-evidence"),
        ):
            lesson = next(item for item in TUTORIALS if item.lesson_id == lesson_id)
            page = Path(lesson.source_path).with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn(f'data-tutorial-sandbox="{refusal_id}"', page)
            self.assertNotIn("fetch(", page)


if __name__ == "__main__":
    unittest.main()
