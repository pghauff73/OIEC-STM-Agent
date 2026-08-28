from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ourd_gui.evidence_graph import evidence_graph
from ourd_gui.read_models import ReadOnlyEGCFRepository

from .fixtures_v1 import install_fixture_repository


class EvidenceGraphTests(unittest.TestCase):
    def test_graph_links_support_records_subjects_and_exact_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            nodes, edges = evidence_graph(
                ReadOnlyEGCFRepository(root),
                [bundle.ids["confidence"], bundle.ids["evidence"]],
            )
            object_ids = {node.object_id for node in nodes}
            self.assertIn(bundle.ids["confidence"], object_ids)
            self.assertIn(bundle.ids["evidence"], object_ids)
            self.assertTrue(any(edge.label == "references" for edge in edges))
            self.assertTrue(any(edge.label == "supported by" for edge in edges))


if __name__ == "__main__":
    unittest.main()
