from __future__ import annotations

from dataclasses import asdict, replace
from typing import Iterable, Mapping, Sequence

from ..errors import PolicyError
from .models import (
    CandidateSet,
    Hypothesis,
    ReasoningBudget,
    ReasoningEdge,
    ReasoningNode,
    ReasoningPath,
    ReasoningProblem,
    ReasoningTopology,
    canonical_inference_mode,
    stable_hash,
)


POSITIVE_RELATIONS = {
    "supports",
    "requires",
    "entails",
    "predicts",
    "tests",
    "explains",
    "causes",
    "depends_on",
}
ATTACK_RELATIONS = {
    "contradicts",
    "falsifies",
    "undercuts",
    "rebuts",
}
BRANCH_RELATIONS = {
    "entails",
    "predicts",
    "tests",
    "causes",
    "depends_on",
}
GROUNDING_KINDS = {"evidence", "observation", "assumption"}
CONTRIBUTION_KINDS = {
    "hypothesis",
    "conclusion",
    "counterexample",
    "decision",
}


def make_reasoning_node(
    node_id: str,
    kind: str,
    content: str,
    **values: object,
) -> ReasoningNode:
    payload = {
        "node_id": node_id,
        "kind": kind,
        "content": content,
        "evidence_ids": tuple(values.get("evidence_ids", ())),
        "confidence_bp": int(values.get("confidence_bp", 0)),
        "path_id": str(values.get("path_id", "")),
        "validated": bool(values.get("validated", False)),
        "hypothetical": bool(values.get("hypothetical", False)),
        "material": bool(values.get("material", False)),
    }
    return ReasoningNode(**payload, signature=stable_hash(payload))


def inference_identity(
    source_id: str,
    target_id: str,
    relation: str,
    inference_mode: str,
) -> str:
    material = {
        "source_id": source_id,
        "target_id": target_id,
        "relation": relation,
        "inference_mode": canonical_inference_mode(inference_mode),
    }
    return f"inference:{stable_hash(material)}"


def make_reasoning_edge(
    source_id: str,
    target_id: str,
    relation: str,
    inference_mode: str,
) -> ReasoningEdge:
    mode = canonical_inference_mode(inference_mode)
    inference_id = inference_identity(source_id, target_id, relation, mode)
    payload = {
        "source_id": source_id,
        "target_id": target_id,
        "relation": relation,
        "inference_id": inference_id,
        "inference_mode": mode,
    }
    edge_id = f"edge:{stable_hash(payload)}"
    return ReasoningEdge(
        edge_id=edge_id,
        **payload,
        signature=stable_hash({**payload, "edge_id": edge_id}),
    )


def reasoning_topology_payload(topology: ReasoningTopology) -> Mapping[str, object]:
    return {
        "problem_id": topology.problem_id,
        "nodes": [asdict(item) for item in topology.nodes],
        "edges": [asdict(item) for item in topology.edges],
    }


def legacy_reasoning_topology_payload(topology: ReasoningTopology) -> Mapping[str, object]:
    nodes = []
    for node in topology.nodes:
        payload = asdict(node)
        for key in ("validated", "hypothetical", "material"):
            payload.pop(key, None)
        nodes.append(payload)
    edges = []
    for edge in topology.edges:
        payload = asdict(edge)
        for key in ("inference_id", "inference_mode"):
            payload.pop(key, None)
        edges.append(payload)
    return {
        "problem_id": topology.problem_id,
        "nodes": nodes,
        "edges": edges,
    }


def _assumption_node_id(owner_id: str, content: str) -> str:
    return f"assumption:{stable_hash({'owner_id': owner_id, 'content': content})}"


def _add_node(nodes: dict[str, ReasoningNode], node: ReasoningNode) -> None:
    previous = nodes.get(node.node_id)
    if previous is not None and previous != node:
        raise PolicyError(f"reasoning node identity collision: {node.node_id}")
    nodes[node.node_id] = node


def _add_edge(edges: dict[str, ReasoningEdge], edge: ReasoningEdge) -> None:
    previous = edges.get(edge.edge_id)
    if previous is not None and previous != edge:
        raise PolicyError(f"reasoning edge identity collision: {edge.edge_id}")
    edges[edge.edge_id] = edge


