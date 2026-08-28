import unittest
from datetime import datetime, timedelta, timezone

from ourd import OURDAgent, PolicyError
from ourd.authority import load_authority
from ourd.workspace import Workspace
from tests.helpers import RepoFixture, governance_args


class AuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_default_authority_is_read_only(self) -> None:
        with OURDAgent(self.fixture.root) as agent:
            agent.establish_governance(**governance_args())
            with self.assertRaises(PolicyError):
                agent.prepare_write_file("README.md", "changed")

    def test_model_cannot_broaden_authority_scope(self) -> None:
        authority = self.fixture.authority(allowed_paths=["README.md"])
        with OURDAgent(self.fixture.root, authority_path=authority) as agent:
            with self.assertRaises(PolicyError):
                agent.establish_governance(**governance_args(["src/**"]))

    def test_mutation_authority_requires_exact_snapshot(self) -> None:
        authority = self.fixture.authority()
        self.fixture.write("new.txt", "drift")
        with self.assertRaises(PolicyError):
            load_authority(authority, Workspace(self.fixture.root))

    def test_expired_authority_is_rejected(self) -> None:
        expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        authority = self.fixture.authority(overrides={"expires_at": expired})
        with self.assertRaises(PolicyError):
            load_authority(authority, Workspace(self.fixture.root))

    def test_empty_model_scope_does_not_broaden_authority(self) -> None:
        authority = self.fixture.authority(allowed_paths=["README.md"])
        with OURDAgent(self.fixture.root, authority_path=authority) as agent:
            proposal = governance_args([])
            proposal["allowed_paths"] = []
            agent.establish_governance(**proposal)
            self.assertEqual(["README.md"], agent.state.authority.allowed_paths)
            self.assertEqual([], agent.state.governance.allowed_paths)

    def test_read_only_authority_rejects_mutation_capabilities(self) -> None:
        authority = self.fixture.authority(
            read_only=True,
            command_capabilities=[],
            allow_l1_auto_apply=False,
            allow_interactive_l2=False,
            max_automatic_risk="L0",
            overrides={"allow_yolo": True},
        )
        with self.assertRaises(PolicyError):
            load_authority(authority, Workspace(self.fixture.root))

    def test_yolo_requires_manifest_permission(self) -> None:
        authority = self.fixture.authority(allow_yolo=False)
        with OURDAgent(self.fixture.root, authority_path=authority, yolo=True) as agent:
            with self.assertRaises(PolicyError):
                agent.policy.require_auto_or_interactive_permission(
                    agent.state.authority, "L2", yolo=True
                )

    def test_max_automatic_risk_can_force_interactive_l1(self) -> None:
        authority = self.fixture.authority(
            allow_l1_auto_apply=True,
            max_automatic_risk="L0",
        )
        with OURDAgent(self.fixture.root, authority_path=authority) as agent:
            self.assertEqual(
                "interactive",
                agent.policy.require_auto_or_interactive_permission(
                    agent.state.authority, "L1", yolo=False
                ),
            )

    def test_retry_limit_outside_schema_range_is_rejected(self) -> None:
        authority = self.fixture.authority(overrides={"max_retries_per_action": 11})
        with self.assertRaises(PolicyError):
            load_authority(authority, Workspace(self.fixture.root))


if __name__ == "__main__":
    unittest.main()
