from __future__ import annotations

from collections.abc import Iterable


def incremental_window(
    identifiers: Iterable[str],
    *,
    limit: int,
    selected_id: str = "",
) -> tuple[str, ...]:
    ordered = tuple(dict.fromkeys(str(item) for item in identifiers if item))
    visible = list(ordered[: max(1, int(limit))])
    if selected_id and selected_id in ordered and selected_id not in visible:
        visible.append(selected_id)
    return tuple(visible)
