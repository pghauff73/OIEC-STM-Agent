from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualTextTheme:
    key: str
    label: str
    background: str
    surface: str
    alternate_surface: str
    foreground: str
    muted: str
    selection: str
    heading: str
    emphasis: str
    link: str
    quote: str
    code_background: str
    code_foreground: str
    divider: str
    user: str
    assistant: str
    system: str
    error: str


VISUAL_TEXT_THEMES: tuple[VisualTextTheme, ...] = (
    VisualTextTheme(
        "midnight-blueprint",
        "Midnight Blueprint",
        "#0b1020",
        "#121a2f",
        "#17223d",
        "#e8eefc",
        "#94a3bd",
        "#294a7a",
        "#8ec5ff",
        "#ffd580",
        "#7dd3fc",
        "#b5a7ff",
        "#080d18",
        "#d7e7ff",
        "#31415f",
        "#72b7ff",
        "#7bd88f",
        "#e0b76a",
        "#ff8585",
    ),
    VisualTextTheme(
        "graphite",
        "Graphite",
        "#17191c",
        "#22252a",
        "#2a2e34",
        "#f0f1f2",
        "#a6aab0",
        "#454b55",
        "#ffffff",
        "#f6c177",
        "#8bd5ca",
        "#c4a7e7",
        "#111315",
        "#eceff4",
        "#4a4f58",
        "#82aaff",
        "#a6e3a1",
        "#f9e2af",
        "#f38ba8",
    ),
    VisualTextTheme(
        "solarized-dark",
        "Solarized Dark",
        "#002b36",
        "#073642",
        "#0b3d49",
        "#eee8d5",
        "#93a1a1",
        "#2a5964",
        "#b58900",
        "#cb4b16",
        "#268bd2",
        "#6c71c4",
        "#001f27",
        "#fdf6e3",
        "#586e75",
        "#268bd2",
        "#859900",
        "#b58900",
        "#dc322f",
    ),
    VisualTextTheme(
        "solarized-light",
        "Solarized Light",
        "#fdf6e3",
        "#eee8d5",
        "#e5ddc8",
        "#073642",
        "#657b83",
        "#c7d2d5",
        "#8b5f00",
        "#b33a00",
        "#006f9f",
        "#5f56a5",
        "#e3dcc9",
        "#002b36",
        "#93a1a1",
        "#006f9f",
        "#557400",
        "#8b5f00",
        "#c62424",
    ),
    VisualTextTheme(
        "paper-ink",
        "Paper & Ink",
        "#f6f2e8",
        "#fffdf7",
        "#eee7d8",
        "#24211d",
        "#6e675d",
        "#c9d7e8",
        "#1f3f5b",
        "#7a3e00",
        "#155b8a",
        "#6f4b7e",
        "#e8e1d3",
        "#26231f",
        "#c8bda9",
        "#1d5f8a",
        "#2d6a4f",
        "#8a5a13",
        "#a12c2c",
    ),
    VisualTextTheme(
        "sepia-study",
        "Sepia Study",
        "#efe3c5",
        "#f8efd9",
        "#e6d5ae",
        "#3d3022",
        "#776550",
        "#cbb789",
        "#604020",
        "#8a4b21",
        "#315f78",
        "#73557e",
        "#dfcca2",
        "#33281d",
        "#b99e69",
        "#355f86",
        "#3f6b48",
        "#8a5d18",
        "#a1372e",
    ),
    VisualTextTheme(
        "ocean-depths",
        "Ocean Depths",
        "#061923",
        "#0b2734",
        "#103543",
        "#e3f6fb",
        "#91b6c0",
        "#17536a",
        "#6ee7f2",
        "#ffd166",
        "#55c2ff",
        "#b9a7ff",
        "#041118",
        "#d6f4ff",
        "#246070",
        "#4cc9f0",
        "#80ed99",
        "#ffd166",
        "#ff6b6b",
    ),
    VisualTextTheme(
        "forest-canopy",
        "Forest Canopy",
        "#0d1b16",
        "#172820",
        "#20352a",
        "#e8f3ea",
        "#9eb6a5",
        "#315b45",
        "#b7e4a8",
        "#f0c674",
        "#79c2a6",
        "#c5a3d8",
        "#09130f",
        "#d9f4df",
        "#3d634d",
        "#73b5ff",
        "#95d57a",
        "#e3bc69",
        "#ff8585",
    ),
    VisualTextTheme(
        "aurora",
        "Aurora",
        "#101426",
        "#191f38",
        "#232a49",
        "#f0f3ff",
        "#a8afd0",
        "#3a4778",
        "#8cf4d8",
        "#ffd37a",
        "#73d8ff",
        "#d9a7ff",
        "#0a0d1a",
        "#e9eeff",
        "#46517a",
        "#72d5ff",
        "#7fffd4",
        "#ffd479",
        "#ff7aa8",
    ),
    VisualTextTheme(
        "lavender-mist",
        "Lavender Mist",
        "#f3effa",
        "#ffffff",
        "#e9e0f5",
        "#2e2540",
        "#756986",
        "#d4c2ed",
        "#5f3b88",
        "#8b4f5e",
        "#4b65a7",
        "#7a4b8e",
        "#e5dcf0",
        "#322840",
        "#c6b4dc",
        "#406fb0",
        "#387a62",
        "#8a641f",
        "#b33a58",
    ),
    VisualTextTheme(
        "rose-quartz",
        "Rose Quartz",
        "#fff3f5",
        "#fffafb",
        "#f8e2e7",
        "#40272d",
        "#80636a",
        "#efc8d1",
        "#8c3f57",
        "#9a5a22",
        "#436fa3",
        "#82517e",
        "#f3dde2",
        "#3d272c",
        "#d9abb6",
        "#3c70a4",
        "#3d7c65",
        "#8b5b18",
        "#b52f4b",
    ),
    VisualTextTheme(
        "amber-terminal",
        "Amber Terminal",
        "#15120b",
        "#211b0f",
        "#2c2413",
        "#ffe9ad",
        "#b8a36c",
        "#594820",
        "#ffd166",
        "#ffb347",
        "#e6c15a",
        "#d8a7ff",
        "#0c0a06",
        "#ffe6a1",
        "#604d22",
        "#8fc7ff",
        "#9fe870",
        "#ffd166",
        "#ff7777",
    ),
    VisualTextTheme(
        "terminal-green",
        "Terminal Green",
        "#06110a",
        "#0a1c10",
        "#102718",
        "#d9ffe1",
        "#84b58e",
        "#1c5130",
        "#7cff9b",
        "#d8ff7a",
        "#66d9ef",
        "#b9a7ff",
        "#030805",
        "#caffd4",
        "#28613a",
        "#6db7ff",
        "#7cff9b",
        "#d8d477",
        "#ff7777",
    ),
    VisualTextTheme(
        "high-contrast-dark",
        "High Contrast Dark",
        "#000000",
        "#111111",
        "#1d1d1d",
        "#ffffff",
        "#c8c8c8",
        "#005fcc",
        "#ffffff",
        "#ffff00",
        "#00d7ff",
        "#ff9cff",
        "#000000",
        "#ffffff",
        "#808080",
        "#59a9ff",
        "#69f075",
        "#ffd75f",
        "#ff7070",
    ),
    VisualTextTheme(
        "high-contrast-light",
        "High Contrast Light",
        "#ffffff",
        "#f2f2f2",
        "#e3e3e3",
        "#000000",
        "#4a4a4a",
        "#a9c7ff",
        "#000000",
        "#7a2800",
        "#004f9f",
        "#6a237e",
        "#e7e7e7",
        "#000000",
        "#6b6b6b",
        "#005fcc",
        "#006b2e",
        "#765000",
        "#b00020",
    ),
)

