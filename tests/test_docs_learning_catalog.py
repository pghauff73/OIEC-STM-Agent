from __future__ import annotations

import unittest
from pathlib import Path

from tools.docs_concept_catalog import discover_concepts
from tools.docs_learning_catalog import (
    ACRONYMS,
    CASE_STUDIES,
    CONTENT_KINDS,
    DOCUMENTATION_STATUSES,
    LEARNING_PATHS,
    TASK_ROUTES,
    TUTORIAL_HEADINGS,
    TUTORIALS,
    teaching_record_for,
    validate_authored_acronyms,
    validate_catalog_sources,
    validate_prerequisite_graph,
)
from tools.build_docs_site import parse_sections


class DocumentationLearningCatalogTests(unittest.TestCase):
    def test_curriculum_is_complete_and_ordered(self) -> None:
        self.assertEqual(len(TUTORIALS), 14)
        self.assertEqual([lesson.lesson_id for lesson in TUTORIALS], [f"T{index:02d}" for index in range(14)])
        self.assertEqual([lesson.ordinal for lesson in TUTORIALS], list(range(14)))
        self.assertEqual(TUTORIALS[-1].next_lesson_id, "")
        for current, following in zip(TUTORIALS, TUTORIALS[1:]):
            self.assertEqual(current.next_lesson_id, following.lesson_id)

    def test_tutorial_sources_follow_the_heading_contract(self) -> None:
        validate_catalog_sources()
        for lesson in TUTORIALS:
            sections = parse_sections(Path(lesson.source_path).read_text(encoding="utf-8"))
            self.assertEqual(
                tuple(section.title for section in sections[1:]),
                TUTORIAL_HEADINGS,
                lesson.lesson_id,
            )

    def test_paths_routes_cases_and_content_kinds_are_closed(self) -> None:
        lesson_ids = {lesson.lesson_id for lesson in TUTORIALS}
        path_ids = {path.path_id for path in LEARNING_PATHS}
        self.assertEqual(len(TASK_ROUTES), 9)
        self.assertEqual(len(CASE_STUDIES), 8)
        self.assertEqual(len(CONTENT_KINDS), len(set(CONTENT_KINDS)))
        self.assertEqual(set(DOCUMENTATION_STATUSES), {"Implemented", "Tested", "Experimental", "Theoretical", "Planned"})
        for path in LEARNING_PATHS:
            self.assertTrue(set(path.ordered_item_ids) <= lesson_ids)
            self.assertTrue(set(path.prerequisite_ids) <= path_ids)
        for route in TASK_ROUTES:
            self.assertTrue(set(route.ordered_item_ids) <= lesson_ids)
            self.assertTrue(Path(route.source_path).is_file())
        for case in CASE_STUDIES:
            self.assertTrue(Path(case.source_path).is_file())

    def test_mandatory_acronyms_have_complete_records(self) -> None:
        mandatory = {
            "OIEC", "STM", "SR", "OURD", "IURM", "EON", "CFEL", "EGCF",
            "HRT", "IEPS", "BD", "DL", "SAA", "CLI", "GUI", "DAG",
            "PEP", "PEP 517", "EGL", "API", "ABI",
        }
        by_token = {record.token: record for record in ACRONYMS}
        self.assertEqual(mandatory, set(by_token))
        for record in ACRONYMS:
            self.assertTrue(record.expansion)
            self.assertTrue(record.short_meaning)
            self.assertTrue(record.everyday_analogy)
            self.assertTrue(record.formal_meaning)
            self.assertTrue(record.source_paths)
        validate_authored_acronyms()

    def test_every_concept_satisfies_the_teaching_contract(self) -> None:
        concepts = discover_concepts()
        records = tuple(teaching_record_for(concept) for concept in concepts)
        self.assertEqual(len(records), len(concepts))
        validate_prerequisite_graph(records)
        for record in records:
            with self.subTest(concept=record.concept_id):
                for field in (
                    record.full_name,
                    record.short_meaning,
                    record.why_it_exists,
                    record.everyday_analogy,
                    record.oiec_example,
                    record.inputs,
                    record.outputs,
                    record.misconception,
                    record.diagram,
                    record.formal_novice,
                    record.formal_intermediate,
                    record.formal_expert,
                    record.failure_example,
                    record.documentation_status,
                    record.authorship,
                ):
                    self.assertTrue(field)
                self.assertTrue(record.source_links)
                self.assertTrue(record.status_evidence)
                self.assertIn(record.documentation_status, DOCUMENTATION_STATUSES)


if __name__ == "__main__":
    unittest.main()
