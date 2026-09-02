from __future__ import annotations

from typing import Callable, TypeAlias


ProgressSink: TypeAlias = Callable[[str], None]
CancellationCheck: TypeAlias = Callable[[], bool]


class FormalWritingCancelledError(RuntimeError):
    pass


def require_not_cancelled(cancellation_check: CancellationCheck | None) -> None:
    if cancellation_check is not None and cancellation_check():
        raise FormalWritingCancelledError("formal-writing operation cancelled")


def report_progress(progress_sink: ProgressSink | None, phase: str) -> None:
    if progress_sink is not None:
        progress_sink(phase)


__all__ = [
    "CancellationCheck",
    "FormalWritingCancelledError",
    "ProgressSink",
    "report_progress",
    "require_not_cancelled",
]