def _add_evidence_node(
    nodes: dict[str, ReasoningNode],
    evidence_id: str,
) -> str:
    node_id = f"evidence:{evidence_id}"
    _add_node(
        nodes,
        make_reasoning_node(
            node_id,
            "evidence",
            f"Evidence artifact {evidence_id}",
            evidence_ids=(evidence_id,),
        ),
    )
    return node_id


def _positive_grounding_kinds(
    node_id: str,
    *,
    nodes: Mapping[str, ReasoningNode],
    incoming: Mapping[str, Sequence[str]],
    memo: dict[str, frozenset[str]],
) -> frozenset[str]:
    if node_id in memo:
        return memo[node_id]
    node = nodes[node_id]
    roots: set[str] = set()
    if node.kind in GROUNDING_KINDS:
        roots.add(node.kind)
    if node.kind == "premise" and node.validated:
        roots.add("validated_premise")
    for source_id in incoming.get(node_id, ()):
        roots.update(
            _positive_grounding_kinds(
                source_id,
                nodes=nodes,
                incoming=incoming,
                memo=memo,
            )
        )
    result = frozenset(roots)
    memo[node_id] = result
    return result


def _mark_hypothetical_material_nodes(
    nodes: dict[str, ReasoningNode],
    edges: Mapping[str, ReasoningEdge],
) -> None:
    incoming: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges.values():
        if edge.relation in POSITIVE_RELATIONS:
            incoming[edge.target_id].append(edge.source_id)
    memo: dict[str, frozenset[str]] = {}
    for node_id, node in tuple(nodes.items()):
        if not node.material:
            continue
        roots = _positive_grounding_kinds(
            node_id,
            nodes=nodes,
            incoming=incoming,
            memo=memo,
        )
        if roots == {"assumption"} and not node.hypothetical:
            material = asdict(node)
            material.pop("signature", None)
            material["hypothetical"] = True
            nodes[node_id] = ReasoningNode(
                **material,
                signature=stable_hash(material),
            )


