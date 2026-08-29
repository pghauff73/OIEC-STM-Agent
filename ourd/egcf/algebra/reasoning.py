from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product
from math import factorial
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import canonical_json, sha256_json


REASONING_ALGEBRA_VERSION = "saa-reasoning-algebra-v1"
MAX_REASONING_NODES = 32
MAX_REASONING_EDGES = 128
MAX_REASONING_CANONICAL_PERMUTATIONS = 4096
MAX_REASONING_STEPS = 1024

REASONING_OPERATORS = {
    "OBSERVE",
    "CLASSIFY",
    "DECOMPOSE",
    "GENERATE",
    "COMPARE",
    "PREDICT",
    "ABSTRACT",
    "SPECIALIZE",
    "GENERALIZE",
    "DEDUCE",
    "INDUCE",
    "ABDUCE",
    "FALSIFY",
    "VERIFY",
    "DISCRIMINATE",
    "OPTIMIZE",
    "PRUNE",
    "BACKTRACK",
    "SYNTHESIZE",
    "BOUND",
    "TERMINATE",
}

REASONING_EDGE_RELATIONS = {
    "NEXT",
    "DEPENDS_ON",
    "SUPPORTS",
    "WARRANTS",
    "ATTACKS",
    "REBUTS",
    "QUALIFIES",
    "LIMITS",
    "ENTAILS",
    "FALSIFIES",
    "BRANCH_TRUE",
    "BRANCH_FALSE",
    "BACKTRACK_TO",
}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _operator(value: str) -> str:
    result = str(value).strip().upper()
    if result not in REASONING_OPERATORS:
        raise EGCFError(f"unsupported SAA-8 reasoning operator: {value!r}")
    return result


def _relation(value: str) -> str:
    result = str(value).strip().upper()
    if result not in REASONING_EDGE_RELATIONS:
        raise EGCFError(f"unsupported SAA-8 reasoning edge relation: {value!r}")
    return result


@dataclass(frozen=True)
class ReasoningNodeSpec:
    node_id: str
    operator: str
    semantic_inputs: Tuple[str, ...] = ()
    semantic_outputs: Tuple[str, ...] = ()
    public_claim_ids: Tuple[str, ...] = ()
    evidence_requirements: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "operator": self.operator,
            "semantic_inputs": list(self.semantic_inputs),
            "semantic_outputs": list(self.semantic_outputs),
            "public_claim_ids": list(self.public_claim_ids),
            "evidence_requirements": list(self.evidence_requirements),
            "assumptions": list(self.assumptions),
            "falsifiers": list(self.falsifiers),
            "description": self.description,
        }


@dataclass(frozen=True)
class ReasoningEdgeSpec:
    source: str
    target: str
    relation: str = "NEXT"
    condition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "condition": self.condition,
        }


@dataclass(frozen=True)
class ReasoningTerminationSpec:
    kind: str
    predicate: str
    max_steps: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "predicate": self.predicate,
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True)
class ReasoningAlgorithmSpec:
    name: str
    inputs: Tuple[str, ...]
    outputs: Tuple[str, ...]
    nodes: Tuple[ReasoningNodeSpec, ...]
    edges: Tuple[ReasoningEdgeSpec, ...]
    invariants: Tuple[str, ...]
    termination: ReasoningTerminationSpec
    applicability: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "invariants": list(self.invariants),
            "termination": self.termination.to_dict(),
            "applicability": list(self.applicability),
        }


@dataclass(frozen=True)
class CanonicalReasoningAlgorithm:
    schema_version: int
    reasoning_version: str
    input_semantics: Tuple[str, ...]
    output_semantics: Tuple[str, ...]
    canonical_nodes: Tuple[Mapping[str, Any], ...]
    canonical_edges: Tuple[Mapping[str, Any], ...]
    invariants: Tuple[str, ...]
    termination: Mapping[str, Any]
    applicability: Tuple[str, ...]
    topology_signature: str
    semantic_signature: str
    canonical_reasoning_signature: str
    canonicalization_strength: str
    canonical_permutations_evaluated: int
    public_artifact_only: bool
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reasoning_version": self.reasoning_version,
            "input_semantics": list(self.input_semantics),
            "output_semantics": list(self.output_semantics),
            "canonical_nodes": [dict(item) for item in self.canonical_nodes],
            "canonical_edges": [dict(item) for item in self.canonical_edges],
            "invariants": list(self.invariants),
            "termination": dict(self.termination),
            "applicability": list(self.applicability),
            "topology_signature": self.topology_signature,
            "semantic_signature": self.semantic_signature,
            "canonical_reasoning_signature": self.canonical_reasoning_signature,
            "canonicalization_strength": self.canonicalization_strength,
            "canonical_permutations_evaluated": self.canonical_permutations_evaluated,
            "public_artifact_only": self.public_artifact_only,
            "warnings": list(self.warnings),
        }


