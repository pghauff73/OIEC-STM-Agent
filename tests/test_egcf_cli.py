from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest

from ourd.egcf.cli import build_parser, main
from tests.helpers import RepoFixture


class EGCFCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_parser_exposes_every_universal_modifier(self) -> None:
        args = build_parser().parse_args(
            [
                "capability",
                "list",
                "--dry-run",
                "--why",
                "--scope",
                "src/**",
                "--evidence",
                "evidence:sha256:abc",
                "--approval",
                "human",
                "--risk",
                "L2",
                "--rollback",
                "exact",
                "--budget",
                '{"actions": 2}',
                "--timeout",
                "10",
                "--trace",
                "--json",
                "--graph",
                "--record",
                "--replay",
                "execution-plan:sha256:abc",
                "--strict",
                "--simulate",
            ]
        )
        for field in (
            "dry_run",
            "why",
            "trace",
            "json_output",
            "graph",
            "record",
            "strict",
            "simulate",
        ):
            self.assertTrue(getattr(args, field))
        self.assertEqual(["src/**"], args.scope)
        self.assertEqual("human", args.approval)
        self.assertEqual("exact", args.rollback)

    def test_dry_run_emits_one_typed_plan_with_all_projections(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = main(
                [
                    "capability",
                    "list",
                    "--repo",
                    str(self.fixture.root),
                    "--dry-run",
                    "--why",
                    "--json",
                    "--graph",
                    "--trace",
                    "--record",
                ]
            )
        self.assertEqual(0, returncode, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual("COMPILED", payload["status"])
        self.assertTrue(payload["compiled_workflow_id"].startswith("compiled-workflow:sha256:"))
        self.assertTrue(payload["execution_plan_id"].startswith("execution-plan:sha256:"))
        self.assertEqual(payload["graph_hash"], payload["trace"]["plan"]["graph_hash"])
        self.assertEqual([], payload["graph"]["nodes"][0]["depends_on"])
        self.assertIn("why", payload)
        self.assertIn("record", payload)

    def test_snapshot_and_projection_rebuild_are_machine_readable(self) -> None:
        for arguments, expected_key in (
            (["--snapshot"], "source_snapshot_hash"),
            (["--rebuild-projection"], "rebuilt"),
        ):
            with self.subTest(arguments=arguments):
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    returncode = main(["--repo", str(self.fixture.root), *arguments])
                self.assertEqual(0, returncode, stderr.getvalue())
                self.assertIn(expected_key, json.loads(stdout.getvalue()))


if __name__ == "__main__":
    unittest.main()
