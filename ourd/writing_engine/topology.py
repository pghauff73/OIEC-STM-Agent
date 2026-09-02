from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

from .models import ReasoningAnnotation
from .signatures import signature


def build_argument_topology(
    objective: str,
    annotations: Sequence[ReasoningAnnotation],
) -> tuple[Any, str]:
    from ..formal_writing import ArgumentEdge, ArgumentNode, ArgumentTopology

    thesis = ArgumentNode(node_id="thesis", kind="thesis", proposition=objective)
    nodes = [thesis]
    edges = []
    for index, annotation in enumerate(annotations, 1):
        kind = annotation.component_role
        node_id = f"reasoning-{index}"
        proposition = annotation.source_claim or annotation.target_claim
        node = ArgumentNode(
            node_id=node_id,
            kind=kind,
            proposition=proposition,
            source_refs=annotation.source_span_ids,
        )
        nodes.append(node)
        relation = {
            "counterclaim": "attacks",
            "rebuttal": "rebuts",
            "qualifier": "qualifies",
            "limitation": "limits",
            "warrant": "warrants",
            "implication": "entails",
        }.get(kind, "supports")
        edges.append(
            ArgumentEdge(
                source=node_id,
                target="thesis",
                relation=relation,
                inference_mode=annotation.inference_mode,
            )
        )
    topology = ArgumentTopology(nodes=tuple(nodes), edges=tuple(edges))
    topology.validate(require_counterargument_response=False)
    return topology, signature(
        {
            "nodes": tuple(asdict(item) for item in topology.nodes),
            "edges": tuple(asdict(item) for item in topology.edges),
        }
    )


__all__ = ["build_argument_topology"]
