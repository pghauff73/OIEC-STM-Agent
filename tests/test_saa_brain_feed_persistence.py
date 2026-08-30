from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ourd.brain_cli import main as brain_main
from ourd.egcf.brain_feed_store import BrainFeedStore
from ourd.egcf.store import EGCFStore


class SAABrainFeedPersistenceTests(unittest.TestCase):
    def test_directory_feed_survives_projection_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            feed_dir = root / "feed"
            feed_dir.mkdir()
            (feed_dir / "01-measurement.json").write_text(
                json.dumps(
                    {
                        "id": "m1",
                        "kind": "MEASUREMENT",
                        "payload": {
                            "subject_id": "test-subject",
                            "producer": "deterministic-test-sensor",
                            "method": "calibrated-measurement",
                            "target": "temperature",
                            "oracle": "test-oracle",
                            "independence_group": "run-a",
                            "content": {"value": "300", "unit": "K"},
                            "success": True,
                            "simulated": False
                        }
                    }
                ),
                encoding="utf-8",
            )
            (feed_dir / "02-algorithm.json").write_text(
                json.dumps(
                    {
                        "id": "a1",
                        "kind": "ALGORITHM_CANDIDATE",
                        "evidence_from": ["m1"],
                        "payload": {
                            "name": "temperature threshold",
                            "inputs": ["temperature"],
                            "outputs": ["flag"],
                            "procedure": "compare temperature with a threshold",
                            "meanings": {"input": "temperature", "output": "threshold state"}
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(0, brain_main(["feed", str(feed_dir), "--repo", str(root)]))
            with EGCFStore(root) as egcf:
                store = BrainFeedStore(egcf)
                self.assertEqual(2, len(store.dispositions()))
                self.assertEqual(1, len(store.batches()))
                store.rebuild_projection()
                self.assertEqual(2, len(store.dispositions()))
                self.assertEqual(1, len(store.batches()))
                statuses = {row["payload"]["item_id"]: row["payload"]["status"] for row in store.dispositions()}
                self.assertEqual("REGISTERED_EVIDENCE", statuses["m1"])
                self.assertEqual("STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED", statuses["a1"])


if __name__ == "__main__":
    unittest.main()
