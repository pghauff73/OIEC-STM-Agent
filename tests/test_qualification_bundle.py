from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.finalize_qualification_bundle import (
    OWNER_GATE_IDS,
    REQUIRED_GATE_IDS,
    qualify_requirements,
    validate_evidence_manifest,
)


def _artifact(path: Path, content: str = "ok\n") -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "path": path.name,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _gates(status: str = "PASS") -> dict[str, dict[str, object]]:
    return {
        gate_id: {
            "gate_id": gate_id,
            "status": status,
            "signature": f"signature-{gate_id}",
            "artifacts": (),
        }
        for gate_id in REQUIRED_GATE_IDS
    }


class QualificationBundleTests(unittest.TestCase):
    def test_evidence_manifest_is_source_bound_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary)
            artifact = _artifact(staging / "gate.log")
            payload = {
                "schema_version": 1,
                "source_tree_hash": "source-hash",
                "gates": [
                    {
                        "gate_id": gate_id,
                        "status": "SKIP" if gate_id == "opengl_optional" else "PASS",
                        "command": "command",
                        "started_utc": "2026-08-28T00:00:00Z",
                        "ended_utc": "2026-08-28T00:00:01Z",
                        "runtime": "Python 3.14",
                        "artifacts": [artifact],
                    }
                    for gate_id in REQUIRED_GATE_IDS
                ],
            }
            gates = validate_evidence_manifest(
                staging, payload, source_tree_hash="source-hash"
            )
            self.assertEqual(set(REQUIRED_GATE_IDS), set(gates))
            payload["source_tree_hash"] = "stale"
            with self.assertRaisesRegex(ValueError, "source tree hash mismatch"):
                validate_evidence_manifest(
                    staging, payload, source_tree_hash="source-hash"
                )

    def test_requirement_promotion_requires_every_owner_gate(self) -> None:
        inventory = {
            "schema_version": 1,
            "source_tree_hash": "source-hash",
            "requirement_count": 1,
            "requirements": [
                {
                    "requirement_id": "REQ-1",
                    "requirement_text": "Evidence remains monotonic",
                    "canonical_owner": "oiec_stm",
                    "status": "IMPLEMENTED_UNVERIFIED",
                    "blocking_dependencies": [],
                }
            ],
            "signature": "old",
        }
        gates = _gates()
        qualified = qualify_requirements(inventory, gates)
        self.assertEqual("FULLY_VALIDATED", qualified["requirements"][0]["status"])
        failed_gate = OWNER_GATE_IDS["oiec_stm"][0]
        gates[failed_gate] = dict(gates[failed_gate], status="FAIL")
        qualified = qualify_requirements(inventory, gates)
        self.assertEqual(
            "IMPLEMENTED_UNVERIFIED", qualified["requirements"][0]["status"]
        )
        self.assertEqual(
            [failed_gate], qualified["requirements"][0]["blocking_dependencies"]
        )

    def test_release_transition_and_human_approval_are_not_auto_promoted(self) -> None:
        inventory = {
            "schema_version": 1,
            "source_tree_hash": "source-hash",
            "requirement_count": 2,
            "requirements": [
                {
                    "requirement_id": "REQ-RELEASE",
                    "requirement_text": "Merge to main",
                    "canonical_owner": "release",
                    "status": "IMPLEMENTED_UNVERIFIED",
                    "blocking_dependencies": [],
                },
                {
                    "requirement_id": "REQ-APPROVAL",
                    "requirement_text": "Obtain exact-hash human approval",
                    "canonical_owner": "authority_policy",
                    "status": "HUMAN_APPROVAL_REQUIRED",
                    "blocking_dependencies": [],
                },
            ],
            "signature": "old",
        }
        rows = qualify_requirements(inventory, _gates())["requirements"]
        self.assertEqual("NOT_IMPLEMENTED", rows[0]["status"])
        self.assertEqual("HUMAN_APPROVAL_REQUIRED", rows[1]["status"])


if __name__ == "__main__":
    unittest.main()
