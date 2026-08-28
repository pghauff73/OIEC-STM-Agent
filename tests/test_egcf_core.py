from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import closing

from ourd.egcf.catalog import command_catalog
from ourd.egcf.context import CommandContext
from ourd.egcf.errors import CompilationError, EGCFError
from ourd.egcf.ids import typed_id
from ourd.egcf.models import IntentRecord
from ourd.egcf.store import EGCFStore
from tests.helpers import RepoFixture


class EGCFCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_typed_identity_includes_object_type_and_payload(self) -> None:
        payload = {
            "raw_request": "inspect",
            "raw_request_hash": "abc",
            "actor": "user",
            "objective": "inspect",
            "assumptions": [],
            "ambiguities": [],
            "provenance": {},
            "created_at": "2026-08-21T00:00:00Z",
        }
        first = typed_id("intent", payload)
        second = typed_id("intent", dict(payload))
        changed = typed_id("intent", {**payload, "objective": "changed"})
        other_type = typed_id("artifact", payload)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertNotEqual(first, other_type)

    def test_object_and_artifact_projection_rebuilds_with_events(self) -> None:
        with EGCFStore(self.fixture.root) as store:
            record = IntentRecord(
                raw_request="inspect",
                raw_request_hash="abc",
                actor="user",
                objective="inspect",
                created_at="2026-08-21T00:00:00Z",
            )
            object_id = store.register(record)
            artifact_id = store.register_artifact(
                b"evidence",
                media_type="text/plain",
                source_ids=[object_id],
                provenance={"producer": "unit-test"},
            )
            store.projection_path.write_bytes(b"not-sqlite")
            store.rebuild_projection()
            self.assertEqual("inspect", store.get(object_id).objective)
            self.assertEqual(8, store.get(artifact_id).size)
            with closing(sqlite3.connect(store.projection_path)) as database:
                self.assertGreaterEqual(database.execute("select count(*) from events").fetchone()[0], 2)

    def test_object_store_tamper_is_detected(self) -> None:
        with EGCFStore(self.fixture.root) as store:
            record = IntentRecord(
                raw_request="inspect",
                raw_request_hash="abc",
                actor="user",
                objective="inspect",
                created_at="2026-08-21T00:00:00Z",
            )
            object_id = store.register(record)
            path = store.objects.path_for(object_id)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["payload"]["objective"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EGCFError):
                store.get(object_id)

    def test_all_universal_modifiers_parse_and_inherit_monotonically(self) -> None:
        parent = CommandContext.from_mapping(
            {
                "dry_run": True,
                "why": True,
                "scope": ["src/**"],
                "evidence": ["parent"],
                "approval": "policy",
                "risk": "L1",
                "rollback": "compensating",
                "budget": {"actions": 5, "retries": 2},
                "timeout": 60,
                "trace": True,
                "json": True,
                "graph": True,
                "record": True,
                "replay": "plan:sha256:abc",
                "strict": True,
                "simulate": True,
            }
        )
        child = CommandContext.from_mapping(
            {
                "scope": ["src/parser.py"],
                "evidence": ["child"],
                "approval": "human",
                "risk": "L2",
                "rollback": "exact",
                "budget": {"actions": 3, "retries": 1},
                "timeout": 30,
            }
        )
        effective = parent.inherit(child)
        self.assertEqual(["src/parser.py"], effective.scope)
        self.assertEqual(["parent", "child"], effective.evidence)
        self.assertEqual("human", effective.approval)
        self.assertEqual("L2", effective.risk)
        self.assertEqual("exact", effective.rollback)
        self.assertEqual(3, effective.budget.actions)
        self.assertEqual(1, effective.budget.retries)
        self.assertEqual(30, effective.timeout)
        self.assertTrue(all((effective.dry_run, effective.why, effective.trace, effective.json_output, effective.graph, effective.record, effective.strict, effective.simulate)))
        with self.assertRaises(CompilationError):
            parent.inherit(CommandContext(scope=["outside/**"]))

    def test_checked_in_command_catalog_matches_runtime_namespaces(self) -> None:
        repository_root = __import__("pathlib").Path(__file__).resolve().parents[1]
        checked_in = json.loads(
            (repository_root / "commands" / "v1" / "catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(command_catalog()["namespaces"], checked_in["namespaces"])


if __name__ == "__main__":
    unittest.main()
