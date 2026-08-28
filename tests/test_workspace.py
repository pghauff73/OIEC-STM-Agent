import os
import unittest

from ourd import PolicyError, Workspace
from tests.helpers import RepoFixture


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.workspace = Workspace(self.fixture.root)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_escape_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.workspace.canonical("../escape")

    def test_absolute_path_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.workspace.canonical("/tmp/escape")

    def test_internal_state_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.workspace.canonical(".ourd-agent/state.json")

    def test_canonical_scope_blocks_lexical_traversal(self) -> None:
        self.fixture.write("secret.txt", "secret")
        with self.assertRaises(PolicyError):
            self.workspace.require_scope("src/../secret.txt", ["src/**"])

    def test_symlink_escape_is_blocked(self) -> None:
        outside = self.fixture.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        os.symlink(outside, self.fixture.root / "linked.txt")
        with self.assertRaises(PolicyError):
            self.workspace.canonical("linked.txt")

    def test_snapshot_ignores_internal_state(self) -> None:
        before = self.workspace.snapshot_hash()
        internal = self.fixture.root / ".ourd-agent"
        internal.mkdir()
        (internal / "state.json").write_text("{}", encoding="utf-8")
        self.assertEqual(before, self.workspace.snapshot_hash())

    def test_snapshot_ignores_packaging_artifacts(self) -> None:
        before = self.workspace.snapshot_hash()
        self.fixture.write("build/generated.py", "generated = True\n")
        self.fixture.write("project.egg-info/PKG-INFO", "generated\n")
        self.assertEqual(before, self.workspace.snapshot_hash())

    def test_snapshot_and_iteration_skip_symlinks_escaping_workspace(self) -> None:
        outside = self.fixture.base / "outside-again.txt"
        outside.write_text("secret", encoding="utf-8")
        (self.fixture.root / "outside-link.txt").symlink_to(outside)
        self.assertNotIn("outside-link.txt", self.workspace.snapshot())
        self.assertEqual([], [path for path in self.workspace.iter_files() if path.name == "outside-link.txt"])


if __name__ == "__main__":
    unittest.main()