def _node_intrinsic(node: ReasoningNodeSpec) -> dict[str, Any]:
    return {
        "operator": _operator(node.operator),
        "semantic_inputs": list(_texts(node.semantic_inputs)),
        "semantic_outputs": list(_texts(node.semantic_outputs)),
        "public_claim_ids": list(_texts(node.public_claim_ids)),
        "evidence_requirements": list(_texts(node.evidence_requirements)),
        "assumptions": list(_texts(node.assumptions)),
        "falsifiers": list(_texts(node.falsifiers)),
    }


def _validate(spec: ReasoningAlgorithmSpec) -> tuple[dict[str, ReasoningNodeSpec], Tuple[ReasoningEdgeSpec, ...]]:
    if not isinstance(spec, ReasoningAlgorithmSpec):
        raise EGCFError("SAA-8 requires ReasoningAlgorithmSpec")
    if not spec.nodes or len(spec.nodes) > MAX_REASONING_NODES:
        raise EGCFError("SAA-8 node count outside bounded range")
    if len(spec.edges) > MAX_REASONING_EDGES:
        raise EGCFError("SAA-8 edge count exceeds bounded cap")
    by_id: dict[str, ReasoningNodeSpec] = {}
    for node in spec.nodes:
        node_id = str(node.node_id).strip()
        if not node_id or node_id in by_id:
            raise EGCFError("SAA-8 reasoning node IDs must be unique and non-empty")
        _operator(node.operator)
        by_id[node_id] = node
    seen_edges: set[tuple[str, str, str, str]] = set()
    normalized_edges: list[ReasoningEdgeSpec] = []
    for edge in spec.edges:
        source = str(edge.source).strip()
        target = str(edge.target).strip()
        if source not in by_id or target not in by_id:
            raise EGCFError("SAA-8 reasoning edge references unknown node")
        relation = _relation(edge.relation)
        condition = _text(edge.condition)
        key = (source, target, relation, condition)
        if key in seen_edges:
            raise EGCFError("duplicate SAA-8 reasoning edge")
        seen_edges.add(key)
        normalized_edges.append(ReasoningEdgeSpec(source, target, relation, condition))
    if not isinstance(spec.termination, ReasoningTerminationSpec):
        raise EGCFError("SAA-8 requires explicit ReasoningTerminationSpec")
    if spec.termination.max_steps < 1 or spec.termination.max_steps > MAX_REASONING_STEPS:
        raise EGCFError("SAA-8 termination step bound outside supported range")
    if not _text(spec.termination.kind) or not _text(spec.termination.predicate):
        raise EGCFError("SAA-8 termination kind and predicate must be explicit")
    return by_id, tuple(normalized_edges)


def _refined_colors(
    by_id: Mapping[str, ReasoningNodeSpec],
    edges: Sequence[ReasoningEdgeSpec],
) -> dict[str, str]:
    intrinsic = {node_id: _node_intrinsic(node) for node_id, node in by_id.items()}
    colors = {node_id: sha256_json(payload) for node_id, payload in intrinsic.items()}
    for _ in range(len(by_id) + 1):
        updated: dict[str, str] = {}
        for node_id in sorted(by_id):
            incoming = sorted(
                (edge.relation, edge.condition, colors[edge.source])
                for edge in edges
                if edge.target == node_id
            )
            outgoing = sorted(
                (edge.relation, edge.condition, colors[edge.target])
                for edge in edges
                if edge.source == node_id
            )
            updated[node_id] = sha256_json(
                {
                    "intrinsic": intrinsic[node_id],
                    "incoming": incoming,
                    "outgoing": outgoing,
                }
            )
        if updated == colors:
            break
        colors = updated
    return colors


def _permutation_budget(groups: Sequence[Sequence[str]]) -> int:
    result = 1
    for group in groups:
        result *= factorial(len(group))
        if result > MAX_REASONING_CANONICAL_PERMUTATIONS:
            return result
    return result


