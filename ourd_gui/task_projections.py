from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .state import GuiTask


def semantic_outputs(value: Any) -> tuple[Mapping[str, Any], ...]:
    outputs: list[Mapping[str, Any]] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            if isinstance(item.get("command_id"), str) and isinstance(item.get("result"), Mapping):
                outputs.append(dict(item["result"]))
            for key in ("outputs", "output"):
                child = item.get(key)
                if isinstance(child, list):
                    for entry in child:
                        visit(entry)
                elif isinstance(child, Mapping):
                    visit(child)
        elif isinstance(item, list):
            for entry in item:
                visit(entry)

    visit(value)
    return tuple(outputs)


@dataclass(frozen=True)
class DomainGraphProjection:
    nodes: tuple[Mapping[str, Any], ...]
    edges: tuple[Mapping[str, Any], ...]
    source: str
    canonical_relationships: bool


def _node_identifier(item: Any, index: int) -> str:
    if isinstance(item, Mapping):
        return str(item.get("id") or item.get("object_id") or item.get("name") or f"node-{index}")
    return str(item)


def domain_graph_for_task(task: GuiTask) -> DomainGraphProjection:
    for output in reversed(semantic_outputs(task.last_result)):
        nodes = output.get("nodes")
        edges = output.get("edges")
        if isinstance(nodes, list) and isinstance(edges, list):
            normalized_nodes = tuple(
                dict(item) if isinstance(item, Mapping) else {"id": str(item), "label": str(item)}
                for item in nodes
            )
            normalized_edges = tuple(
                dict(item)
                for item in edges
                if isinstance(item, Mapping) and "from" in item and "to" in item
            )
            return DomainGraphProjection(
                nodes=normalized_nodes,
                edges=normalized_edges,
                source="canonical semantic command output",
                canonical_relationships=True,
            )
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("intent", task.intent_ids),
        ("invocation", task.invocation_ids),
        ("selection", task.selection_ids),
        ("workflow", task.compiled_workflow_ids),
        ("plan", task.execution_plan_ids),
        ("execution", task.execution_ids),
        ("evidence", task.evidence_ids),
        ("approval", task.approval_ids),
        ("failure", task.failure_ids),
        ("artifact", task.artifact_ids),
        ("assurance", task.assurance_case_ids),
    )
    nodes: list[Mapping[str, Any]] = [
        {"id": task.task_id, "label": task.title, "type": "task"}
    ]
    edges: list[Mapping[str, Any]] = []
    for group, identifiers in groups:
        for index, identifier in enumerate(identifiers):
            nodes.append({"id": identifier, "label": identifier, "type": group})
            edges.append(
                {
                    "from": task.task_id,
                    "to": identifier,
                    "relation": "GUI_REFERENCES",
                    "order": index,
                }
            )
    return DomainGraphProjection(
        nodes=tuple(nodes),
        edges=tuple(edges),
        source="GUI task projection",
        canonical_relationships=False,
    )


@dataclass(frozen=True)
class IURMDimensionProjection:
    name: str
    baseline: Any
    values: tuple[Any, ...]
    coverage: str
    interactions: tuple[str, ...]


@dataclass(frozen=True)
class IURMProjection:
    dimensions: tuple[IURMDimensionProjection, ...]
    minimum_viable_dimensions: tuple[str, ...]
    source_outputs: tuple[Mapping[str, Any], ...]


def iurm_for_task(task: GuiTask) -> IURMProjection:
    outputs = semantic_outputs(task.last_result)
    dimensions: dict[str, list[Any]] = {}
    baseline: dict[str, Any] = {}
    pairs: list[tuple[str, str]] = []
    minimum: list[str] = []
    for output in outputs:
        raw_dimensions = output.get("dimensions")
        if isinstance(raw_dimensions, Mapping):
            for name, values in raw_dimensions.items():
                dimensions[str(name)] = list(values) if isinstance(values, list) else [values]
        raw_baseline = output.get("baseline")
        if isinstance(raw_baseline, Mapping):
            baseline.update(raw_baseline)
        raw_pairs = output.get("pairs")
        if isinstance(raw_pairs, list):
            for pair in raw_pairs:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    pairs.append((str(pair[0]), str(pair[1])))
        raw_minimum = output.get("minimum_viable_dimensions")
        if isinstance(raw_minimum, list):
            minimum.extend(str(item) for item in raw_minimum)
    projected = []
    for name, values in dimensions.items():
        related = sorted(
            right if left == name else left
            for left, right in pairs
            if name in {left, right}
        )
        projected.append(
            IURMDimensionProjection(
                name=name,
                baseline=baseline.get(name),
                values=tuple(values),
                coverage="returned" if values else "unknown",
                interactions=tuple(related),
            )
        )
    projected.sort(key=lambda item: item.name)
    return IURMProjection(
        dimensions=tuple(projected),
        minimum_viable_dimensions=tuple(dict.fromkeys(minimum)),
        source_outputs=outputs,
    )
