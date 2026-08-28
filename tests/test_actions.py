import unittest
from unittest import mock
import stat

from ourd import OURDAgent, PolicyError
from tests.helpers import RepoFixture, governance_args


class ActionTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.authority = self.fixture.authority(allowed_paths=["README.md"])
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args())

    def tearDown(self) -> None:
        self.agent.close()
        self.fixture.close()

    def _evidence(self) -> list[dict[str, object]]:
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.search_text("value", "README.md", 10)["evidence_id"]
        return [
            {"artifact_id": first, "category": "invariant", "satisfies": ["preserve heading"]},
            {"artifact_id": second, "category": "boundary", "satisfies": ["bounded replacement"]},
        ]

    def _prepare_action(self, content: str = "# Example\n\nvalue = 2\n", use_limit: int = 1):
        transaction = self.agent.prepare_write_file("README.md", content)
        action = self.agent.propose_eon_action(
            summary="Update one documented value",
            operation="write_file",
            targets=["README.md"],
            preconditions=["README exists"],
            postconditions=["value is updated"],
            preserve=["heading"],
            evidence=["preserve heading", "bounded replacement"],
            risk="L0",
            transaction_id=transaction["transaction_id"],
            command_capabilities=[],
            required_tests=[],
            expires_at="",
            use_limit=use_limit,
        )["eon_action"]
        return transaction, action

    def test_candidate_preparation_does_not_mutate_workspace(self) -> None:
        before = (self.fixture.root / "README.md").read_text(encoding="utf-8")
        transaction, _ = self._prepare_action()
        self.assertEqual("PREPARED", transaction["status"])
        self.assertEqual(before, (self.fixture.root / "README.md").read_text(encoding="utf-8"))

    def test_model_l0_write_becomes_l1(self) -> None:
        _, action = self._prepare_action()
        self.assertEqual("L0", action["model_risk"])
        self.assertEqual("L1", action["effective_risk"])

    def test_gate_requires_grounded_categories_and_requirements(self) -> None:
        self._prepare_action()
        result = self.agent.submit_evidence_gate(
            evidence_items=[],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        self.assertEqual("REQUEST_EVIDENCE", result["gate"]["verdict"])

    def test_apply_and_rollback_restore_exact_content(self) -> None:
        original = (self.fixture.root / "README.md").read_bytes()
        transaction, _ = self._prepare_action()
        gate = self.agent.submit_evidence_gate(
            evidence_items=self._evidence(),
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )["gate"]
        self.assertEqual("APPROVE", gate["verdict"])
        applied = self.agent.apply_transaction(transaction["transaction_id"])
        self.assertEqual("APPLIED", applied["status"])
        self.assertEqual(self.agent.state.pending_action.action_id, applied["action_id"])
        self.assertIn("rollback_manifest", applied)
        self.assertIn("postconditions", applied)
        self.assertIn("value = 2", (self.fixture.root / "README.md").read_text(encoding="utf-8"))
        rolled_back = self.agent.rollback_transaction(transaction["transaction_id"])
        self.assertEqual("ROLLED_BACK", rolled_back["status"])
        self.assertEqual(original, (self.fixture.root / "README.md").read_bytes())
        self.assertTrue(any(item.boundary == "rollback" for item in self.agent.state.collisions))

    def test_source_drift_blocks_apply(self) -> None:
        transaction, _ = self._prepare_action()
        self.agent.submit_evidence_gate(
            evidence_items=self._evidence(),
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        (self.fixture.root / "README.md").write_text("drift", encoding="utf-8")
        with self.assertRaises(PolicyError):
            self.agent.apply_transaction(transaction["transaction_id"])

    def test_source_drift_invalidates_gate_before_apply(self) -> None:
        self._prepare_action()
        evidence = self._evidence()
        self.fixture.write("drift.txt", "unexpected\n")
        with self.assertRaises(PolicyError):
            self.agent.submit_evidence_gate(
                evidence_items=evidence,
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )

    def test_limited_approval_enforces_use_count(self) -> None:
        transaction, _ = self._prepare_action(use_limit=2)
        gate = self.agent.submit_evidence_gate(
            evidence_items=self._evidence(),
            uncovered=["broader repository behavior"],
            proposed_verdict="APPROVE_WITH_LIMITS",
            limits={"targets": ["README.md"], "command_capabilities": [], "max_uses": 1},
        )["gate"]
        self.assertEqual("APPROVE_WITH_LIMITS", gate["verdict"])
        self.agent.apply_transaction(transaction["transaction_id"])
        with self.assertRaises(PolicyError):
            self.agent._enforce_gate_limits(
                self.agent.state.pending_action,
                self.agent.state.last_gate,
                targets=["README.md"],
            )

    def test_duplicate_evidence_cannot_fill_multiple_categories(self) -> None:
        self._prepare_action()
        evidence_id = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        with self.assertRaises(PolicyError):
            self.agent.submit_evidence_gate(
                evidence_items=[
                    {"artifact_id": evidence_id, "category": "invariant", "satisfies": ["preserve heading"]},
                    {"artifact_id": evidence_id, "category": "boundary", "satisfies": ["bounded replacement"]},
                ],
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )

    def test_expired_action_is_rejected(self) -> None:
        transaction = self.agent.prepare_write_file("README.md", "changed")
        self.agent.propose_eon_action(
            summary="Expired candidate",
            operation="write_file",
            targets=["README.md"],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=[],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=[],
            required_tests=[],
            expires_at="2000-01-01T00:00:00Z",
            use_limit=1,
        )
        with self.assertRaises(PolicyError):
            self.agent.submit_evidence_gate(
                evidence_items=[], uncovered=[], proposed_verdict="APPROVE", limits={}
            )

    def test_multi_file_mid_apply_failure_rolls_back_every_file(self) -> None:
        self.agent.close()
        self.fixture.write("src/a.txt", "a1\n")
        self.fixture.write("src/b.txt", "b1\n")
        self.authority = self.fixture.authority(allowed_paths=["src/**"])
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args(["src/**"]))
        transaction = self.agent.prepare_transaction(
            [
                {"type": "write", "path": "src/a.txt", "content": "a2\n", "old": "", "new": "", "count": 1},
                {"type": "write", "path": "src/b.txt", "content": "b2\n", "old": "", "new": "", "count": 1},
            ]
        )
        self.agent.propose_eon_action(
            summary="Update two bounded files",
            operation="write_file",
            targets=["src/a.txt", "src/b.txt"],
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
        first = self.agent.read_file("src/a.txt", 1, 2)["evidence_id"]
        second = self.agent.read_file("src/b.txt", 1, 2)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        real_replace = __import__("os").replace
        calls = {"count": 0}

        def fail_second(source, destination):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated second-file failure")
            return real_replace(source, destination)

        with mock.patch("ourd.transactions.os.replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.agent.apply_transaction(transaction["transaction_id"])
        self.assertEqual("a1\n", (self.fixture.root / "src/a.txt").read_text(encoding="utf-8"))
        self.assertEqual("b1\n", (self.fixture.root / "src/b.txt").read_text(encoding="utf-8"))

    def test_prepared_transaction_can_be_discarded(self) -> None:
        transaction, _ = self._prepare_action()
        result = self.agent.rollback_transaction(transaction["transaction_id"])
        self.assertEqual("DISCARDED", result["status"])

    def test_same_summary_different_candidate_changes_action_id(self) -> None:
        first_transaction, first_action = self._prepare_action("first\n")
        self.agent.rollback_transaction(first_transaction["transaction_id"])
        second_transaction, second_action = self._prepare_action("second\n")
        self.assertNotEqual(first_action["candidate_hash"], second_action["candidate_hash"])
        self.assertNotEqual(first_action["action_id"], second_action["action_id"])

    def test_full_approval_with_uncovered_evidence_is_downgraded(self) -> None:
        self._prepare_action()
        gate = self.agent.submit_evidence_gate(
            evidence_items=self._evidence(),
            uncovered=["unknown behavior"],
            proposed_verdict="APPROVE",
            limits={},
        )["gate"]
        self.assertEqual("REQUEST_EVIDENCE", gate["verdict"])

    def test_rollback_restores_file_mode(self) -> None:
        target = self.fixture.root / "README.md"
        target.chmod(0o640)
        self.agent.close()
        self.authority = self.fixture.authority(allowed_paths=["README.md"])
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args())
        transaction, _ = self._prepare_action()
        self.agent.submit_evidence_gate(
            evidence_items=self._evidence(), uncovered=[], proposed_verdict="APPROVE", limits={}
        )
        self.agent.apply_transaction(transaction["transaction_id"])
        self.agent.rollback_transaction(transaction["transaction_id"])
        self.assertEqual(0o640, stat.S_IMODE(target.stat().st_mode))

    def test_mandatory_command_evidence_finalizes_transaction(self) -> None:
        self.agent.close()
        command = "python3 -m unittest discover -s tests -v"
        self.fixture.write(
            "tests/test_sample.py",
            "import unittest\n\nclass Sample(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        )
        self.authority = self.fixture.authority(
            allowed_paths=["README.md", "tests/**"],
            command_capabilities=["python.unittest"],
            mandatory_tests=[command],
        )
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args(["README.md", "tests/**"]))
        transaction = self.agent.prepare_write_file("README.md", "# Example\n\nvalue = 3\n")
        self.agent.propose_eon_action(
            summary="Update value and verify",
            operation="write_file",
            targets=["README.md"],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=["invariant", "boundary"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=["python.unittest"],
            required_tests=[command],
            expires_at="",
            use_limit=2,
        )
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.read_file("tests/test_sample.py", 1, 20)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        self.agent.apply_transaction(transaction["transaction_id"])
        command_result = self.agent.run_command(command)
        self.assertTrue(command_result["ok"])
        output_artifact = self.agent.state_dir / command_result["output_artifact"]
        self.assertTrue(output_artifact.is_file())
        self.assertIn(command, output_artifact.read_text(encoding="utf-8"))
        finalized = self.agent.finalize_transaction(
            transaction["transaction_id"], [command_result["evidence_id"]]
        )
        self.assertEqual("VERIFIED", finalized["status"])

    def test_candidate_artifact_tamper_blocks_apply(self) -> None:
        transaction, _ = self._prepare_action()
        self.agent.submit_evidence_gate(
            evidence_items=self._evidence(), uncovered=[], proposed_verdict="APPROVE", limits={}
        )
        record = self.agent.state.transactions[transaction["transaction_id"]]
        candidate = self.agent.state_dir / record.candidate_files["README.md"]
        candidate.write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(PolicyError):
            self.agent.apply_transaction(transaction["transaction_id"])
        self.assertIn("value = 1", (self.fixture.root / "README.md").read_text(encoding="utf-8"))

    def test_evidence_cannot_be_reused_for_another_action(self) -> None:
        first_transaction, _ = self._prepare_action("first\n")
        old_evidence = self._evidence()
        self.agent.rollback_transaction(first_transaction["transaction_id"])
        self._prepare_action("second\n")
        with self.assertRaises(PolicyError):
            self.agent.submit_evidence_gate(
                evidence_items=old_evidence,
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )

    def test_new_file_rollback_restores_nonexistence(self) -> None:
        self.agent.close()
        self.authority = self.fixture.authority(allowed_paths=["README.md", "new.txt"])
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args(["README.md", "new.txt"]))
        transaction = self.agent.prepare_write_file("new.txt", "created\n")
        self.agent.propose_eon_action(
            summary="Create bounded file",
            operation="write_file",
            targets=["new.txt"],
            preconditions=[],
            postconditions=["new file exists"],
            preserve=[],
            evidence=["invariant", "boundary"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=[],
            commands=[],
            required_tests=[],
            expires_at="",
            use_limit=1,
        )
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.search_text("value", "README.md", 10)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        self.agent.apply_transaction(transaction["transaction_id"])
        self.assertTrue((self.fixture.root / "new.txt").exists())
        self.agent.rollback_transaction(transaction["transaction_id"])
        self.assertFalse((self.fixture.root / "new.txt").exists())

    def test_l2_human_denial_leaves_workspace_unchanged(self) -> None:
        original = (self.fixture.root / "README.md").read_bytes()
        transaction = self.agent.prepare_write_file("README.md", "refactored\n")
        self.agent.propose_eon_action(
            summary="Refactor architecture",
            operation="write_file",
            targets=["README.md"],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=["invariant", "boundary", "counterexample"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=[],
            commands=[],
            required_tests=[],
            expires_at="",
            use_limit=1,
        )
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.search_text("value", "README.md", 10)["evidence_id"]
        third = self.agent.list_files(".", 2)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
                {"artifact_id": third, "category": "counterexample", "satisfies": ["counterexample"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        with mock.patch("builtins.print"), mock.patch(
            "builtins.input", return_value="n"
        ), self.assertRaises(PolicyError):
            self.agent.apply_transaction(transaction["transaction_id"])
        self.assertEqual(original, (self.fixture.root / "README.md").read_bytes())

    def test_altered_command_arguments_are_not_authorized(self) -> None:
        self.agent.close()
        approved = "python3 -m unittest discover -s tests -v"
        altered = "python3 -m unittest discover -s tests -q"
        self.fixture.write(
            "tests/test_sample.py",
            "import unittest\n\nclass Sample(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        )
        self.authority = self.fixture.authority(
            allowed_paths=["README.md", "tests/**"],
            command_capabilities=["python.unittest"],
        )
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args(["README.md", "tests/**"]))
        transaction = self.agent.prepare_write_file("README.md", "changed\n")
        self.agent.propose_eon_action(
            summary="Change and verify exact argv",
            operation="write_file",
            targets=["README.md"],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=["invariant", "boundary"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=["python.unittest"],
            commands=[approved],
            required_tests=[],
            expires_at="",
            use_limit=2,
        )
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.search_text("value", "README.md", 10)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        self.agent.apply_transaction(transaction["transaction_id"])
        with self.assertRaises(PolicyError):
            self.agent.run_command(altered)

    def test_post_apply_drift_blocks_verification_command(self) -> None:
        self.agent.close()
        command = "python3 -m unittest discover -s tests -v"
        self.fixture.write(
            "tests/test_sample.py",
            "import unittest\n\nclass Sample(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        )
        self.authority = self.fixture.authority(
            allowed_paths=["README.md", "tests/**"],
            command_capabilities=["python.unittest"],
        )
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args(["README.md", "tests/**"]))
        transaction = self.agent.prepare_write_file("README.md", "changed\n")
        self.agent.propose_eon_action(
            summary="Change and verify",
            operation="write_file",
            targets=["README.md"],
            preconditions=[],
            postconditions=[],
            preserve=[],
            evidence=["invariant", "boundary"],
            risk="L1",
            transaction_id=transaction["transaction_id"],
            command_capabilities=["python.unittest"],
            commands=[command],
            required_tests=[command],
            expires_at="",
            use_limit=2,
        )
        first = self.agent.read_file("README.md", 1, 3)["evidence_id"]
        second = self.agent.search_text("value", "README.md", 10)["evidence_id"]
        self.agent.submit_evidence_gate(
            evidence_items=[
                {"artifact_id": first, "category": "invariant", "satisfies": ["invariant"]},
                {"artifact_id": second, "category": "boundary", "satisfies": ["boundary"]},
            ],
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )
        self.agent.apply_transaction(transaction["transaction_id"])
        self.fixture.write("tests/drift.txt", "unexpected\n")
        with self.assertRaises(PolicyError):
            self.agent.run_command(command)

    def test_authority_mandatory_evidence_cannot_be_omitted(self) -> None:
        self.agent.close()
        self.authority = self.fixture.authority(
            allowed_paths=["README.md"],
            mandatory_evidence=["critical invariant"],
        )
        self.agent = OURDAgent(self.fixture.root, authority_path=self.authority)
        self.agent.establish_governance(**governance_args())
        _, action = self._prepare_action()
        self.assertIn("critical invariant", action["evidence"])
        gate = self.agent.submit_evidence_gate(
            evidence_items=self._evidence(),
            uncovered=[],
            proposed_verdict="APPROVE",
            limits={},
        )["gate"]
        self.assertEqual("REQUEST_EVIDENCE", gate["verdict"])
        self.assertIn("critical invariant", gate["reason"])

    def test_changed_gate_allows_one_retry_then_authority_cap_blocks(self) -> None:
        transaction, _ = self._prepare_action()
        self.agent.submit_evidence_gate(
            evidence_items=self._evidence(), uncovered=[], proposed_verdict="APPROVE", limits={}
        )
        with mock.patch.object(self.agent.transactions, "apply", side_effect=OSError("fail")):
            first = self.agent.dispatch(
                "apply_transaction", {"transaction_id": transaction["transaction_id"]}
            )
            self.assertFalse(first["ok"])
            self.agent.submit_evidence_gate(
                evidence_items=self._evidence(),
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )
            second = self.agent.dispatch(
                "apply_transaction", {"transaction_id": transaction["transaction_id"]}
            )
            self.assertFalse(second["ok"])
            self.agent.submit_evidence_gate(
                evidence_items=self._evidence(),
                uncovered=[],
                proposed_verdict="APPROVE",
                limits={},
            )
            third = self.agent.dispatch(
                "apply_transaction", {"transaction_id": transaction["transaction_id"]}
            )
        self.assertFalse(third["ok"])
        self.assertIn("retry limit", third["error"])
        with self.assertRaises(PolicyError):
            self.agent.prepare_write_file("README.md", "stale authority")


if __name__ == "__main__":
    unittest.main()
