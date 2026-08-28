import json
import os
import unittest
from unittest import mock

from ourd import OURDAgent
from ourd.errors import StateError
from ourd.persistence import EventStore, StateStore
from tests.helpers import RepoFixture, governance_args


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.authority = self.fixture.authority(allowed_paths=["README.md"])

    def tearDown(self) -> None:
        self.fixture.close()

    def test_restart_restores_governance(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
        with OURDAgent(self.fixture.root, authority_path=self.authority) as restarted:
            self.assertTrue(restarted.state.governance.established)
            self.assertEqual("Make one bounded change", restarted.state.governance.goal)

    def test_corrupt_projection_rebuilds_from_events(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
        state_path = self.fixture.root / ".ourd-agent" / "state.json"
        state_path.write_text("not-json", encoding="utf-8")
        with OURDAgent(self.fixture.root, authority_path=self.authority) as rebuilt:
            self.assertTrue(rebuilt.state.governance.established)

    def test_valid_json_projection_tamper_rebuilds_from_events(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
        state_path = self.fixture.root / ".ourd-agent" / "state.json"
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        payload["governance"]["goal"] = "tampered"
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        with OURDAgent(self.fixture.root, authority_path=self.authority) as rebuilt:
            self.assertEqual("Make one bounded change", rebuilt.state.governance.goal)

    def test_broken_event_chain_fails_closed(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority):
            pass
        event_path = self.fixture.root / ".ourd-agent" / "events.jsonl"
        events = event_path.read_text(encoding="utf-8").splitlines()
        payload = json.loads(events[-1])
        payload["previous_hash"] = "broken"
        events[-1] = json.dumps(payload)
        event_path.write_text("\n".join(events) + "\n", encoding="utf-8")
        with self.assertRaises(StateError):
            StateStore(self.fixture.root / ".ourd-agent")

    def test_second_writer_is_rejected(self) -> None:
        first = StateStore(self.fixture.root / ".ourd-agent")
        try:
            with self.assertRaises(StateError):
                StateStore(self.fixture.root / ".ourd-agent")
        finally:
            first.close()

    def test_sensitive_keys_are_redacted(self) -> None:
        store = EventStore(self.fixture.base / "events.jsonl")
        store.append(
            "test",
            {
                "api_key": "secret-value",
                "safe": "OPENAI_API_KEY=another-secret Bearer abcdef123456",
            },
        )
        text = (self.fixture.base / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("secret-value", text)
        self.assertNotIn("another-secret", text)
        self.assertNotIn("abcdef123456", text)
        self.assertIn("<redacted>", text)

    def test_configured_secret_patterns_are_redacted(self) -> None:
        store = EventStore(self.fixture.base / "custom-events.jsonl")
        with mock.patch.dict(os.environ, {"OURD_SECRET_PATTERNS": r"customer-[0-9]+"}):
            store.append("test", {"safe": "customer-48291"})
        text = (self.fixture.base / "custom-events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("customer-48291", text)
        self.assertIn("<redacted>", text)

    def test_events_include_run_action_and_transaction_lineage(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
            transaction = agent.prepare_write_file("README.md", "changed\n")
            action = agent.propose_eon_action(
                summary="Lineage write",
                operation="write_file",
                targets=["README.md"],
                preconditions=[],
                postconditions=[],
                preserve=[],
                evidence=[],
                risk="L1",
                transaction_id=transaction["transaction_id"],
                command_capabilities=[],
                commands=[],
                required_tests=[],
                expires_at="",
                use_limit=1,
            )["eon_action"]
            run_id = agent.run_id
        events = [
            json.loads(line)
            for line in (self.fixture.root / ".ourd-agent" / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertTrue(all({"run_id", "action_id", "transaction_id"} <= set(event) for event in events))
        self.assertTrue(any(event["run_id"] == run_id for event in events))
        self.assertTrue(any(event["action_id"] == action["action_id"] for event in events))
        self.assertTrue(
            any(event["transaction_id"] == transaction["transaction_id"] for event in events)
        )

    def test_prepared_transaction_is_detected_on_restart(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
            prepared = agent.prepare_write_file("README.md", "changed")
        with OURDAgent(
            self.fixture.root,
            authority_path=self.authority,
            recovery_transaction_id=prepared["transaction_id"],
        ) as restarted:
            self.assertEqual(prepared["transaction_id"], restarted.state.active_transaction_id)
            with self.assertRaises(Exception):
                restarted.prepare_write_file("README.md", "another")

    def test_applied_transaction_can_restart_and_rollback_with_original_authority(self) -> None:
        with OURDAgent(self.fixture.root, authority_path=self.authority) as agent:
            agent.establish_governance(**governance_args())
            transaction = agent.prepare_write_file("README.md", "changed\n")
            agent.propose_eon_action(
                summary="Recoverable write",
                operation="write_file",
                targets=["README.md"],
                preconditions=[],
                postconditions=[],
                preserve=[],
                evidence=["invariant", "boundary"],
                risk="L1",
                transaction_id=transaction["transaction_id"],
                command_capabilities=[],
                required_tests=[],
                expires_at="",
                use_limit=1,
            )
            first = agent.read_file("README.md", 1, 3)["evidence_id"]
            second = agent.search_text("value", "README.md", 10)["evidence_id"]
            agent.submit_evidence_gate(
                evidence_items=[
                    {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                    {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
                ],
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )
            agent.apply_transaction(transaction["transaction_id"])
        with OURDAgent(
            self.fixture.root,
            authority_path=self.authority,
            recovery_transaction_id=transaction["transaction_id"],
        ) as recovered:
            self.assertEqual(transaction["transaction_id"], recovered.state.active_transaction_id)
            result = recovered.rollback_transaction(transaction["transaction_id"])
            self.assertEqual("ROLLED_BACK", result["status"])
        self.assertIn("value = 1", (self.fixture.root / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