DEFAULT_VISUAL_TEXT_THEME = "midnight-blueprint"

_THEMES_BY_KEY = {theme.key: theme for theme in VISUAL_TEXT_THEMES}
_THEMES_BY_LABEL = {theme.label: theme for theme in VISUAL_TEXT_THEMES}


def visual_theme_labels() -> tuple[str, ...]:
    return tuple(theme.label for theme in VISUAL_TEXT_THEMES)


def visual_theme(key: str) -> VisualTextTheme:
    return _THEMES_BY_KEY.get(key, _THEMES_BY_KEY[DEFAULT_VISUAL_TEXT_THEME])


def visual_theme_for_label(label: str) -> VisualTextTheme:
    return _THEMES_BY_LABEL.get(label, _THEMES_BY_KEY[DEFAULT_VISUAL_TEXT_THEME])


@dataclass(frozen=True)
class InlineSpan:
    text: str
    style: str = "body"
    target: str = ""


@dataclass(frozen=True)
class VisualTextBlock:
    kind: str
    spans: tuple[InlineSpan, ...] = ()
    text: str = ""
    marker: str = ""
    level: int = 0
    language: str = ""


_INLINE_PATTERN = re.compile(
    r"(`[^`\n]+`|\*\*[^*\n]+?\*\*|__[^_\n]+?__|"
    r"\[[^\]\n]+\]\([^\)\n]+\)|(?<!\*)\*[^*\n]+?\*(?!\*)|"
    r"(?<!_)_[^_\n]+?_(?!_))"
)
_FENCE_PATTERN = re.compile(r"^\s*```([A-Za-z0-9_+.-]*)\s*$")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_PATTERN = re.compile(r"^(\s*)[-+*]\s+(.+)$")
_ORDERED_PATTERN = re.compile(r"^(\s*)(\d+)[.)]\s+(.+)$")
_QUOTE_PATTERN = re.compile(r"^\s*>\s?(.*)$")
_DIVIDER_PATTERN = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def parse_inline_spans(text: str) -> tuple[InlineSpan, ...]:
    spans: list[InlineSpan] = []
    cursor = 0
    for match in _INLINE_PATTERN.finditer(text):
        if match.start() > cursor:
            spans.append(InlineSpan(text[cursor : match.start()]))
        token = match.group(0)
        if token.startswith("`"):
            spans.append(InlineSpan(token[1:-1], "inline_code"))
        elif token.startswith(("**", "__")):
            spans.append(InlineSpan(token[2:-2], "strong"))
        elif token.startswith("["):
            label, separator, target = token[1:].partition("](")
            if separator:
                spans.append(InlineSpan(label, "link", target[:-1]))
            else:
                spans.append(InlineSpan(token))
        else:
            spans.append(InlineSpan(token[1:-1], "emphasis"))
        cursor = match.end()
    if cursor < len(text):
        spans.append(InlineSpan(text[cursor:]))
    return tuple(spans) or (InlineSpan(""),)


