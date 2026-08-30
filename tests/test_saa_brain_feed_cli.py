from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ourd.brain_cli import main as brain_main
from ourd.entrypoint import main as entrypoint_main
from ourd.egcf.brain_feed_store import BrainFeedStore
from ourd.egcf.knowledge_governance_store import KnowledgeGovernanceStore
from ourd.egcf.semantic_ontology import SemanticOntologyStore
from ourd.egcf.store import EGCFStore


def manifest() -> dict:
    return {
        "schema_version": 1,
        "batch_id": "thermal-lab-test",
        "source_label": "thermal batch test",
        "items": [
            {
                "id": "measurement-1",
                "kind": "MEASUREMENT",
                "payload": {
                    "subject_id": "thermal-control",
                    "producer": "deterministic-test-sensor",
                    "method": "calibrated-temperature-measurement",
                    "target": "coolant temperature",
                    "oracle": "test thermocouple",
                    "independence_group": "test-run-1",
                    "content": {"value": "83.2", "unit": "degC"},
                    "success": True,
                    "simulated": False,
                },
            },
            {
                "id": "meaning-1",
                "kind": "SEMANTIC_CONCEPT",
                "evidence_from": ["measurement-1"],
                "payload": {
                    "name": "coolant temperature",
                    "meaning": "thermodynamic temperature of engine coolant at the declared sensor location",
                    "domain": "automotive thermal control",
                    "quantity_kind": "temperature",
                    "physical_dimension": [0, 0, 0, 0, 1, 0, 0],
                    "canonical_unit": "degC",
                    "semantic_status": "SEMANTICALLY_RESOLVED",
                },
            },
            {
                "id": "algorithm-1",
                "kind": "ALGORITHM_CANDIDATE",
                "depends_on": ["meaning-1"],
                "evidence_from": ["measurement-1"],
                "payload": {
                    "name": "thermal threshold detector",
                    "inputs": ["coolant temperature"],
                    "outputs": ["overheat flag"],
                    "procedure": "compare representative temperature with a qualified threshold",
                    "meanings": {"input": "coolant temperature", "output": "overheat state"},
                },
            },
            {
                "id": "failure-1",
                "kind": "FAILURE",
                "evidence_from": ["measurement-1"],
                "payload": {
                    "source_kind": "thermal experiment",
                    "component": "coolant temperature sensor",
                    "failure_class": "EVIDENCE_FAILURE",
                    "mechanism": "calibration drift contradicted the expected measurement tolerance",
                    "semantic_roles": ["temperature observation"],
                    "violated_invariants": ["measurement remains within calibration tolerance"],
                },
            },
        ],
    }


class SAA BrainFeedCLITests(unittest.TestCase):
    def _write_manifest(self, root: Path, payload: dict | None = None) -> Path:
        path = root / "brain-feed.json"
        path.write_text(json.dumps(payload or manifest(), indent=2), encoding="utf-8")
        return path

    def test_batch_routes_grounded_knowledge_and_stages_algorithm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._write_manifest(root)
            output = io.StringIO()
            with redirect_stdout(output):
                status = brain_main(["feed", str(source), "--repo", str(root), "--verbose"])
            self.assertEqual(0, status)
            self.assertIn("canonical algorithm admissions: 0", output.getvalue())
            with EGCFStore(root) as egcf:
                feed = BrainFeedStore(egcf)
                dispositions = {row["payload"]["item_id"]: row["payload"] for row in feed.dispositions()}
                self.assertEqual("REGISTERED_EVIDENCE", dispositions["measurement-1"]["status"])
                self.assertEqual("ADMITTED_SEMANTIC_CONCEPT", dispositions["meaning-1"]["status"])
                self.assertEqual(
                    "STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED",
                    dispositions["algorithm-1"]["status"],
                )
                self.assertEqual("REGISTERED_FAILURE", dispositions["failure-1"]["status"])
                self.assertFalse(dispositions["algorithm-1"]["canonical_algorithm_admission_attempted"])
                self.assertTrue(dispositions["algorithm-1"]["target_refs"][0].startswith("brain-feed-item:sha256:"))
                self.assertEqual(1, len(SemanticOntologyStore(egcf).concepts()))
                self.assertEqual(1, len(KnowledgeGovernanceStore(egcf).failure_patterns()))
                receipt = feed.batches()[-1]["payload"]
                self.assertEqual(3, receipt["admitted_count"])
                self.assertEqual(1, receipt["staged_count"])
                self.assertEqual(0, receipt["canonical_algorithm_admissions"])

    def test_refeeding_same_manifest_is_idempotent_and_reported_as_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._write_manifest(root)
            self.assertEqual(0, brain_main(["feed", str(source), "--repo", str(root), "--json"]))
            self.assertEqual(0, brain_main(["feed", str(source), "--repo", str(root), "--json"]))
            with EGCFStore(root) as egcf:
                feed = BrainFeedStore(egcf)
                self.assertEqual(4, len(feed.dispositions()))
                latest = feed.batches()[-1]["payload"]
                self.assertEqual(4, latest["duplicate_count"])
                self.assertEqual(0, latest["canonical_algorithm_admissions"])

    def test_ungrounded_measurement_and_meaning_remain_staged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = manifest()
            payload["items"] = payload["items"][:2]
            payload["items"][0]["payload"]["producer"] = "unknown-sensor"
            source = self._write_manifest(root, payload)
            self.assertEqual(0, brain_main(["feed", str(source), "--repo", str(root)]))
            with EGCFStore(root) as egcf:
                dispositions = {row["payload"]["item_id"]: row["payload"] for row in BrainFeedStore(egcf).dispositions()}
                self.assertEqual("STAGED_EVIDENCE_METADATA_REQUIRED", dispositions["measurement-1"]["status"])
                self.assertEqual("STAGED_EVIDENCE_REQUIRED", dispositions["meaning-1"]["status"])
                self.assertEqual(0, len(SemanticOntologyStore(egcf).concepts()))

    def test_malformed_algorithm_is_quarantined_and_strict_feed_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {
                "batch_id": "bad-candidate",
                "items": [{"id": "bad-alg", "kind": "ALGORITHM_CANDIDATE", "payload": {"name": "bad"}}],
            }
            source = self._write_manifest(root, payload)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = brain_main(["feed", str(source), "--repo", str(root), "--strict"])
            self.assertEqual(2, status)
            with EGCFStore(root) as egcf:
                quarantined = BrainFeedStore(egcf).quarantined()
                self.assertEqual(1, len(quarantined))
                self.assertEqual("QUARANTINED", quarantined[0]["payload"]["status"])

    def test_validate_detects_cycle_without_creating_brain_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {
                "batch_id": "cycle",
                "items": [
                    {"id": "a", "kind": "CLAIM", "depends_on": ["b"], "payload": {"statement": "a"}},
                    {"id": "b", "kind": "CLAIM", "depends_on": ["a"], "payload": {"statement": "b"}},
                ],
            }
            source = self._write_manifest(root, payload)
            output = io.StringIO()
            with redirect_stdout(output):
                status = brain_main(["validate", str(source)])
            self.assertEqual(2, status)
            self.assertIn("CYCLIC_OR_UNRESOLVED_DEPENDENCY", output.getvalue())
            self.assertFalse((root / ".ourd-agent" / "egcf" / "brain-feed").exists())

    def test_installed_entrypoint_dispatches_brain_help(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
            entrypoint_main(["brain", "--help"])
        self.assertEqual(0, raised.exception.code)
        self.assertIn("Batch-feed evidence and candidate knowledge", output.getvalue())


if __name__ == "__main__":
    unittest.main()
