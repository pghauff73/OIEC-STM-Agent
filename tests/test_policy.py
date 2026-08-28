import unittest
import os
import subprocess
from unittest import mock

from ourd import OURDAgent, PolicyError, Workspace
from ourd.models import AuthorityManifest
from ourd.policy import PolicyEngine
from tests.helpers import RepoFixture


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()
        self.workspace = Workspace(self.fixture.root)
        self.policy = PolicyEngine()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_file_write_has_l1_floor(self) -> None:
        self.assertEqual(
            "L1",
            self.policy.effective_risk("L0", "write_file", "small edit", ["README.md"], []),
        )

    def test_structural_change_has_l2_floor(self) -> None:
        self.assertEqual(
            "L2",
            self.policy.effective_risk(
                "L0", "write_file", "refactor architecture", ["src/a.py"], []
            ),
        )

    def test_python_c_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.classify_command("python3 -c 'open(\"x\",\"w\").write(\"x\")'", self.workspace)

    def test_sed_in_place_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.classify_command("sed -i s/a/b/ README.md", self.workspace)

    def test_find_delete_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.classify_command("find . -delete", self.workspace)

    def test_git_mutation_is_blocked(self) -> None:
        for command in ("git add README.md", "git restore README.md", "git push"):
            with self.subTest(command=command), self.assertRaises(PolicyError):
                self.policy.classify_command(command, self.workspace)

    def test_unittest_capability_is_exact(self) -> None:
        decision = self.policy.classify_command(
            "python3 -m unittest discover -s tests -v", self.workspace
        )
        self.assertEqual("python.unittest", decision.capability)
        self.assertEqual("L1", decision.minimum_risk)

    def test_shell_tokens_environment_assignments_and_absolute_executables_are_blocked(self) -> None:
        commands = (
            "python3 -m unittest tests.test_sample ; touch escaped",
            "TOKEN=value python3 -m unittest tests.test_sample",
            "/usr/bin/python3 -m unittest tests.test_sample",
        )
        for command in commands:
            with self.subTest(command=command), self.assertRaises(PolicyError):
                self.policy.classify_command(command, self.workspace)

    def test_compiler_output_and_unknown_flags_are_blocked(self) -> None:
        self.fixture.write("src/a.cpp", "int main() {}\n")
        for command in (
            "g++ -fsyntax-only -o outside.o src/a.cpp",
            "g++ -fsyntax-only -fplugin=plugin.so src/a.cpp",
            "g++ -fsyntax-only @args.txt",
        ):
            with self.subTest(command=command), self.assertRaises(PolicyError):
                self.policy.classify_command(command, self.workspace)

    def test_command_paths_must_remain_inside_authority_scope(self) -> None:
        self.fixture.write("secrets/private.py", "value = 1\n")
        decision = self.policy.classify_command(
            "python3 -m py_compile secrets/private.py", self.workspace
        )
        authority = AuthorityManifest(
            allowed_paths=["README.md", "tests/**"],
            forbidden_paths=["secrets/**"],
            command_capabilities=["python.py_compile"],
            read_only=False,
        )
        with self.assertRaises(PolicyError):
            self.policy.require_command_scope(decision, authority, self.workspace)

    def test_child_environment_is_sanitized_and_commands_use_argv_without_shell(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "secret", "UNRELATED_SECRET": "hidden"},
        ):
            environment = self.workspace.safe_child_environment()
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("UNRELATED_SECRET", environment)
        completed = subprocess.CompletedProcess(["git", "status", "--short"], 0, "", "")
        with OURDAgent(self.fixture.root) as agent, mock.patch(
            "ourd.agent.subprocess.run", return_value=completed
        ) as run:
            agent.git_status()
        argv = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIsInstance(argv, list)
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])


if __name__ == "__main__":
    unittest.main()