def _serialization_for_order(
    order: Sequence[str],
    by_id: Mapping[str, ReasoningNodeSpec],
    edges: Sequence[ReasoningEdgeSpec],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    position = {node_id: index for index, node_id in enumerate(order)}
    nodes = [_node_intrinsic(by_id[node_id]) for node_id in order]
    canonical_edges = sorted(
        (
            {
                "source": position[edge.source],
                "target": position[edge.target],
                "relation": edge.relation,
                "condition": edge.condition,
            }
            for edge in edges
        ),
        key=lambda item: (item["source"], item["target"], item["relation"], item["condition"]),
    )
    serialized = canonical_json({"nodes": nodes, "edges": canonical_edges})
    return nodes, canonical_edges, serialized


def canonicalize_reasoning_algorithm(
    spec: ReasoningAlgorithmSpec,
) -> CanonicalReasoningAlgorithm:
    by_id, edges = _validate(spec)
    colors = _refined_colors(by_id, edges)
    grouped: dict[str, list[str]] = {}
    for node_id, color in colors.items():
        grouped.setdefault(color, []).append(node_id)
    groups = [grouped[color] for color in sorted(grouped)]
    budget = _permutation_budget(groups)
    evaluated = 0
    warnings: list[str] = []
    if budget <= MAX_REASONING_CANONICAL_PERMUTATIONS:
        best: tuple[str, list[dict[str, Any]], list[dict[str, Any]], Tuple[str, ...]] | None = None
        permutation_sets = [tuple(permutations(sorted(group))) for group in groups]
        for choice in product(*permutation_sets):
            order = tuple(node_id for group_order in choice for node_id in group_order)
            nodes, canonical_edges, serialized = _serialization_for_order(order, by_id, edges)
            evaluated += 1
            if best is None or serialized < best[0]:
                best = (serialized, nodes, canonical_edges, order)
        assert best is not None
        canonical_nodes = tuple(best[1])
        canonical_edges = tuple(best[2])
        strength = "EXACT_BOUNDED_GRAPH_CANONICALIZATION"
        source_binding: list[str] = []
    else:
        order = tuple(
            sorted(
                by_id,
                key=lambda node_id: (
                    colors[node_id],
                    canonical_json(_node_intrinsic(by_id[node_id])),
                    node_id,
                ),
            )
        )
        nodes, canonical_edges, _ = _serialization_for_order(order, by_id, edges)
        canonical_nodes = tuple(nodes)
        canonical_edges = tuple(canonical_edges)
        strength = "CONSERVATIVE_RENAMING_BOUND"
        source_binding = list(order)
        warnings.append(
            "Reasoning graph symmetry exceeded the exact permutation budget. Source node IDs remain conservatively bound to avoid false equivalence."
        )
    termination = {
        "kind": _text(spec.termination.kind),
        "predicate": _text(spec.termination.predicate),
        "max_steps": int(spec.termination.max_steps),
    }
    topology_payload = {
        "version": REASONING_ALGEBRA_VERSION,
        "operators": [node["operator"] for node in canonical_nodes],
        "edges": [
            {
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["relation"],
            }
            for edge in canonical_edges
        ],
        "termination_kind": termination["kind"],
        "source_binding": source_binding,
    }
    topology_signature = sha256_json(topology_payload)
    input_semantics = _texts(spec.inputs)
    output_semantics = _texts(spec.outputs)
    invariants = _texts(spec.invariants)
    applicability = _texts(spec.applicability)
    semantic_payload = {
        "version": REASONING_ALGEBRA_VERSION,
        "inputs": input_semantics,
        "outputs": output_semantics,
        "nodes": list(canonical_nodes),
        "edges": list(canonical_edges),
        "invariants": invariants,
        "termination": termination,
        "applicability": applicability,
        "source_binding": source_binding,
    }
    semantic_signature = sha256_json(semantic_payload)
    algorithm_payload = {
        "version": REASONING_ALGEBRA_VERSION,
        "topology_signature": topology_signature,
        "semantic_signature": semantic_signature,
        "canonicalization_strength": strength,
    }
    return CanonicalReasoningAlgorithm(
        schema_version=1,
        reasoning_version=REASONING_ALGEBRA_VERSION,
        input_semantics=input_semantics,
        output_semantics=output_semantics,
        canonical_nodes=canonical_nodes,
        canonical_edges=canonical_edges,
        invariants=invariants,
        termination=termination,
        applicability=applicability,
        topology_signature=topology_signature,
        semantic_signature=semantic_signature,
        canonical_reasoning_signature=sha256_json(algorithm_payload),
        canonicalization_strength=strength,
        canonical_permutations_evaluated=evaluated,
        public_artifact_only=True,
        warnings=tuple(warnings),
    )
