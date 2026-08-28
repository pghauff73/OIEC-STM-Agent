from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Number
from typing import Any, Iterable, Mapping

from ourd.egcf.models import CommandInvocation, ExecutionRecord, SelectionDecision

from .events import AgentEvent
from .read_models import ReadOnlyEGCFRepository
from .state import GuiState, GuiTask, reduce_event


def state_at(events: Iterable[AgentEvent], cursor: int) -> GuiState:
    state = GuiState()
    if cursor < 0:
        return state
    for index, event in enumerate(events):
        if index > cursor:
            break
        state = reduce_event(state, event)
    return state


def _paths(value: Any) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"path", "file", "filename"} and isinstance(item, str):
                paths.add(item)
            elif key in {"paths", "files", "targets", "changed_files"} and isinstance(item, list):
                paths.update(str(entry) for entry in item if isinstance(entry, str))
            else:
                paths.update(_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.update(_paths(item))
    return paths


def _numeric_usage(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, Number):
        return float(value)
    if isinstance(value, Mapping):
        return sum(_numeric_usage(item) for item in value.values())
    if isinstance(value, list):
        return sum(_numeric_usage(item) for item in value)
    return 0.0


@dataclass(frozen=True)
class TaskRunSummary:
    task_id: str
    title: str
    status: str
    command_ids: tuple[str, ...]
    selected_algorithms: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    files_changed: tuple[str, ...]
    execution_ids: tuple[str, ...]
    failure_ids: tuple[str, ...]
    approval_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    total_usage: float
    duration_seconds: float | None
    cost_micros: float | None
    execution_records_observed: int


def summarize_task(
    repository: ReadOnlyEGCFRepository,
    task: GuiTask,
) -> TaskRunSummary:
    commands: list[str] = []
    algorithms: list[str] = []
    files: set[str] = set()
    total_usage = 0.0
    duration_seconds = 0.0
    cost_micros = 0.0
    duration_observed = False
    cost_observed = False
    execution_records_observed = 0
    for identifier in task.invocation_ids:
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            continue
        if isinstance(record, CommandInvocation):
            commands.append(record.command_id)
    for identifier in task.selection_ids:
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            continue
        if isinstance(record, SelectionDecision):
            algorithms.append(record.selected_algorithm_id)
    for identifier in task.execution_ids:
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            continue
        if isinstance(record, ExecutionRecord):
            execution_records_observed += 1
            files.update(_paths(record.output))
            total_usage += _numeric_usage(record.usage)
            if isinstance(record.usage.get("wall_seconds"), Number):
                duration_seconds += float(record.usage["wall_seconds"])
                duration_observed = True
            if isinstance(record.usage.get("cost_micros"), Number):
                cost_micros += float(record.usage["cost_micros"])
                cost_observed = True
    files.update(_paths(task.last_result))
    return TaskRunSummary(
        task_id=task.task_id,
        title=task.title,
        status=task.status,
        command_ids=tuple(dict.fromkeys(commands)),
        selected_algorithms=tuple(dict.fromkeys(algorithms)),
        evidence_ids=task.evidence_ids,
        files_changed=tuple(sorted(files)),
        execution_ids=task.execution_ids,
        failure_ids=task.failure_ids,
        approval_ids=task.approval_ids,
        artifact_ids=task.artifact_ids,
        total_usage=total_usage,
        duration_seconds=duration_seconds if duration_observed else None,
        cost_micros=cost_micros if cost_observed else None,
        execution_records_observed=execution_records_observed,
    )


def _compare_optional(left: float | None, right: float | None) -> dict[str, Any]:
    if left is None and right is None:
        return {"state": "missing_both", "delta": None}
    if left is None:
        return {"state": "missing_a", "delta": None}
    if right is None:
        return {"state": "missing_b", "delta": None}
    return {
        "state": "equal" if left == right else "different",
        "delta": right - left,
    }


def compare_tasks(
    repository: ReadOnlyEGCFRepository,
    left: GuiTask,
    right: GuiTask,
) -> dict[str, Any]:
    left_summary = summarize_task(repository, left)
    right_summary = summarize_task(repository, right)
    return {
        "run_a": asdict(left_summary),
        "run_b": asdict(right_summary),
        "differences": {
            "algorithms_only_a": sorted(
                set(left_summary.selected_algorithms) - set(right_summary.selected_algorithms)
            ),
            "algorithms_only_b": sorted(
                set(right_summary.selected_algorithms) - set(left_summary.selected_algorithms)
            ),
            "evidence_only_a": sorted(set(left_summary.evidence_ids) - set(right_summary.evidence_ids)),
            "evidence_only_b": sorted(set(right_summary.evidence_ids) - set(left_summary.evidence_ids)),
            "files_only_a": sorted(set(left_summary.files_changed) - set(right_summary.files_changed)),
            "files_only_b": sorted(set(right_summary.files_changed) - set(left_summary.files_changed)),
            "failure_count_delta": len(right_summary.failure_ids) - len(left_summary.failure_ids),
            "approval_count_delta": len(right_summary.approval_ids) - len(left_summary.approval_ids),
            "usage_delta": right_summary.total_usage - left_summary.total_usage,
            "duration": _compare_optional(
                left_summary.duration_seconds,
                right_summary.duration_seconds,
            ),
            "cost": _compare_optional(
                left_summary.cost_micros,
                right_summary.cost_micros,
            ),
            "status_changed": left_summary.status != right_summary.status,
            "data_availability": {
                "run_a_has_execution_records": left_summary.execution_records_observed > 0,
                "run_b_has_execution_records": right_summary.execution_records_observed > 0,
            },
        },
    }
