from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Tuple

from .errors import PolicyError


WRITING_PROFILES = ("general", "scientific-essay", "argumentative-essay")

NODE_KINDS = {
    "thesis",
    "claim",
    "premise",
    "evidence",
    "warrant",
    "counterclaim",
    "rebuttal",
    "qualifier",
    "limitation",
    "implication",
}

EDGE_KINDS = {
    "supports",
    "warrants",
    "attacks",
    "rebuts",
    "qualifies",
    "limits",
    "entails",
    "depends_on",
}

INFERENCE_MODES = {
    "unspecified",
    "deductive",
    "inductive",
    "abductive",
    "causal",
    "analogical",
    "authority",
    "defeasible",
}

POSITIVE_EDGE_KINDS = {"supports", "warrants", "entails", "depends_on"}


@dataclass(frozen=True)
class ArgumentNode:
    node_id: str
    kind: str
    proposition: str
    source_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise PolicyError("argument node_id must be non-empty")
        if self.kind not in NODE_KINDS:
            raise PolicyError(f"unsupported argument node kind: {self.kind!r}")
        if not self.proposition.strip():
            raise PolicyError("argument proposition must be non-empty")


@dataclass(frozen=True)
class ArgumentEdge:
    source: str
    target: str
    relation: str
    inference_id: str = ""
    inference_mode: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise PolicyError("argument edge endpoints must be non-empty")
        if self.source == self.target:
            raise PolicyError("argument edge cannot be a self-loop")
        if self.relation not in EDGE_KINDS:
            raise PolicyError(f"unsupported argument relation: {self.relation!r}")
        if self.inference_mode not in INFERENCE_MODES:
            raise PolicyError(f"unsupported inference mode: {self.inference_mode!r}")


@dataclass(frozen=True)
class ArgumentTopology:
    nodes: Tuple[ArgumentNode, ...]
    edges: Tuple[ArgumentEdge, ...]

    def node_map(self) -> Dict[str, ArgumentNode]:
        return {node.node_id: node for node in self.nodes}

    def validate(self, *, require_counterargument_response: bool = True) -> None:
        if not self.nodes:
            raise PolicyError("argument topology must contain nodes")
        node_map = self.node_map()
        if len(node_map) != len(self.nodes):
            raise PolicyError("argument topology node IDs must be unique")
        thesis_nodes = [node for node in self.nodes if node.kind == "thesis"]
        if len(thesis_nodes) != 1:
            raise PolicyError("argument topology requires exactly one thesis node")
        thesis_id = thesis_nodes[0].node_id

        for edge in self.edges:
            if edge.source not in node_map or edge.target not in node_map:
                raise PolicyError("argument edge references an unknown node")

        self._require_positive_graph_acyclic(node_map)

        dialectical = {node_id: set() for node_id in node_map}
        for edge in self.edges:
            dialectical[edge.source].add(edge.target)

        for node in self.nodes:
            if node.node_id == thesis_id or node.kind == "implication":
                continue
            if not self._reaches(node.node_id, thesis_id, dialectical):
                raise PolicyError(
                    f"argument node {node.node_id!r} is disconnected from the thesis"
                )

        for node in self.nodes:
            if node.kind == "evidence" and not node.source_refs:
                raise PolicyError(
                    f"evidence node {node.node_id!r} requires at least one source reference"
                )

        if require_counterargument_response:
            counterclaims = {node.node_id for node in self.nodes if node.kind == "counterclaim"}
            active_counterclaims = {
                edge.source
                for edge in self.edges
                if edge.relation == "attacks" and edge.source in counterclaims
            }
            unanswered = {
                counterclaim
                for counterclaim in active_counterclaims
                if not any(
                    edge.relation == "rebuts" and edge.target == counterclaim
                    for edge in self.edges
                )
            }
            if unanswered:
                raise PolicyError(
                    "counterclaims require an explicit rebuttal/response: "
                    f"{sorted(unanswered)!r}"
                )

    def linked_inference_groups(self) -> Dict[str, Tuple[ArgumentEdge, ...]]:
        """Return explicitly grouped inference edges.

        Edges that share a non-empty inference_id are treated as linked premises:
        their support is intended to work together. Ungrouped support edges are
        interpreted as independent/convergent unless the writer specifies a group.
        """

        groups: Dict[str, list[ArgumentEdge]] = {}
        for edge in self.edges:
            if not edge.inference_id:
                continue
            groups.setdefault(edge.inference_id, []).append(edge)
        return {
            inference_id: tuple(
                sorted(
                    edges,
                    key=lambda edge: (
                        edge.source,
                        edge.target,
                        edge.relation,
                        edge.inference_mode,
                    ),
                )
            )
            for inference_id, edges in sorted(groups.items())
        }

    def _require_positive_graph_acyclic(self, node_map: Mapping[str, ArgumentNode]) -> None:
        adjacency = {node_id: [] for node_id in node_map}
        for edge in self.edges:
            if edge.relation in POSITIVE_EDGE_KINDS:
                adjacency[edge.source].append(edge.target)

        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in permanent:
                return
            if node_id in temporary:
                raise PolicyError("positive argument support graph contains a cycle")
            temporary.add(node_id)
            for target in sorted(adjacency[node_id]):
                visit(target)
            temporary.remove(node_id)
            permanent.add(node_id)

        for node_id in sorted(adjacency):
            visit(node_id)

    @staticmethod
    def _reaches(source: str, target: str, adjacency: Mapping[str, set[str]]) -> bool:
        frontier = [source]
        visited = set()
        while frontier:
            current = frontier.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            frontier.extend(sorted(adjacency.get(current, ()), reverse=True))
        return False


