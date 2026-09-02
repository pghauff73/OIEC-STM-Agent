from __future__ import annotations

import unittest

from ourd.interaction import parse_slash_command


class SlashCommandTests(unittest.TestCase):
    def test_parses_arguments_and_options_deterministically(self) -> None:
        command = parse_slash_command('/attach "docs/my file.md" --mode=read --trace')
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual("attach", command.name)
        self.assertEqual(("docs/my file.md",), command.arguments)
        self.assertEqual((("mode", "read"), ("trace", "true")), command.options)
        self.assertFalse(command.privileged)

    def test_non_slash_text_returns_none(self) -> None:
        self.assertIsNone(parse_slash_command("inspect parser"))

    def test_unknown_command_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown ICPI slash command"):
            parse_slash_command("/shell")

    def test_shell_metacharacters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "metacharacters"):
            parse_slash_command("/status | sh")

    def test_duplicate_options_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_slash_command("/files --format json --format text")

    def test_detach_requires_paths_or_all(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires path"):
            parse_slash_command("/detach")
        command = parse_slash_command("/detach --all")
        assert command is not None
        self.assertEqual((("all", "true"),), command.options)

    def test_detach_all_cannot_mix_paths_or_unknown_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            parse_slash_command("/detach README.md --all")
        with self.assertRaisesRegex(ValueError, "does not accept"):
            parse_slash_command("/detach --force")

    def test_context_refresh_is_explicit_and_strict(self) -> None:
        argument = parse_slash_command("/context refresh")
        option = parse_slash_command("/context --refresh")
        assert argument is not None and option is not None
        self.assertEqual(("refresh",), argument.arguments)
        self.assertEqual((("refresh", "true"),), option.options)
        with self.assertRaisesRegex(ValueError, "accepts only"):
            parse_slash_command("/context rebuild")
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            parse_slash_command("/context refresh --refresh")
        with self.assertRaisesRegex(ValueError, "does not accept"):
            parse_slash_command("/context --force")


if __name__ == "__main__":
    unittest.main()