def build_reasoning_topology(
    *,
    problem: ReasoningProblem,
    hypotheses: Sequence[Hypothesis],
    candidates: CandidateSet,
) -> ReasoningTopology:
    nodes: dict[str, ReasoningNode] = {}
    edges: dict[str, ReasoningEdge] = {}
    question_id = f"question:{problem.problem_id}"
    premise_id = f"premise:{problem.problem_id}"
    _add_node(nodes, make_reasoning_node(question_id, "question", problem.goal))
    _add_node(
        nodes,
        make_reasoning_node(
            premise_id,
            "premise",
            problem.statement,
            validated=True,
        ),
    )
    _add_edge(edges, make_reasoning_edge(premise_id, question_id, "requires", "constraint"))

    hypothesis_by_id = {item.hypothesis_id: item for item in hypotheses}
    for hypothesis in sorted(hypotheses, key=lambda item: item.hypothesis_id):
        hypothesis_node_id = f"hypothesis:{hypothesis.hypothesis_id}"
        _add_node(
            nodes,
            make_reasoning_node(
                hypothesis_node_id,
                "hypothesis",
                hypothesis.proposition,
                evidence_ids=(
                    *hypothesis.supporting_evidence,
                    *hypothesis.conflicting_evidence,
                ),
                confidence_bp=hypothesis.posterior_bp,
                hypothetical=True,
            ),
        )
        _add_edge(
            edges,
            make_reasoning_edge(hypothesis_node_id, question_id, "explains", "abductive"),
        )
        for evidence_id in hypothesis.supporting_evidence:
            evidence_node_id = _add_evidence_node(nodes, evidence_id)
            _add_edge(
                edges,
                make_reasoning_edge(
                    evidence_node_id,
                    hypothesis_node_id,
                    "supports",
                    "inductive",
                ),
            )
        for evidence_id in hypothesis.conflicting_evidence:
            evidence_node_id = _add_evidence_node(nodes, evidence_id)
            _add_edge(
                edges,
                make_reasoning_edge(
                    evidence_node_id,
                    hypothesis_node_id,
                    "contradicts",
                    "defeasible",
                ),
            )
        for assumption in hypothesis.assumptions:
            assumption_id = _assumption_node_id(hypothesis_node_id, assumption)
            _add_node(
                nodes,
                make_reasoning_node(
                    assumption_id,
                    "assumption",
                    assumption,
                ),
            )
            _add_edge(
                edges,
                make_reasoning_edge(
                    assumption_id,
                    hypothesis_node_id,
                    "requires",
                    "constraint",
                ),
            )
        for prediction in hypothesis.predictions:
            prediction_material = {
                "hypothesis_id": hypothesis.hypothesis_id,
                "prediction": prediction,
            }
            prediction_id = f"prediction:{stable_hash(prediction_material)}"
            _add_node(nodes, make_reasoning_node(prediction_id, "prediction", prediction))
            _add_edge(
                edges,
                make_reasoning_edge(
                    hypothesis_node_id,
                    prediction_id,
                    "predicts",
                    "probabilistic",
                ),
            )

    verifier_by_path = {report.path_id: report for report in candidates.verifier_reports}
    path_by_id = {path.path_id: path for path in candidates.paths}
    admitted_path_ids = set(candidates.surviving_path_ids)
    step_node_ids: dict[tuple[str, str], str] = {}
    for path in candidates.paths:
        if path.path_id not in admitted_path_ids:
            continue
        for step in path.steps:
            node_id = f"step:{path.path_id}:{step.step_id}"
            step_node_ids[(path.path_id, step.step_id)] = node_id
            _add_node(
                nodes,
                make_reasoning_node(
                    node_id,
                    "claim",
                    step.claim,
                    evidence_ids=step.evidence_ids,
                    confidence_bp=step.confidence_bp,
                    path_id=path.path_id,
                    hypothetical=bool(step.assumptions),
                ),
            )
            for premise in step.premises:
                if premise == "problem":
                    source_id = premise_id
                    relation = "requires"
                elif premise in hypothesis_by_id:
                    source_id = f"hypothesis:{premise}"
                    relation = "supports"
                else:
                    source_id = step_node_ids.get((path.path_id, premise), "")
                    relation = "entails"
                if source_id:
                    _add_edge(
                        edges,
                        make_reasoning_edge(
                            source_id,
                            node_id,
                            relation,
                            step.inference,
                        ),
                    )
            for evidence_id in step.evidence_ids:
                evidence_node_id = _add_evidence_node(nodes, evidence_id)
                _add_edge(
                    edges,
                    make_reasoning_edge(
                        evidence_node_id,
                        node_id,
                        "supports",
                        step.inference,
                    ),
                )
            for assumption in step.assumptions:
                assumption_id = _assumption_node_id(node_id, assumption)
                _add_node(nodes, make_reasoning_node(assumption_id, "assumption", assumption))
                _add_edge(
                    edges,
                    make_reasoning_edge(
                        assumption_id,
                        node_id,
                        "requires",
                        step.inference,
                    ),
                )
        conclusion_id = f"conclusion:{path.path_id}"
        report = verifier_by_path.get(path.path_id)
        material = bool(report and report.verdict != "REJECT") or (
            path.path_id == candidates.selected_path_id
        )
        _add_node(
            nodes,
            make_reasoning_node(
                conclusion_id,
                "conclusion",
                path.conclusion,
                confidence_bp=path.provider_confidence_bp,
                path_id=path.path_id,
                material=material,
            ),
        )
        final_step = path.steps[-1]
        _add_edge(
            edges,
            make_reasoning_edge(
                step_node_ids[(path.path_id, final_step.step_id)],
                conclusion_id,
                "entails",
                final_step.inference,
            ),
        )

    for report in candidates.verifier_reports:
        if report.path_id not in admitted_path_ids:
            continue
        path = path_by_id[report.path_id]
        target_id = step_node_ids[(path.path_id, path.steps[-1].step_id)]
        for index, contradiction in enumerate(report.contradictions, 1):
            node_id = f"counterexample:{report.report_id}:{index:02d}"
            _add_node(
                nodes,
                make_reasoning_node(
                    node_id,
                    "counterexample",
                    contradiction,
                    path_id=report.path_id,
                ),
            )
            _add_edge(
                edges,
                make_reasoning_edge(node_id, target_id, "rebuts", "defeasible"),
            )
    for report in candidates.falsifier_reports:
        if report.path_id not in admitted_path_ids:
            continue
        path = path_by_id[report.path_id]
        for index, counterexample in enumerate(report.counterexamples, 1):
            node_id = f"counterexample:{report.report_id}:{index:02d}"
            _add_node(
                nodes,
                make_reasoning_node(
                    node_id,
                    "counterexample",
                    counterexample,
                    path_id=report.path_id,
                ),
            )
            if report.contradicted_step_ids:
                targets = tuple(
                    step_node_ids[(report.path_id, step_id)]
                    for step_id in report.contradicted_step_ids
                )
            elif path.hypothesis_ids:
                targets = tuple(f"hypothesis:{item}" for item in path.hypothesis_ids)
            else:
                targets = (step_node_ids[(path.path_id, path.steps[-1].step_id)],)
            for target_id in targets:
                _add_edge(
                    edges,
                    make_reasoning_edge(node_id, target_id, "falsifies", "defeasible"),
                )
        for index, condition in enumerate(report.unresolved_defeat_conditions, 1):
            node_id = f"constraint:{report.report_id}:{index:02d}"
            _add_node(
                nodes,
                make_reasoning_node(
                    node_id,
                    "constraint",
                    condition,
                    path_id=report.path_id,
                ),
            )
            _add_edge(
                edges,
                make_reasoning_edge(
                    node_id,
                    f"conclusion:{report.path_id}",
                    "qualifies",
                    "defeasible",
                ),
            )
    if candidates.selected_path_id:
        selected = path_by_id[candidates.selected_path_id]
        conclusion_id = f"conclusion:{selected.path_id}"
        decision_id = f"decision:{problem.problem_id}"
        _add_node(
            nodes,
            make_reasoning_node(
                decision_id,
                "decision",
                candidates.synthesized_conclusion or selected.conclusion,
                path_id=selected.path_id,
                material=True,
            ),
        )
        _add_edge(
            edges,
            make_reasoning_edge(conclusion_id, decision_id, "supports", "constraint"),
        )

    _mark_hypothetical_material_nodes(nodes, edges)
    topology = ReasoningTopology(
        schema_version=2,
        problem_id=problem.problem_id,
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
    )
    return replace(topology, signature=stable_hash(reasoning_topology_payload(topology)))


