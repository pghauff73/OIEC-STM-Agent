from __future__ import annotations

import unittest

from tools.docs_status_catalog import discover_statuses, validate_statuses


class DocumentationStatusCatalogTests(unittest.TestCase):
    def test_source_statuses_are_closed_and_decodable(self) -> None:
        statuses = discover_statuses()
        validate_statuses(statuses)
        by_status = {record.status: record for record in statuses}
        required = {
            "QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND",
            "SEMANTIC_MISREPRESENTATION",
            "NON_REPRESENTATIVE_COUPLED",
            "CANDIDATE_IMPROVEMENT_QUALIFIED",
            "CLOSED_LOOP_IMPROVEMENT_VERIFIED",
        }
        self.assertTrue(required <= set(by_status))
        self.assertGreaterEqual(len(statuses), 50)
        for record in statuses:
            self.assertTrue(record.plain_language_meaning)
            self.assertTrue(record.trigger)
            self.assertTrue(record.what_happens_next)
            self.assertTrue(record.user_action)
            self.assertTrue(record.source_paths)


if __name__ == "__main__":
    unittest.main()