def parse_visual_text(text: str) -> tuple[VisualTextBlock, ...]:
    blocks: list[VisualTextBlock] = []
    code_lines: list[str] = []
    code_language = ""
    in_code = False

    for line in text.splitlines():
        fence = _FENCE_PATTERN.match(line)
        if fence:
            if in_code:
                blocks.append(
                    VisualTextBlock(
                        kind="code",
                        text="\n".join(code_lines),
                        language=code_language,
                    )
                )
                code_lines = []
                code_language = ""
                in_code = False
            else:
                in_code = True
                code_language = fence.group(1)
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            blocks.append(VisualTextBlock(kind="blank"))
            continue
        if _DIVIDER_PATTERN.match(line):
            blocks.append(VisualTextBlock(kind="divider"))
            continue
        heading = _HEADING_PATTERN.match(line)
        if heading:
            blocks.append(
                VisualTextBlock(
                    kind="heading",
                    spans=parse_inline_spans(heading.group(2)),
                    level=len(heading.group(1)),
                )
            )
            continue
        quote = _QUOTE_PATTERN.match(line)
        if quote:
            blocks.append(
                VisualTextBlock(kind="quote", spans=parse_inline_spans(quote.group(1)))
            )
            continue
        ordered = _ORDERED_PATTERN.match(line)
        if ordered:
            blocks.append(
                VisualTextBlock(
                    kind="list",
                    spans=parse_inline_spans(ordered.group(3)),
                    marker=f"{ordered.group(2)}.",
                    level=min(len(ordered.group(1)) // 2, 4),
                )
            )
            continue
        bullet = _BULLET_PATTERN.match(line)
        if bullet:
            blocks.append(
                VisualTextBlock(
                    kind="list",
                    spans=parse_inline_spans(bullet.group(2)),
                    marker="•",
                    level=min(len(bullet.group(1)) // 2, 4),
                )
            )
            continue
        blocks.append(VisualTextBlock(kind="paragraph", spans=parse_inline_spans(line)))

    if in_code:
        blocks.append(
            VisualTextBlock(kind="code", text="\n".join(code_lines), language=code_language)
        )
    if not blocks and text:
        blocks.append(VisualTextBlock(kind="paragraph", spans=parse_inline_spans(text)))
    return tuple(blocks)


__all__ = [
    "DEFAULT_VISUAL_TEXT_THEME",
    "InlineSpan",
    "VISUAL_TEXT_THEMES",
    "VisualTextBlock",
    "VisualTextTheme",
    "parse_inline_spans",
    "parse_visual_text",
    "visual_theme",
    "visual_theme_for_label",
    "visual_theme_labels",
]
