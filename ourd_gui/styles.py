from __future__ import annotations

from typing import Dict


STATUS_COLORS: Dict[str, tuple[str, str]] = {
    "selected": ("#0b5d3b", "#ffffff"),
    "qualified": ("#1f6f8b", "#ffffff"),
    "excluded": ("#7a3e00", "#ffffff"),
    "blocked": ("#7b1e1e", "#ffffff"),
    "failed": ("#7b1e1e", "#ffffff"),
    "warning": ("#806000", "#ffffff"),
    "running": ("#4257a6", "#ffffff"),
    "completed": ("#236b2c", "#ffffff"),
    "simulated": ("#6b4f9b", "#ffffff"),
    "stale": ("#7a3e00", "#ffffff"),
    "missing": ("#5a5a5a", "#ffffff"),
    "neutral": ("#e6e8eb", "#202124"),
}


def status_palette(status: str) -> tuple[str, str]:
    return STATUS_COLORS.get(status.lower(), STATUS_COLORS["neutral"])

