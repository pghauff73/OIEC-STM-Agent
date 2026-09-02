from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ourd.authority import save_authority, scoped_write_authority
from ourd.formal_writing_cli import _prepare_governed_write, build_parser, main
from ourd.workspace import Workspace


class FormalWritingCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "source.md").write_text(
            "# Source\n\nEvidence supports a qualified conclusion.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_parser_exposes_all_command_groups_and_revision_input(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "revise",
                "--workspace",
                str(self.root),
                "--source",
                "source.md",
                "--draft",
                "prior.md",
                "--task",
                "Revise the argument.",
            ]
        )
        self.assertEqual("revise", args.command)
        self.assertEqual(["source.md"], args.source)
        self.assertEqual(["prior.md"], args.draft)

    def test_read_only_command_returns_signed_reference_projection(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(
                [
                    "locate",
                    "--workspace",
                    str(self.root),
                    "--source",
                    "source.md",
                    "--task",
                    "qualified conclusion evidence",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["references"])
        self.assertEqual("VERIFIED", payload["references"][0]["verification_status"])
        self.assertTrue(payload["request"]["request_signature"])

    def test_governed_write_prepares_but_does_not_apply(self) -> None:
        workspace = Workspace(self.root)
        manifest = scoped_write_authority(
            workspace,
            allowed_paths=["essay.md"],
            goal="Prepare an exact formal-writing candidate",
            operator="test-user",
        )
        with tempfile.TemporaryDirectory() as authority_dir:
            authority_path = Path(authority_dir) / "authority.json"
            save_authority(authority_path, manifest)
            result = _prepare_governed_write(
                self.root,
                authority_path,
                "a" * 64,
                "Prepare an exact formal-writing candidate",
                ("essay.md",),
                "# Candidate\n\nGrounded text.\n",
            )
        self.assertEqual(
            "PREPARED_PENDING_EVIDENCE_AND_HUMAN_APPROVAL",
            result["status"],
        )
        self.assertEqual("PREPARED", result["transaction"]["status"])
        self.assertFalse((self.root / "essay.md").exists())


if __name__ == "__main__":
    unittest.main()
