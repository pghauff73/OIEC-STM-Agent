from __future__ import annotations

from collections.abc import Iterable

from ourd.egcf.models import (
    AssuranceCase,
    ConfidenceAssessment,
    EvidenceArtifact,
    ExecutionPlan,
    QualificationRecord,
    SelectionDecision,
)

from .read_models import ReadOnlyEGCFRepository
from .widgets.graph_view import GraphEdge, GraphNode


def evidence_graph(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
    requested = tuple(dict.fromkeys(str(item) for item in identifiers if item))
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_ids: set[str] = set()

    def add_node(node: GraphNode) -> None:
        if node.node_id not in node_ids:
            node_ids.add(node.node_id)
            nodes.append(node)

    def evidence_ids(record) -> tuple[str, ...]:
        if isinstance(record, EvidenceArtifact):
            return (record.object_id,)
        if isinstance(record, (QualificationRecord, SelectionDecision, ConfidenceAssessment)):
            return tuple(record.evidence_ids)
        if isinstance(record, AssuranceCase):
            return tuple([*record.supporting_evidence, *record.refuting_evidence])
        if isinstance(record, ExecutionPlan):
            return tuple(record.evidence_ids)
        return ()

    expanded: list[str] = []
    for index, identifier in enumerate(requested):
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            add_node(
                GraphNode(
                    node_id=f"missing:{identifier}",
                    label="Unresolved support",
                    layer=0,
                    order=index,
                    status="blocked",
                    subtitle=identifier,
                    object_id=identifier,
                )
            )
            continue
        if isinstance(record, EvidenceArtifact):
            expanded.append(record.object_id)
            continue
        support_node = f"support:{record.object_id}"
        add_node(
            GraphNode(
                node_id=support_node,
                label=record.object_type,
                layer=0,
                order=index,
                status="neutral",
                subtitle=record.object_id,
                object_id=record.object_id,
            )
        )
        for evidence_id in evidence_ids(record):
            expanded.append(evidence_id)
            edges.append(GraphEdge(support_node, f"evidence:{evidence_id}", "references"))

    for index, identifier in enumerate(dict.fromkeys(expanded)):
        try:
            record = repository.get(identifier)
        except (OSError, ValueError, KeyError):
            add_node(
                GraphNode(
                    node_id=f"evidence:{identifier}",
                    label="Missing evidence",
                    layer=2,
                    order=index,
                    status="blocked",
                    subtitle=identifier,
                    object_id=identifier,
                )
            )
            continue
        if not isinstance(record, EvidenceArtifact):
            add_node(
                GraphNode(
                    node_id=f"evidence:{identifier}",
                    label=record.object_type,
                    layer=2,
                    order=index,
                    status="neutral",
                    subtitle="support object",
                    object_id=record.object_id,
                )
            )
            continue
        subject_node = f"subject:{record.subject_id}"
        add_node(
            GraphNode(
                node_id=subject_node,
                label="Subject",
                layer=1,
                order=index,
                status="neutral",
                subtitle=record.subject_id,
                object_id=record.subject_id if ":sha256:" in record.subject_id else "",
            )
        )
        evidence_node = f"evidence:{record.object_id}"
        add_node(
            GraphNode(
                node_id=evidence_node,
                label=record.category or "Evidence",
                layer=2,
                order=index,
                status="qualified" if record.success is not False else "blocked",
                subtitle=(
                    f"{'SIMULATED' if record.simulated else 'REAL'} | "
                    f"{record.object_id.partition(':sha256:')[2][:12]}"
                ),
                object_id=record.object_id,
            )
        )
        edges.append(GraphEdge(subject_node, evidence_node, "supported by"))
    return tuple(nodes), tuple(edges)
