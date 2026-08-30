import unittest

from ourd import OURDAgent
from ourd.errors import PolicyError
from tests.helpers import RepoFixture


class ReadToolTests(unittest.TestCase):
    def test_empty_file_read_returns_empty_content(self) -> None:
        fixture = RepoFixture()
        fixture.write("empty.txt", "")
        try:
            with OURDAgent(fixture.root) as agent:
                result = agent.read_file("empty.txt", 1, 20)
            self.assertTrue(result["ok"])
            self.assertEqual("", result["content"])
            self.assertEqual(0, result["end_line"])
        finally:
            fixture.close()

    def test_list_files_skips_escaping_symlink(self) -> None:
        fixture = RepoFixture()
        outside = fixture.base / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (fixture.root / "outside-link.txt").symlink_to(outside)
        try:
            with OURDAgent(fixture.root) as agent:
                result = agent.list_files(".", 2)
            self.assertNotIn("outside-link.txt", result["files"])
        finally:
            fixture.close()

    def test_list_files_supports_deterministic_bounded_pagination(self) -> None:
        fixture = RepoFixture()
        fixture.write("alpha.txt", "alpha\n")
        fixture.write("beta.txt", "beta\n")
        fixture.write("gamma.txt", "gamma\n")
        try:
            with OURDAgent(fixture.root) as agent:
                first = agent.list_files(".", 2, offset=0, max_results=2)
                second = agent.list_files(
                    ".",
                    2,
                    offset=first["next_offset"],
                    max_results=2,
                )

            self.assertEqual(["README.md", "alpha.txt"], first["files"])
            self.assertTrue(first["has_more"])
            self.assertEqual(2, first["next_offset"])
            self.assertEqual(["beta.txt", "gamma.txt"], second["files"])
            self.assertFalse(second["has_more"])
            self.assertIsNone(second["next_offset"])
            self.assertEqual(4, second["total_files"])
        finally:
            fixture.close()

    def test_list_files_rejects_invalid_loop_cursor(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root) as agent:
                with self.assertRaises(PolicyError):
                    agent.list_files(".", 2, offset=-1, max_results=20)
                with self.assertRaises(PolicyError):
                    agent.list_files(".", 2, offset=0, max_results=0)
        finally:
            fixture.close()

    def test_empty_discovery_root_targets_workspace_and_named_file_can_be_read(self) -> None:
        fixture = RepoFixture()
        fixture.write(
            "ourd/formal_writing.py",
            "class ArgumentTopology:\n    pass\n",
        )
        try:
            with OURDAgent(fixture.root) as agent:
                listing = agent.list_files("", 4)
                search = agent.search_text("ArgumentTopology", "", 20)
                direct = agent.read_file("ourd/formal_writing.py", 1, 20)

            self.assertIn("ourd/formal_writing.py", listing["files"])
            self.assertEqual(".", search["path"])
            self.assertEqual(20, search["max_results"])
            self.assertEqual("ourd/formal_writing.py", search["results"][0]["path"])
            self.assertTrue(direct["ok"])
            self.assertEqual("ourd/formal_writing.py", direct["path"])
            self.assertIn("ArgumentTopology", direct["content"])
        finally:
            fixture.close()

    def test_search_text_rejects_invalid_result_limit(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root) as agent:
                with self.assertRaises(PolicyError):
                    agent.search_text("value", ".", 0)
                with self.assertRaises(PolicyError):
                    agent.search_text("value", ".", 501)
        finally:
            fixture.close()

    def test_read_file_returns_monotonic_line_cursor(self) -> None:
        fixture = RepoFixture()
        fixture.write("loop.txt", "one\ntwo\nthree\nfour\nfive\n")
        try:
            with OURDAgent(fixture.root) as agent:
                first = agent.read_file("loop.txt", 1, 2)
                second = agent.read_file(
                    "loop.txt",
                    first["next_start_line"],
                    4,
                )
                final = agent.read_file(
                    "loop.txt",
                    second["next_start_line"],
                    6,
                )

            self.assertEqual(5, first["total_lines"])
            self.assertTrue(first["has_more"])
            self.assertEqual(3, first["next_start_line"])
            self.assertEqual(4, second["end_line"])
            self.assertEqual(5, second["next_start_line"])
            self.assertEqual(5, final["end_line"])
            self.assertFalse(final["has_more"])
            self.assertIsNone(final["next_start_line"])
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
