from __future__ import annotations

import re
import unittest

from ourd_gui.visual_text import (
    DEFAULT_VISUAL_TEXT_THEME,
    VISUAL_TEXT_THEMES,
    parse_inline_spans,
    parse_visual_text,
    visual_theme,
    visual_theme_for_label,
    visual_theme_labels,
)


class VisualTextTests(unittest.TestCase):
    def test_theme_registry_contains_fifteen_unique_themes(self) -> None:
        self.assertEqual(15, len(VISUAL_TEXT_THEMES))
        self.assertEqual(15, len({theme.key for theme in VISUAL_TEXT_THEMES}))
        self.assertEqual(15, len(set(visual_theme_labels())))
        self.assertEqual(DEFAULT_VISUAL_TEXT_THEME, visual_theme("missing").key)
        for theme in VISUAL_TEXT_THEMES:
            self.assertEqual(theme, visual_theme(theme.key))
            self.assertEqual(theme, visual_theme_for_label(theme.label))

    def test_theme_colors_are_svg_compatible_hex_values(self) -> None:
        color_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for theme in VISUAL_TEXT_THEMES:
            for field_name, value in theme.__dict__.items():
                if field_name in {"key", "label"}:
                    continue
                self.assertRegex(value, color_pattern, f"{theme.key}.{field_name}")

    def test_inline_markup_is_projected_to_visual_spans(self) -> None:
        spans = parse_inline_spans(
            "Use **strong**, *emphasis*, `code`, and [evidence](artifact://evidence)."
        )
        styles = {span.style for span in spans}
        self.assertTrue({"strong", "emphasis", "inline_code", "link"} <= styles)
        link = next(span for span in spans if span.style == "link")
        self.assertEqual("evidence", link.text)
        self.assertEqual("artifact://evidence", link.target)

    def test_block_parser_handles_formal_markdown_shapes(self) -> None:
        blocks = parse_visual_text(
            "# Finding\n\n"
            "A **supported** statement.\n"
            "- first item\n"
            "  2. nested item\n"
            "> bounded limitation\n"
            "---\n"
            "```python\nprint('ok')\n```"
        )
        self.assertEqual(
            ["heading", "blank", "paragraph", "list", "list", "quote", "divider", "code"],
            [block.kind for block in blocks],
        )
        self.assertEqual("2.", blocks[4].marker)
        self.assertEqual(1, blocks[4].level)
        self.assertEqual("python", blocks[-1].language)
        self.assertEqual("print('ok')", blocks[-1].text)


if __name__ == "__main__":
    unittest.main()
