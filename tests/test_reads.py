import unittest

from ourd import OURDAgent
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


if __name__ == "__main__":
    unittest.main()
