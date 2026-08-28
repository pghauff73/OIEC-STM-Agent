from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ourd_gui.evidence_exports import evidence_json, evidence_markdown
from ourd_gui.read_models import ReadOnlyEGCFRepository

from .fixtures_v1 import install_fixture_repository


class EvidenceExportTests(unittest.TestCase):
    def test_exports_preserve_ids_hashes_limits_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = install_fixture_repository(root)
            repository = ReadOnlyEGCFRepository(root)
            identifiers = [bundle.ids["confidence"], bundle.ids["evidence"]]
            payload = json.loads(evidence_json(repository, identifiers))
            self.assertFalse(payload["authoritative"])
            self.assertEqual(bundle.source_snapshot_hash, payload["current_source_snapshot_hash"])
            evidence_record = next(
                item for item in payload["records"] if item["object_id"] == bundle.ids["evidence"]
            )
            self.assertEqual(bundle.source_snapshot_hash, evidence_record["payload"]["source_snapshot_hash"])
            self.assertTrue(evidence_record["payload"]["limitations"])
            markdown = evidence_markdown(repository, identifiers)
            self.assertIn(bundle.ids["evidence"], markdown)
            self.assertIn("content hash", markdown)
            self.assertIn("Limitation:", markdown)


if __name__ == "__main__":
    unittest.main()