def validate_reasoning_topology(
    topology: ReasoningTopology,
    *,
    budget: ReasoningBudget,
    declared_evidence_ids: Iterable[str],
) -> None:
    if len(topology.nodes) > budget.max_topology_nodes:
        raise PolicyError("reasoning topology node budget exceeded")
    if len(topology.edges) > budget.max_topology_edges:
        raise PolicyError("reasoning topology edge budget exceeded")
    node_ids = [node.node_id for node in topology.nodes]
    edge_ids = [edge.edge_id for edge in topology.edges]
    if len(set(node_ids)) != len(node_ids):
        raise PolicyError("reasoning topology contains duplicate node IDs")
    if len(set(edge_ids)) != len(edge_ids):
        raise PolicyError("reasoning topology contains duplicate edge IDs")
    nodes = {node.node_id: node for node in topology.nodes}
    known_nodes = set(nodes)
    declared = {str(value) for value in declared_evidence_ids if str(value)}
    positive_adjacency: dict[str, list[str]] = {node_id: [] for node_id in known_nodes}
    positive_incoming: dict[str, list[str]] = {node_id: [] for node_id in known_nodes}
    undirected: dict[str, set[str]] = {node_id: set() for node_id in known_nodes}
    branch_counts = {node_id: 0 for node_id in known_nodes}

    if POSITIVE_RELATIONS & ATTACK_RELATIONS:
        raise PolicyError("attack relations overlap positive reasoning relations")
    for edge in topology.edges:
        if edge.source_id not in known_nodes or edge.target_id not in known_nodes:
            raise PolicyError("reasoning topology edge references an unknown node")
        if topology.schema_version >= 2:
            if edge.inference_mode == "unspecified" or not edge.inference_id:
                raise PolicyError("reasoning topology edge lacks explicit inference metadata")
            expected_inference_id = inference_identity(
                edge.source_id,
                edge.target_id,
                edge.relation,
                edge.inference_mode,
            )
            if edge.inference_id != expected_inference_id:
                raise PolicyError("reasoning topology inference identity mismatch")
            expected = make_reasoning_edge(
                edge.source_id,
                edge.target_id,
                edge.relation,
                edge.inference_mode,
            )
            if edge.edge_id != expected.edge_id or edge.signature != expected.signature:
                raise PolicyError("reasoning topology edge content address mismatch")
        undirected[edge.source_id].add(edge.target_id)
        undirected[edge.target_id].add(edge.source_id)
        if edge.relation in POSITIVE_RELATIONS:
            positive_adjacency[edge.source_id].append(edge.target_id)
            positive_incoming[edge.target_id].append(edge.source_id)
        if edge.relation in BRANCH_RELATIONS:
            branch_counts[edge.source_id] += 1
    if any(count > budget.max_branch_factor for count in branch_counts.values()):
        raise PolicyError("reasoning topology branch factor exceeded")

    for node in topology.nodes:
        unknown_evidence = set(node.evidence_ids) - declared
        if unknown_evidence:
            raise PolicyError("reasoning topology references undeclared evidence")
        if node.kind == "evidence":
            if len(node.evidence_ids) != 1:
                raise PolicyError("reasoning evidence node must bind exactly one artifact")
            evidence_id = node.evidence_ids[0]
            if evidence_id not in declared or node.node_id != f"evidence:{evidence_id}":
                raise PolicyError("reasoning evidence node lies outside the finite universe")
        if node.kind == "decision":
            if not node.path_id:
                raise PolicyError("reasoning decision lacks a candidate path")
            conclusion_id = f"conclusion:{node.path_id}"
            if conclusion_id not in known_nodes or not any(
                edge.source_id == conclusion_id
                and edge.target_id == node.node_id
                and edge.relation == "supports"
                for edge in topology.edges
            ):
                raise PolicyError("reasoning decision lacks a traceable candidate conclusion")
        if node.kind == "counterexample":
            attacks = tuple(
                edge
                for edge in topology.edges
                if edge.source_id == node.node_id and edge.relation in ATTACK_RELATIONS
            )
            if not attacks or any(
                nodes[edge.target_id].kind not in {"hypothesis", "claim"}
                for edge in attacks
            ):
                raise PolicyError("counterexample is not bound to a hypothesis or reasoning step")

    state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        marker = state.get(node_id, 0)
        if marker == 1:
            raise PolicyError("positive reasoning topology contains a cycle")
        if marker == 2:
            return
        state[node_id] = 1
        for target_id in positive_adjacency[node_id]:
            visit(target_id)
        state[node_id] = 2

    for node_id in sorted(known_nodes):
        visit(node_id)

    grounding_memo: dict[str, frozenset[str]] = {}
    for node in topology.nodes:
        if not node.material:
            continue
        roots = _positive_grounding_kinds(
            node.node_id,
            nodes=nodes,
            incoming=positive_incoming,
            memo=grounding_memo,
        )
        if not roots:
            raise PolicyError("material reasoning conclusion lacks a grounding trace")
        if roots == {"assumption"} and not node.hypothetical:
            raise PolicyError("assumption-only conclusion must remain hypothetical")

    anchors = {node.node_id for node in topology.nodes if node.kind in CONTRIBUTION_KINDS}
    for start_id in sorted(known_nodes):
        if start_id in anchors:
            continue
        seen = {start_id}
        frontier = [start_id]
        contributes = False
        while frontier:
            current = frontier.pop()
            if current in anchors:
                contributes = True
                break
            for adjacent in undirected[current]:
                if adjacent not in seen:
                    seen.add(adjacent)
                    frontier.append(adjacent)
        if not contributes:
            raise PolicyError("reasoning topology contains an unconnected branch")


__all__ = [
    "ATTACK_RELATIONS",
    "BRANCH_RELATIONS",
    "GROUNDING_KINDS",
    "POSITIVE_RELATIONS",
    "build_reasoning_topology",
    "inference_identity",
    "legacy_reasoning_topology_payload",
    "make_reasoning_edge",
    "make_reasoning_node",
    "reasoning_topology_payload",
    "validate_reasoning_topology",
]