def research_backed_profile(profile: str) -> str:
    if profile not in WRITING_PROFILES:
        raise PolicyError(f"unsupported writing profile: {profile!r}")

    common = """
FORMAL UNIVERSITY WRITING RULES
- Analyse the assignment before drafting: identify content words, direction words, limiting/focus words, genre, audience, marking criteria, required evidence and citation style.
- State one clear central thesis/position and make every body section contribute to it.
- Build paragraphs around a claim -> evidence -> reasoning link, not around one source at a time.
- Synthesize multiple sources by theme, agreement, disagreement, method, limitation or implication; do not produce a source-by-source catalogue.
- Evaluate evidence for relevance, credibility, method, limitations, bias and consistency with other evidence.
- Make reasoning explicit: show why the evidence supports the claim and surface important implicit assumptions/warrants.
- Distinguish observed evidence from interpretation, inference, hypothesis and speculation.
- Use calibrated language. Do not claim causation from correlation alone; qualify claims where evidence is partial, indirect or defeasible.
- Include counterclaims or alternative explanations where they materially affect the thesis, then respond with evidence and reasoning rather than dismissive rhetoric.
- Use an introduction that establishes context, thesis and roadmap; a logically ordered body; and a conclusion that answers the task without introducing new evidence.
- Prefer direct, precise, formal prose. Remove repetition, vague filler, unsupported certainty and ornamental complexity.
- Preserve accurate citations and never invent references, quotations, results, statistics, DOIs or page numbers.
""".strip()

    scientific = """
SCIENTIFIC ESSAY PROFILE
- Treat the essay as a scientific argument, not as a laboratory report unless the assessment explicitly requires report/IMRaD structure.
- Define the scientific question or contested proposition precisely and state the scope, system, population, conditions and important definitions.
- Organise the body around scientific claims or mechanisms. For each major claim record: claim, supporting evidence, method/source, reasoning, limitations, competing explanation and confidence/qualifier.
- Prefer peer-reviewed primary research for empirical claims, using reviews and authoritative syntheses to establish context or consensus.
- Compare methods and evidential quality, not merely conclusions. Note sample size, measurement validity, controls, uncertainty, reproducibility/replicability and external validity when relevant.
- Separate necessity, sufficiency, correlation, mechanism and causation. State which relation the evidence actually establishes.
- Report uncertainty honestly: contradictory evidence, null results, unresolved mechanisms and methodological limits belong in the argument when material.
- The conclusion should state what the evidence justifies, what remains uncertain, and the strongest reasonable implication without overclaiming.
""".strip()

    argumentative = """
ARGUMENTATIVE ESSAY + LOGIC TOPOLOGY PROFILE
- Construct an explicit ArgumentTopology before prose. Use one thesis node and nodes for claims, premises, evidence, warrants/implicit assumptions, counterclaims, rebuttals, qualifiers, limitations and implications.
- Use directed relations such as supports, warrants, attacks, rebuts, qualifies, limits, entails and depends_on.
- Keep the positive support graph acyclic: evidence/premises support intermediate claims, and intermediate claims support the thesis. Avoid circular support.
- Connect opposing evidence and premises through the counterclaim they support; dialectical attack/rebuttal relations may cross the positive support hierarchy.
- Standardise important reasoning into premises and conclusion. Identify unstated premises needed for an inference and test whether they are defensible.
- Distinguish linked premises (needed together) from convergent premises (independent reasons). Use a shared inference_id for linked premises where a machine representation is produced.
- Label material inference modes where useful: deductive, inductive, abductive, causal, analogical, authority or defeasible.
- For deductive reasoning, test validity and premise acceptability. For inductive/abductive/causal reasoning, state the inference as defeasible and test alternative explanations or defeaters.
- Every serious counterclaim must attack a specific claim, inference or premise. Every rebuttal must answer that counterclaim by rebutting its conclusion, undermining a premise or undercutting the inference.
- Apply critical questions to argument schemes: source expertise, domain relevance, independence, consistency, evidence base, analogy relevance, causal alternatives and possible exceptions.
- Translate the topology into readable prose rather than exposing graph jargon unless the assignment benefits from formal notation.
""".strip()

    if profile == "general":
        return common
    if profile == "scientific-essay":
        return f"{common}\n\n{scientific}"
    return f"{common}\n\n{argumentative}"


def profile_dimensions(profile: str) -> Tuple[str, ...]:
    base = (
        "task compliance",
        "audience",
        "thesis",
        "structure",
        "evidence quality",
        "reasoning",
        "source synthesis",
        "citation integrity",
        "clarity",
        "tone",
        "length",
    )
    if profile == "scientific-essay":
        return base + (
            "scientific claim calibration",
            "methodological quality",
            "causal inference",
            "uncertainty",
            "reproducibility",
            "limitations",
        )
    if profile == "argumentative-essay":
        return base + (
            "argument topology",
            "implicit warrants",
            "counterarguments",
            "rebuttals",
            "inference validity",
            "defeaters",
        )
    if profile != "general":
        raise PolicyError(f"unsupported writing profile: {profile!r}")
    return base
