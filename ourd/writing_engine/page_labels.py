from __future__ import annotations

from typing import Iterable, Tuple


def normalize_page_labels(labels: Iterable[str], page_count: int) -> Tuple[Tuple[int, str], ...]:
    values = list(labels)
    return tuple(
        (index, values[index].strip() if index < len(values) and values[index].strip() else str(index + 1))
        for index in range(max(0, int(page_count)))
    )


def display_label(page_label_map: Iterable[tuple[int, str]], physical_page_index: int) -> str:
    labels = dict(page_label_map)
    return labels.get(int(physical_page_index), str(int(physical_page_index) + 1))


__all__ = ["display_label", "normalize_page_labels"]
