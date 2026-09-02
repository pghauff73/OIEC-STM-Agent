from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping, Tuple

from ..constants import SCORE_SCALE

HYPOTHESIS_STATUSES = {
    "ACTIVE",
    "WEAKENED",
    "SUPPORTED",
    "FALSIFIED",
    "UNRESOLVED",
}
NODE_KINDS = {
    "question",
    "hypothesis",
    "premise",
    "assumption",
    "claim",
    "observation",
    "evidence",
    "inference",
    "prediction",
    "experiment",
    "counterexample",
    "constraint",
    "conclusion",
    "decision",
}
EDGE_RELATIONS = {
    "supports",
    "contradicts",
    "requires",
    "entails",
    "predicts",
    "tests",
    "falsifies",
    "qualifies",
    "explains",
    "causes",
    "depends_on",
    "undercuts",
    "rebuts",
}
INFERENCE_MODES = {
    "unspecified",
    "deductive",
    "inductive",
    "abductive",
    "causal",
    "analogical",
    "probabilistic",
    "authority",
    "defeasible",
    "constraint",
    "computational",
}
INFERENCE_MODE_ALIASES = {
    "empirical": "inductive",
    "formal": "deductive",
    "mathematical": "computational",
    "mechanistic": "causal",
}
VERIFIER_VERDICTS = {"ACCEPT", "REVISE", "REJECT"}
FALSIFIER_VERDICTS = {"SURVIVES", "REVISE", "REJECT"}
REASONING_DECISIONS = {
    "ACCEPT",
    "REVISE",
    "REGENERATE",
    "STOP_UNRESOLVED",
    "STOP_NO_VALUE",
}
REASONING_TERMINAL_STATES = {
    "SOLUTION",
    "EPISTEMIC_STOP",
    "INSUFFICIENT_EVIDENCE",
    "GOVERNANCE_STOP",
    "COMPUTE_BUDGET_EXHAUSTED",
    "NO_SURVIVING_HYPOTHESIS",
}
REASONING_OPERATIONS = {
    "GENERATE_HYPOTHESIS",
    "RETRIEVE_EVIDENCE",
    "RUN_READ_ONLY_EXPERIMENT",
    "VERIFY_AGAIN",
    "SEARCH_COUNTEREXAMPLE",
    "REFINE_DIMENSION",
    "STOP",
}
CONTRADICTION_TYPES = {
    "logical",
    "empirical",
    "causal",
    "scope",
    "temporal",
    "definition",
    "measurement",
}
CONTRADICTION_RESOLUTION_STATUSES = {
    "UNRESOLVED",
    "QUALIFIED",
    "RESOLVED",
    "SUPERSEDED",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bounded_score(value: int, label: str, *, signed: bool = False) -> int:
    score = int(value)
    lower = -SCORE_SCALE if signed else 0
    if not lower <= score <= SCORE_SCALE:
        raise ValueError(f"{label} must be {lower}..{SCORE_SCALE}")
    return score


def canonical_strings(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def stable_strings(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def canonical_inference_mode(value: str, *, allow_unspecified: bool = False) -> str:
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    normalized = INFERENCE_MODE_ALIASES.get(normalized, normalized)
    if normalized not in INFERENCE_MODES:
        raise ValueError(f"invalid reasoning inference mode: {value}")
    if normalized == "unspecified" and not allow_unspecified:
        raise ValueError("reasoning inference mode must be explicit")
    return normalized


def canonical_score_pairs(values: Iterable[Tuple[str, int]]) -> Tuple[Tuple[str, int], ...]:
    normalized: Dict[str, int] = {}
    for name, value in values:
        key = str(name)
        if not key:
            raise ValueError("score keys must be non-empty")
        normalized[key] = int(value)
    return tuple(sorted(normalized.items()))


@dataclass(frozen=True)
class ReasoningProblem:
    schema_version: int = 1
    problem_id: str = ""
    statement: str = ""
    goal: str = ""
    source_snapshot_hash: str = ""
    boundary_signature: str = ""
    dimension_signature: str = ""
    evidence_ids: Tuple[str, ...] = ()
    uncertainty_bp: int = 0
    difficulty_bp: int = 0
    mutually_exclusive_hypotheses: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("reasoning problem statement must be non-empty")
        if not self.goal.strip():
            raise ValueError("reasoning problem goal must be non-empty")
        bounded_score(self.uncertainty_bp, "problem uncertainty")
        bounded_score(self.difficulty_bp, "problem difficulty")
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningProblem":
        return cls(**dict(payload))


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    proposition: str
    prior_bp: int = 0
    posterior_bp: int = 0
    supporting_evidence: Tuple[str, ...] = ()
    conflicting_evidence: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    predictions: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    status: str = "ACTIVE"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id must be non-empty")
        if not self.proposition.strip():
            raise ValueError("hypothesis proposition must be non-empty")
        bounded_score(self.prior_bp, "hypothesis prior")
        bounded_score(self.posterior_bp, "hypothesis posterior")
        if self.status not in HYPOTHESIS_STATUSES:
            raise ValueError(f"invalid hypothesis status: {self.status}")
        for name in (
            "supporting_evidence",
            "conflicting_evidence",
            "assumptions",
            "predictions",
            "falsifiers",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Hypothesis":
        return cls(**dict(payload))


@dataclass(frozen=True)
class HypothesisUpdateRecord:
    schema_version: int = 1
    update_id: str = ""
    problem_id: str = ""
    hypothesis_id: str = ""
    operation: str = "BAYES_EVIDENCE_UPDATE"
    evidence_ids: Tuple[str, ...] = ()
    collision_ids: Tuple[str, ...] = ()
    polarity: str = "support"
    likelihood_if_true_bp: int = 0
    likelihood_if_false_bp: int = 0
    previous_posterior_bp: int = 0
    updated_posterior_bp: int = 0
    previous_status: str = "ACTIVE"
    updated_status: str = "ACTIVE"
    previous_hypothesis_signature: str = ""
    updated_hypothesis_signature: str = ""
    reason: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("hypothesis update schema_version must be 1")
        for name in (
            "problem_id",
            "hypothesis_id",
            "operation",
            "previous_hypothesis_signature",
            "updated_hypothesis_signature",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"hypothesis update {name} must be non-empty")
        if self.polarity not in {"support", "counterexample", "conflict"}:
            raise ValueError("hypothesis update polarity is invalid")
        for name in (
            "likelihood_if_true_bp",
            "likelihood_if_false_bp",
            "previous_posterior_bp",
            "updated_posterior_bp",
        ):
            bounded_score(getattr(self, name), name)
        if self.previous_status not in HYPOTHESIS_STATUSES:
            raise ValueError("hypothesis update previous status is invalid")
        if self.updated_status not in HYPOTHESIS_STATUSES:
            raise ValueError("hypothesis update updated status is invalid")
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "collision_ids", canonical_strings(self.collision_ids))
        material = {
            "schema_version": self.schema_version,
            "problem_id": self.problem_id,
            "hypothesis_id": self.hypothesis_id,
            "operation": self.operation,
            "evidence_ids": self.evidence_ids,
            "collision_ids": self.collision_ids,
            "polarity": self.polarity,
            "likelihood_if_true_bp": self.likelihood_if_true_bp,
            "likelihood_if_false_bp": self.likelihood_if_false_bp,
            "previous_posterior_bp": self.previous_posterior_bp,
            "updated_posterior_bp": self.updated_posterior_bp,
            "previous_status": self.previous_status,
            "updated_status": self.updated_status,
            "previous_hypothesis_signature": self.previous_hypothesis_signature,
            "updated_hypothesis_signature": self.updated_hypothesis_signature,
            "reason": self.reason,
        }
        expected_id = f"hypothesis-update:{stable_hash(material)}"
        if self.update_id and self.update_id != expected_id:
            raise ValueError("hypothesis update ID mismatch")
        object.__setattr__(self, "update_id", expected_id)
        expected_signature = stable_hash({**material, "update_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("hypothesis update signature mismatch")
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisUpdateRecord":
        return cls(**dict(payload))


@dataclass(frozen=True)
class HypothesisSet:
    schema_version: int = 1
    problem_id: str = ""
    hypotheses: Tuple[Hypothesis, ...] = ()
    max_hypotheses: int = 16
    mutually_exclusive: bool = False
    uncertainty_bp: int = 0
    evidence_ids: Tuple[str, ...] = ()
    update_ids: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("hypothesis set schema_version must be 1")
        if not self.problem_id.strip():
            raise ValueError("hypothesis set problem_id must be non-empty")
        maximum = int(self.max_hypotheses)
        if maximum < 1:
            raise ValueError("hypothesis set maximum must be positive")
        ordered = tuple(sorted(self.hypotheses, key=lambda item: item.hypothesis_id))
        if not ordered:
            raise ValueError("hypothesis set must contain at least one hypothesis")
        if len(ordered) > maximum:
            raise ValueError("hypothesis set exceeds its maximum")
        if len({item.hypothesis_id for item in ordered}) != len(ordered):
            raise ValueError("hypothesis set IDs must be unique")
        if self.mutually_exclusive:
            survivors = tuple(item for item in ordered if item.status != "FALSIFIED")
            expected_mass = SCORE_SCALE if survivors else 0
            if sum(item.posterior_bp for item in ordered) != expected_mass:
                raise ValueError(
                    "mutually exclusive hypothesis posteriors must sum to 10000 or zero when all are falsified"
                )
        bounded_score(self.uncertainty_bp, "hypothesis set uncertainty")
        object.__setattr__(self, "hypotheses", ordered)
        object.__setattr__(self, "max_hypotheses", maximum)
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "update_ids", canonical_strings(self.update_ids))
        material = {
            "schema_version": self.schema_version,
            "problem_id": self.problem_id,
            "hypotheses": tuple(asdict(item) for item in ordered),
            "max_hypotheses": maximum,
            "mutually_exclusive": self.mutually_exclusive,
            "uncertainty_bp": self.uncertainty_bp,
            "evidence_ids": self.evidence_ids,
            "update_ids": self.update_ids,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("hypothesis set signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisSet":
        values = dict(payload)
        values["hypotheses"] = tuple(
            Hypothesis.from_dict(item) for item in values.get("hypotheses", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class ReasoningNode:
    node_id: str
    kind: str
    content: str
    evidence_ids: Tuple[str, ...] = ()
    confidence_bp: int = 0
    path_id: str = ""
    validated: bool = False
    hypothetical: bool = False
    material: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("reasoning node ID must be non-empty")
        if self.kind not in NODE_KINDS:
            raise ValueError(f"invalid reasoning node kind: {self.kind}")
        if not self.content.strip():
            raise ValueError("reasoning node content must be non-empty")
        bounded_score(self.confidence_bp, "reasoning node confidence")
        if self.validated and self.kind != "premise":
            raise ValueError("only premise nodes may be marked validated")
        if self.material and self.kind not in {"conclusion", "decision"}:
            raise ValueError("only conclusion or decision nodes may be material")
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningNode":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    inference_id: str = ""
    inference_mode: str = "unspecified"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.edge_id or not self.source_id or not self.target_id:
            raise ValueError("reasoning edge IDs must be non-empty")
        if self.relation not in EDGE_RELATIONS:
            raise ValueError(f"invalid reasoning edge relation: {self.relation}")
        object.__setattr__(
            self,
            "inference_mode",
            canonical_inference_mode(self.inference_mode, allow_unspecified=True),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningEdge":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningTopology:
    schema_version: int = 2
    problem_id: str = ""
    nodes: Tuple[ReasoningNode, ...] = ()
    edges: Tuple[ReasoningEdge, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(sorted(self.nodes, key=lambda item: item.node_id)))
        object.__setattr__(self, "edges", tuple(sorted(self.edges, key=lambda item: item.edge_id)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningTopology":
        values = dict(payload)
        values["nodes"] = tuple(
            ReasoningNode.from_dict(item) for item in values.get("nodes", ())
        )
        values["edges"] = tuple(
            ReasoningEdge.from_dict(item) for item in values.get("edges", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class ReasoningStep:
    step_id: str
    claim: str
    premises: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    inference: str = "deductive"
    confidence_bp: int = 0
    assumptions: Tuple[str, ...] = ()
    falsifier: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("reasoning step ID must be non-empty")
        if not self.claim.strip():
            raise ValueError("reasoning step claim must be non-empty")
        object.__setattr__(self, "inference", canonical_inference_mode(self.inference))
        bounded_score(self.confidence_bp, "reasoning step confidence")
        object.__setattr__(self, "premises", stable_strings(self.premises))
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "assumptions", canonical_strings(self.assumptions))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningStep":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningPath:
    path_id: str
    perspective: str
    hypothesis_ids: Tuple[str, ...]
    steps: Tuple[ReasoningStep, ...]
    conclusion: str
    provider_confidence_bp: int = 0
    estimated_cost_bp: int = 0
    goal_relevance_bp: int = 0
    risk_bp: int = 0
    topology_node_ids: Tuple[str, ...] = ()
    topology_edge_ids: Tuple[str, ...] = ()
    structure_signature: str = ""
    diversity_bp: int = 0
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.path_id or not self.perspective:
            raise ValueError("reasoning path identity must be non-empty")
        if not self.steps:
            raise ValueError("reasoning path must contain at least one step")
        if not self.conclusion.strip():
            raise ValueError("reasoning path conclusion must be non-empty")
        for name in (
            "provider_confidence_bp",
            "estimated_cost_bp",
            "goal_relevance_bp",
            "risk_bp",
            "diversity_bp",
        ):
            bounded_score(getattr(self, name), name)
        object.__setattr__(self, "hypothesis_ids", canonical_strings(self.hypothesis_ids))
        object.__setattr__(self, "topology_node_ids", canonical_strings(self.topology_node_ids))
        object.__setattr__(self, "topology_edge_ids", canonical_strings(self.topology_edge_ids))
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("reasoning path step IDs must be unique")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningPath":
        values = dict(payload)
        values["steps"] = tuple(
            ReasoningStep.from_dict(item) for item in values.get("steps", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class VerifierReport:
    report_id: str
    path_id: str
    step_scores: Tuple[Tuple[str, int], ...] = ()
    failures: Tuple[str, ...] = ()
    contradictions: Tuple[str, ...] = ()
    unsupported_nodes: Tuple[str, ...] = ()
    missing_assumptions: Tuple[str, ...] = ()
    premise_validity_bp: int = 0
    evidence_support_bp: int = 0
    inference_quality_bp: int = 0
    consistency_bp: int = 0
    completeness_bp: int = 0
    weakest_step_bp: int = 0
    score_bp: int = 0
    verdict: str = "REJECT"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.report_id or not self.path_id:
            raise ValueError("verifier report identity must be non-empty")
        bounded_score(self.score_bp, "verifier score")
        for name in (
            "premise_validity_bp",
            "evidence_support_bp",
            "inference_quality_bp",
            "consistency_bp",
            "completeness_bp",
            "weakest_step_bp",
        ):
            bounded_score(getattr(self, name), name)
        if self.verdict not in VERIFIER_VERDICTS:
            raise ValueError(f"invalid verifier verdict: {self.verdict}")
        pairs = canonical_score_pairs(self.step_scores)
        if any(not 0 <= value <= SCORE_SCALE for _, value in pairs):
            raise ValueError("verifier step scores must be 0..10000")
        object.__setattr__(self, "step_scores", pairs)
        object.__setattr__(self, "failures", canonical_strings(self.failures))
        object.__setattr__(self, "contradictions", canonical_strings(self.contradictions))
        object.__setattr__(self, "unsupported_nodes", canonical_strings(self.unsupported_nodes))
        object.__setattr__(
            self,
            "missing_assumptions",
            canonical_strings(self.missing_assumptions),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerifierReport":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FalsifierReport:
    report_id: str
    path_id: str
    searched_falsifiers: Tuple[str, ...] = ()
    counterexamples: Tuple[str, ...] = ()
    contradicted_step_ids: Tuple[str, ...] = ()
    unresolved_defeat_conditions: Tuple[str, ...] = ()
    unresolved_defeat_evidence_ids: Tuple[str, ...] = ()
    alternative_explanations: Tuple[str, ...] = ()
    boundary_cases: Tuple[str, ...] = ()
    reversed_causal_directions: Tuple[str, ...] = ()
    invalid_invariants: Tuple[str, ...] = ()
    evidence_reversal_conditions: Tuple[str, ...] = ()
    severity_bp: int = 0
    survival_bp: int = 0
    residual_uncertainty_bp: int = 0
    verdict: str = "REJECT"
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.report_id or not self.path_id:
            raise ValueError("falsifier report identity must be non-empty")
        bounded_score(self.survival_bp, "falsifier survival")
        bounded_score(self.severity_bp, "falsifier severity")
        bounded_score(self.residual_uncertainty_bp, "falsifier residual uncertainty")
        if self.verdict not in FALSIFIER_VERDICTS:
            raise ValueError(f"invalid falsifier verdict: {self.verdict}")
        for name in (
            "searched_falsifiers",
            "counterexamples",
            "contradicted_step_ids",
            "unresolved_defeat_conditions",
            "unresolved_defeat_evidence_ids",
            "alternative_explanations",
            "boundary_cases",
            "reversed_causal_directions",
            "invalid_invariants",
            "evidence_reversal_conditions",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FalsifierReport":
        return cls(**dict(payload))


@dataclass(frozen=True)
class DiversityConfiguration:
    schema_version: int = 1
    config_id: str = "oiec-sr-diversity-v1"
    hypothesis_weight: int = 25
    evidence_weight: int = 25
    inference_weight: int = 20
    assumption_weight: int = 10
    falsifier_weight: int = 10
    conclusion_weight: int = 10
    duplicate_threshold_bp: int = 9_001
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("diversity configuration schema_version must be 1")
        if not self.config_id.strip():
            raise ValueError("diversity configuration ID must be non-empty")
        weights = (
            self.hypothesis_weight,
            self.evidence_weight,
            self.inference_weight,
            self.assumption_weight,
            self.falsifier_weight,
            self.conclusion_weight,
        )
        if any(not 0 <= int(value) <= 100 for value in weights):
            raise ValueError("diversity weights must be 0..100")
        if sum(weights) != 100:
            raise ValueError("diversity weights must sum to 100")
        bounded_score(self.duplicate_threshold_bp, "diversity duplicate threshold")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("diversity configuration signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiversityConfiguration":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ScoreConfiguration:
    schema_version: int = 1
    config_id: str = "oiec-sr-score-v1"
    verifier_weight: int = 30
    evidence_weight: int = 25
    consistency_weight: int = 15
    falsifier_weight: int = 15
    goal_weight: int = 10
    diversity_weight: int = 5
    uncertainty_penalty: int = 15
    compute_penalty: int = 5
    minimum_survivor_bp: int = 5_000
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("score configuration schema_version must be 1")
        if not self.config_id.strip():
            raise ValueError("score configuration ID must be non-empty")
        weights = (
            self.verifier_weight,
            self.evidence_weight,
            self.consistency_weight,
            self.falsifier_weight,
            self.goal_weight,
            self.diversity_weight,
        )
        if any(not 0 <= int(value) <= 100 for value in weights):
            raise ValueError("score configuration weights must be 0..100")
        if sum(weights) != 100:
            raise ValueError("positive score configuration weights must sum to 100")
        if any(
            not 0 <= int(value) <= 100
            for value in (self.uncertainty_penalty, self.compute_penalty)
        ):
            raise ValueError("score configuration penalties must be 0..100")
        bounded_score(self.minimum_survivor_bp, "minimum survivor score")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("score configuration signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScoreConfiguration":
        return cls(**dict(payload))


@dataclass(frozen=True)
class SynthesisResult:
    schema_version: int = 1
    winning_path_id: str = ""
    synthesized_path_id: str = ""
    source_path_ids: Tuple[str, ...] = ()
    accepted_node_ids: Tuple[str, ...] = ()
    rejected_node_ids: Tuple[str, ...] = ()
    merged_conclusion: str = ""
    remaining_uncertainties: Tuple[str, ...] = ()
    confidence_bp: int = 0
    verifier_report_id: str = ""
    topology_signature: str = ""
    verified: bool = False
    fallback_used: bool = False
    failure_reasons: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("synthesis schema_version must be 1")
        bounded_score(self.confidence_bp, "synthesis confidence")
        for name in (
            "source_path_ids",
            "accepted_node_ids",
            "rejected_node_ids",
            "remaining_uncertainties",
            "failure_reasons",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))
        if self.merged_conclusion and not self.winning_path_id:
            raise ValueError("synthesis conclusion requires a winning path")
        if self.winning_path_id and self.winning_path_id not in self.source_path_ids:
            raise ValueError("synthesis winning path must be a source path")
        if self.verified and not self.verifier_report_id:
            raise ValueError("verified synthesis requires a verifier report")
        if self.verified and not self.synthesized_path_id:
            raise ValueError("verified synthesis requires a synthesized path ID")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("synthesis signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SynthesisResult":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ContradictionRecord:
    schema_version: int = 1
    contradiction_id: str = ""
    left_claim_id: str = ""
    right_claim_id: str = ""
    evidence_left: Tuple[str, ...] = ()
    evidence_right: Tuple[str, ...] = ()
    conflict_type: str = "logical"
    severity_bp: int = 0
    resolution_status: str = "UNRESOLVED"
    resolution_evidence_ids: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.conflict_type not in CONTRADICTION_TYPES:
            raise ValueError(f"invalid contradiction type: {self.conflict_type}")
        if self.resolution_status not in CONTRADICTION_RESOLUTION_STATUSES:
            raise ValueError(
                f"invalid contradiction resolution status: {self.resolution_status}"
            )
        if not self.left_claim_id or not self.right_claim_id:
            raise ValueError("contradiction claim IDs must be non-empty")
        bounded_score(self.severity_bp, "contradiction severity")
        for name in ("evidence_left", "evidence_right", "resolution_evidence_ids"):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))
        material = asdict(self)
        material.pop("contradiction_id", None)
        material.pop("signature", None)
        identity_material = {
            key: value
            for key, value in material.items()
            if key not in {"resolution_status", "resolution_evidence_ids"}
        }
        expected_id = f"contradiction:{stable_hash(identity_material)}"
        if self.contradiction_id and self.contradiction_id != expected_id:
            raise ValueError("contradiction ID mismatch")
        object.__setattr__(self, "contradiction_id", expected_id)
        expected_signature = stable_hash({**material, "contradiction_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("contradiction signature mismatch")
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContradictionRecord":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningContext:
    schema_version: int = 1
    problem_hash: str = ""
    constraints: Tuple[str, ...] = ()
    hypothesis_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    topology_node_ids: Tuple[str, ...] = ()
    collision_ids: Tuple[str, ...] = ()
    unresolved_questions: Tuple[str, ...] = ()
    candidate_summaries: Tuple[Tuple[str, str], ...] = ()
    max_items: int = 128
    max_chars_per_item: int = 512
    max_total_chars: int = 16_384
    signature: str = ""

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("reasoning context max_items must be positive")
        if self.max_chars_per_item < 1 or self.max_total_chars < 1:
            raise ValueError("reasoning context character bounds must be positive")
        for name in (
            "constraints",
            "hypothesis_ids",
            "evidence_ids",
            "topology_node_ids",
            "collision_ids",
            "unresolved_questions",
        ):
            values = canonical_strings(getattr(self, name))
            if len(values) > self.max_items:
                raise ValueError(f"reasoning context {name} exceeds the item bound")
            if any(len(value) > self.max_chars_per_item for value in values):
                raise ValueError(f"reasoning context {name} exceeds the character bound")
            object.__setattr__(self, name, values)
        summaries = tuple(
            sorted(
                {
                    (str(path_id), str(summary))
                    for path_id, summary in self.candidate_summaries
                    if str(path_id) and str(summary)
                }
            )
        )
        if len(summaries) > self.max_items:
            raise ValueError("reasoning context candidate summaries exceed the item bound")
        if any(
            len(path_id) > self.max_chars_per_item or len(summary) > self.max_chars_per_item
            for path_id, summary in summaries
        ):
            raise ValueError("reasoning context candidate summary exceeds the character bound")
        object.__setattr__(self, "candidate_summaries", summaries)
        total_chars = sum(
            len(value)
            for name in (
                "constraints",
                "hypothesis_ids",
                "evidence_ids",
                "topology_node_ids",
                "collision_ids",
                "unresolved_questions",
            )
            for value in getattr(self, name)
        ) + sum(len(path_id) + len(summary) for path_id, summary in summaries)
        if total_chars > self.max_total_chars:
            raise ValueError("reasoning context exceeds the total character bound")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("reasoning context signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningContext":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningOperationChoice:
    schema_version: int = 1
    operation: str = "STOP"
    expected_quality_gain_bp: int = 0
    cost_bp: int = 0
    value_bp: int = 0
    requires_iurm: bool = False
    read_only: bool = True
    signature: str = ""

    def __post_init__(self) -> None:
        if self.operation not in REASONING_OPERATIONS:
            raise ValueError(f"invalid reasoning operation: {self.operation}")
        bounded_score(self.expected_quality_gain_bp, "operation expected gain")
        bounded_score(self.cost_bp, "operation cost")
        if not -SCORE_SCALE <= int(self.value_bp) <= SCORE_SCALE:
            raise ValueError("operation value must be -10000..10000")
        if self.operation == "RUN_READ_ONLY_EXPERIMENT" and not self.read_only:
            raise ValueError("SR experiments must remain read-only")
        if self.operation == "REFINE_DIMENSION" and not self.requires_iurm:
            raise ValueError("dimension refinement must require IURM")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("reasoning operation signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningOperationChoice":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningMetrics:
    path_id: str
    evidence_support_bp: int = 0
    verifier_bp: int = 0
    consistency_bp: int = 0
    falsifier_bp: int = 0
    goal_relevance_bp: int = 0
    diversity_bp: int = 0
    uncertainty_bp: int = 0
    risk_bp: int = 0
    cost_bp: int = 0
    total_score_bp: int = 0
    score_config_id: str = ""
    score_config_hash: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.path_id:
            raise ValueError("reasoning metrics path_id must be non-empty")
        for name in (
            "evidence_support_bp",
            "verifier_bp",
            "consistency_bp",
            "falsifier_bp",
            "goal_relevance_bp",
            "diversity_bp",
            "uncertainty_bp",
            "risk_bp",
            "cost_bp",
        ):
            bounded_score(getattr(self, name), name)
        bounded_score(self.total_score_bp, "reasoning total score", signed=True)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningMetrics":
        return cls(**dict(payload))


@dataclass(frozen=True)
class CandidateSet:
    schema_version: int = 1
    problem_id: str = ""
    paths: Tuple[ReasoningPath, ...] = ()
    verifier_reports: Tuple[VerifierReport, ...] = ()
    falsifier_reports: Tuple[FalsifierReport, ...] = ()
    metrics: Tuple[ReasoningMetrics, ...] = ()
    selected_path_id: str = ""
    surviving_path_ids: Tuple[str, ...] = ()
    rejected_path_ids: Tuple[str, ...] = ()
    synthesized_conclusion: str = ""
    synthesis_source_path_ids: Tuple[str, ...] = ()
    synthesis: SynthesisResult | None = None
    score_config_id: str = ""
    score_config_hash: str = ""
    diversity_config_hash: str = ""
    ablation_id: str = "full_sr"
    ablation_config_hash: str = ""
    contradiction_ids: Tuple[str, ...] = ()
    hypothesis_updates: Tuple[HypothesisUpdateRecord, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", tuple(sorted(self.paths, key=lambda item: item.path_id)))
        object.__setattr__(
            self,
            "verifier_reports",
            tuple(sorted(self.verifier_reports, key=lambda item: item.path_id)),
        )
        object.__setattr__(
            self,
            "falsifier_reports",
            tuple(sorted(self.falsifier_reports, key=lambda item: item.path_id)),
        )
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics, key=lambda item: item.path_id)))
        object.__setattr__(self, "surviving_path_ids", canonical_strings(self.surviving_path_ids))
        object.__setattr__(self, "rejected_path_ids", canonical_strings(self.rejected_path_ids))
        object.__setattr__(
            self,
            "synthesis_source_path_ids",
            canonical_strings(self.synthesis_source_path_ids),
        )
        object.__setattr__(self, "contradiction_ids", canonical_strings(self.contradiction_ids))
        object.__setattr__(
            self,
            "hypothesis_updates",
            tuple(sorted(self.hypothesis_updates, key=lambda item: item.update_id)),
        )
        if self.synthesis is not None:
            if self.synthesized_conclusion and (
                self.synthesized_conclusion != self.synthesis.merged_conclusion
            ):
                raise ValueError("candidate synthesis projection mismatch")
            object.__setattr__(self, "synthesized_conclusion", self.synthesis.merged_conclusion)
            object.__setattr__(self, "synthesis_source_path_ids", self.synthesis.source_path_ids)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateSet":
        values = dict(payload)
        values["paths"] = tuple(ReasoningPath.from_dict(item) for item in values.get("paths", ()))
        values["verifier_reports"] = tuple(
            VerifierReport.from_dict(item) for item in values.get("verifier_reports", ())
        )
        values["falsifier_reports"] = tuple(
            FalsifierReport.from_dict(item) for item in values.get("falsifier_reports", ())
        )
        values["metrics"] = tuple(
            ReasoningMetrics.from_dict(item) for item in values.get("metrics", ())
        )
        synthesis = values.get("synthesis")
        values["synthesis"] = SynthesisResult.from_dict(synthesis) if synthesis else None
        values["hypothesis_updates"] = tuple(
            HypothesisUpdateRecord.from_dict(item)
            for item in values.get("hypothesis_updates", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class ReasoningBudget:
    schema_version: int = 1
    max_hypotheses: int = 16
    minimum_candidates: int = 1
    maximum_candidates: int = 16
    candidate_count: int = 4
    max_steps_per_path: int = 8
    max_branch_factor: int = 16
    max_topology_nodes: int = 256
    max_topology_edges: int = 512
    max_provider_calls: int = 16
    max_generation_attempts: int = 8
    verifier_count: int = 4
    falsifier_count: int = 2
    max_verifier_passes: int = 2
    max_falsifier_passes: int = 2
    max_tokens: int = 12_000
    max_tool_calls: int = 20
    max_context_items: int = 128
    operation_costs_bp: Tuple[Tuple[str, int], ...] = ()
    max_compute_bp: int = SCORE_SCALE
    minimum_voi_bp: int = 100
    signature: str = ""

    def __post_init__(self) -> None:
        positive = (
            self.max_hypotheses,
            self.minimum_candidates,
            self.maximum_candidates,
            self.candidate_count,
            self.max_steps_per_path,
            self.max_branch_factor,
            self.max_topology_nodes,
            self.max_topology_edges,
            self.max_provider_calls,
            self.max_generation_attempts,
            self.verifier_count,
            self.max_verifier_passes,
            self.max_falsifier_passes,
            self.max_tokens,
            self.max_tool_calls,
            self.max_context_items,
        )
        if any(int(value) < 1 for value in positive):
            raise ValueError("reasoning budget limits must be positive")
        if not self.minimum_candidates <= self.candidate_count <= self.maximum_candidates:
            raise ValueError("candidate count must fit the reasoning budget")
        if self.verifier_count > self.candidate_count:
            raise ValueError("verifier count cannot exceed candidate count")
        if self.max_generation_attempts < self.candidate_count:
            raise ValueError("generation attempts cannot be below candidate count")
        if not 0 <= self.falsifier_count <= self.verifier_count:
            raise ValueError("falsifier count must fit verified candidates")
        bounded_score(self.max_compute_bp, "maximum reasoning compute")
        bounded_score(self.minimum_voi_bp, "minimum value of information")
        costs = canonical_score_pairs(self.operation_costs_bp)
        if any(name not in REASONING_OPERATIONS for name, _ in costs):
            raise ValueError("reasoning budget contains an unknown operation cost")
        if any(not 0 <= value <= SCORE_SCALE for _, value in costs):
            raise ValueError("reasoning operation costs must be 0..10000")
        object.__setattr__(self, "operation_costs_bp", costs)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningBudget":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ReasoningCertificate:
    schema_version: int = 2
    problem_hash: str = ""
    boundary_signature: str = ""
    dimension_signature: str = ""
    hypothesis_signature: str = ""
    topology_signature: str = ""
    candidate_set_signature: str = ""
    synthesis_signature: str = ""
    score_config_id: str = ""
    score_config_hash: str = ""
    ablation_id: str = "full_sr"
    ablation_config_hash: str = ""
    active_hypothesis_ids: Tuple[str, ...] = ()
    candidate_count: int = 0
    surviving_candidate_count: int = 0
    winning_candidate_id: str = ""
    winning_path_id: str = ""
    verifier_report_ids: Tuple[str, ...] = ()
    falsifier_report_ids: Tuple[str, ...] = ()
    evidence_coverage_bp: int = 0
    verifier_score_bp: int = 0
    falsification_score_bp: int = 0
    contradiction_count: int = 0
    unresolved_contradiction_ids: Tuple[str, ...] = ()
    uncertainty_before_bp: int = 0
    uncertainty_after_bp: int = 0
    disagreement_bp: int = 0
    residual_risk_bp: int = 0
    compute_spent_bp: int = 0
    unresolved_assumptions: Tuple[str, ...] = ()
    reasoning_topology_hash: str = ""
    derived_confidence_bp: int = 0
    decision: str = "STOP_UNRESOLVED"
    terminal_state: str = "INSUFFICIENT_EVIDENCE"
    reasons: Tuple[str, ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if self.decision not in REASONING_DECISIONS:
            raise ValueError(f"invalid reasoning decision: {self.decision}")
        if self.terminal_state not in REASONING_TERMINAL_STATES:
            raise ValueError(f"invalid reasoning terminal state: {self.terminal_state}")
        if (
            int(self.candidate_count) < 0
            or int(self.surviving_candidate_count) < 0
            or int(self.contradiction_count) < 0
        ):
            raise ValueError("reasoning certificate counts cannot be negative")
        if self.surviving_candidate_count > self.candidate_count:
            raise ValueError("surviving candidate count cannot exceed candidate count")
        for name in (
            "evidence_coverage_bp",
            "verifier_score_bp",
            "falsification_score_bp",
            "uncertainty_before_bp",
            "uncertainty_after_bp",
            "disagreement_bp",
            "residual_risk_bp",
            "compute_spent_bp",
            "derived_confidence_bp",
        ):
            bounded_score(getattr(self, name), name)
        for name in (
            "active_hypothesis_ids",
            "verifier_report_ids",
            "falsifier_report_ids",
            "unresolved_assumptions",
            "unresolved_contradiction_ids",
            "reasons",
        ):
            object.__setattr__(self, name, canonical_strings(getattr(self, name)))
        if self.winning_candidate_id and self.winning_path_id:
            if self.winning_candidate_id != self.winning_path_id:
                raise ValueError("reasoning certificate winning path projections conflict")
        winning = self.winning_path_id or self.winning_candidate_id
        object.__setattr__(self, "winning_candidate_id", winning)
        object.__setattr__(self, "winning_path_id", winning)
        if self.reasoning_topology_hash and self.topology_signature:
            if self.reasoning_topology_hash != self.topology_signature:
                raise ValueError("reasoning certificate topology projections conflict")
        topology = self.topology_signature or self.reasoning_topology_hash
        object.__setattr__(self, "reasoning_topology_hash", topology)
        object.__setattr__(self, "topology_signature", topology)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningCertificate":
        return cls(**dict(payload))


__all__ = [
    "CandidateSet",
    "CONTRADICTION_RESOLUTION_STATUSES",
    "CONTRADICTION_TYPES",
    "EDGE_RELATIONS",
    "FALSIFIER_VERDICTS",
    "HYPOTHESIS_STATUSES",
    "INFERENCE_MODES",
    "INFERENCE_MODE_ALIASES",
    "Hypothesis",
    "HypothesisSet",
    "HypothesisUpdateRecord",
    "NODE_KINDS",
    "REASONING_DECISIONS",
    "REASONING_OPERATIONS",
    "REASONING_TERMINAL_STATES",
    "ContradictionRecord",
    "DiversityConfiguration",
    "ReasoningBudget",
    "ReasoningCertificate",
    "ReasoningContext",
    "ReasoningEdge",
    "ReasoningMetrics",
    "ReasoningNode",
    "ReasoningPath",
    "ReasoningProblem",
    "ReasoningOperationChoice",
    "ReasoningStep",
    "ReasoningTopology",
    "SCORE_SCALE",
    "ScoreConfiguration",
    "SynthesisResult",
    "VERIFIER_VERDICTS",
    "VerifierReport",
    "FalsifierReport",
    "bounded_score",
    "canonical_inference_mode",
    "canonical_json",
    "canonical_strings",
    "stable_hash",
]
