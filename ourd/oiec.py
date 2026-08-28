from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence, TYPE_CHECKING

from .errors import PolicyError
from .models import (
    AttemptKey,
    AuthorityManifest,
    BoundaryState,
    DimensionBudget,
    EONAction,
    EvidenceArtifact,
    FiniteEvidenceState,
    GovernanceRecord,
    ProgressCertificate,
    RISK_ORDER,
    RuntimeState,
    SCORE_SCALE,
)

if TYPE_CHECKING:
    from .models import GateDecision
    from .policy import PolicyEngine
    from .workspace import Workspace


DIMENSION_WEIGHTS = {
    "information": 35,
    "goal": 30,
    "orthogonality": 20,
    "cost": 8,
    "risk": 7,
}
COLLISION_WEIGHTS = {
    "surprise": 20,
    "invariant": 25,
    "boundary": 25,
    "dimension": 10,
    "repeat": 10,
    "conflict": 10,
}
MIN_GOAL_PROGRESS_BP = 100
MIN_RISK_PROGRESS_BP = 100
MIN_BOUNDARY_PROGRESS_BP = 100
MIN_INFORMATION_GAIN_BP = 100


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _score(value: int, label: str, *, signed: bool = False) -> int:
    score = int(value)
    lower = -SCORE_SCALE if signed else 0
    if not lower <= score <= SCORE_SCALE:
        raise PolicyError(f"{label} must be {lower}..{SCORE_SCALE}")
    return score


def _canonical_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def membership_uncertainty_bp(probability_bp: int) -> int:
    probability_bp = _score(probability_bp, "boundary membership")
    return SCORE_SCALE - abs((2 * probability_bp) - SCORE_SCALE)


def binary_entropy(probability: float) -> float:
    probability = float(probability)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must lie in [0, 1]")
    if probability in {0.0, 1.0}:
        return 0.0
    return -probability * math.log2(probability) - (1.0 - probability) * math.log2(
        1.0 - probability
    )


def dimension_utility(
    information_bp: int,
    goal_bp: int,
    orthogonality_bp: int,
    cost_bp: int,
    risk_bp: int,
) -> int:
    information_bp = _score(information_bp, "dimension information")
    goal_bp = _score(goal_bp, "dimension goal contribution")
    orthogonality_bp = _score(orthogonality_bp, "dimension orthogonality")
    cost_bp = _score(cost_bp, "dimension cost")
    risk_bp = _score(risk_bp, "dimension risk")
    raw = (
        DIMENSION_WEIGHTS["information"] * information_bp
        + DIMENSION_WEIGHTS["goal"] * goal_bp
        + DIMENSION_WEIGHTS["orthogonality"] * orthogonality_bp
        - DIMENSION_WEIGHTS["cost"] * cost_bp
        - DIMENSION_WEIGHTS["risk"] * risk_bp
    )
    return raw // 100


@dataclass(frozen=True)
class DimensionCandidate:
    name: str
    information_bp: int = 0
    goal_bp: int = 0
    orthogonality_bp: int = 0
    cost_bp: int = 0
    risk_bp: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise PolicyError("dimension name must be non-empty")
        for field_name in (
            "information_bp",
            "goal_bp",
            "orthogonality_bp",
            "cost_bp",
            "risk_bp",
        ):
            _score(getattr(self, field_name), field_name)

    @property
    def utility_bp(self) -> int:
        return dimension_utility(
            self.information_bp,
            self.goal_bp,
            self.orthogonality_bp,
            self.cost_bp,
            self.risk_bp,
        )


@dataclass(frozen=True)
class TransitionMetrics:
    uncertainty_bp: int = 0
    goal_loss_bp: int = 0
    residual_risk_bp: int = 0
    boundary_uncertainty_bp: int = 0
    expected_information_gain_bp: int = 0
    novel_experiment: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "uncertainty_bp",
            "goal_loss_bp",
            "residual_risk_bp",
            "boundary_uncertainty_bp",
            "expected_information_gain_bp",
        ):
            _score(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class PreparedTransition:
    boundary: BoundaryState
    budget: DimensionBudget
    evidence: FiniteEvidenceState
    attempt: AttemptKey
    effective_risk: str
    gate_decision_id: str = ""


def build_boundary(
    governance: GovernanceRecord,
    authority: AuthorityManifest,
    source_snapshot_hash: str,
    memberships: Optional[Mapping[str, int]] = None,
) -> BoundaryState:
    if not governance.established:
        raise PolicyError("established mutation governance is required")
    if governance.authority_hash != authority.authority_hash:
        raise PolicyError("governance authority hash mismatch")
    membership_values = memberships or {}
    semantic_objects = _canonical_strings(governance.objects)
    semantic_relations = _canonical_strings(governance.relations)
    membership_items = []
    for item in (*semantic_objects, *semantic_relations):
        probability = _score(
            int(membership_values.get(item, SCORE_SCALE)),
            f"boundary membership for {item!r}",
        )
        membership_items.append((item, probability))

    uncertainty = 0
    if membership_items:
        uncertainty = sum(
            membership_uncertainty_bp(probability)
            for _, probability in membership_items
        ) // len(membership_items)

    payload = {
        "authority_hash": authority.authority_hash,
        "source_snapshot_hash": source_snapshot_hash,
        "semantic_objects": semantic_objects,
        "semantic_relations": semantic_relations,
        "authority_allowed": _canonical_strings(authority.allowed_paths),
        "authority_forbidden": _canonical_strings(authority.forbidden_paths),
        "governance_allowed": _canonical_strings(governance.allowed_paths),
        "governance_excluded": _canonical_strings(governance.excluded_scope),
        "dimensions": _canonical_strings(governance.dimensions),
        "membership": tuple(membership_items),
        "uncertainty": uncertainty,
    }
    return BoundaryState(
        authority_hash=authority.authority_hash,
        source_snapshot_hash=source_snapshot_hash,
        semantic_objects=semantic_objects,
        semantic_relations=semantic_relations,
        authority_allowed_patterns=payload["authority_allowed"],
        authority_forbidden_patterns=payload["authority_forbidden"],
        governance_allowed_patterns=payload["governance_allowed"],
        governance_excluded_patterns=payload["governance_excluded"],
        experimental_dimensions=payload["dimensions"],
        semantic_membership_bp=tuple(membership_items),
        boundary_uncertainty_bp=uncertainty,
        signature=stable_hash(payload),
    )


def require_boundary_target(
    workspace: "Workspace",
    boundary: BoundaryState,
    target: str,
) -> str:
    target = workspace.require_scope(
        target,
        list(boundary.authority_allowed_patterns),
        list(boundary.authority_forbidden_patterns),
    )
    if not boundary.governance_allowed_patterns:
        raise PolicyError("established mutation governance has no operational boundary")
    return workspace.require_scope(
        target,
        list(boundary.governance_allowed_patterns),
        list(boundary.governance_excluded_patterns),
    )


def require_dimension_action(
    budget: DimensionBudget,
    varied_dimensions: Sequence[str],
) -> None:
    varied = _canonical_strings(varied_dimensions)
    if len(varied) > budget.max_interaction_order:
        raise PolicyError("IURM interaction-order limit exceeded")
    missing = set(varied) - set(budget.selected_dimensions)
    if missing:
        raise PolicyError(f"action varies non-admitted dimensions: {sorted(missing)!r}")


def empty_evidence_state(atoms: Iterable[str]) -> FiniteEvidenceState:
    atom_tuple = _canonical_strings(atoms)
    payload = {
        "atoms": atom_tuple,
        "present_mask": 0,
        "conflict_mask": 0,
        "quality_bp": (0,) * len(atom_tuple),
        "representative_ids": ("",) * len(atom_tuple),
    }
    return FiniteEvidenceState(**payload, signature=stable_hash(payload))


def update_evidence(
    state: FiniteEvidenceState,
    *,
    atom: str,
    artifact_id: str,
    quality_bp: int,
    conflict: bool = False,
) -> FiniteEvidenceState:
    if atom not in state.atoms:
        raise PolicyError(f"evidence atom outside finite universe: {atom}")
    quality_bp = _score(quality_bp, "evidence quality")
    index = state.atoms.index(atom)
    bit = 1 << index
    qualities = list(state.quality_bp)
    representatives = list(state.representative_ids)
    old_quality = qualities[index]
    if quality_bp > old_quality:
        qualities[index] = quality_bp
        representatives[index] = artifact_id
    elif quality_bp == old_quality and artifact_id and (
        not representatives[index] or artifact_id < representatives[index]
    ):
        representatives[index] = artifact_id
    present_mask = state.present_mask | bit
    conflict_mask = state.conflict_mask | (bit if conflict else 0)
    payload = {
        "atoms": state.atoms,
        "present_mask": present_mask,
        "conflict_mask": conflict_mask,
        "quality_bp": tuple(qualities),
        "representative_ids": tuple(representatives),
    }
    return FiniteEvidenceState(**payload, signature=stable_hash(payload))


def evidence_mass(state: FiniteEvidenceState) -> int:
    return sum(
        quality
        for index, quality in enumerate(state.quality_bp)
        if state.present_mask & (1 << index)
    )


def make_attempt_key(
    *,
    source_snapshot_hash: str,
    action_id: str,
    evidence_signature: str,
    boundary_signature: str,
    dimension_signature: str,
) -> AttemptKey:
    material = {
        "source_snapshot_hash": source_snapshot_hash,
        "action_id": action_id,
        "evidence_signature": evidence_signature,
        "boundary_signature": boundary_signature,
        "dimension_signature": dimension_signature,
    }
    return AttemptKey(**material, digest=stable_hash(material))


def certify_progress(
    *,
    evidence_gain_bp: int,
    uncertainty_reduction_bp: int,
    goal_improvement_bp: int,
    residual_risk_reduction_bp: int,
    boundary_uncertainty_reduction_bp: int,
    expected_information_gain_bp: int,
    novel_evidence: bool,
    novel_experiment: bool,
    terminal: bool,
) -> ProgressCertificate:
    evidence_gain_bp = _score(evidence_gain_bp, "evidence gain")
    uncertainty_reduction_bp = _score(
        uncertainty_reduction_bp, "uncertainty reduction", signed=True
    )
    goal_improvement_bp = _score(goal_improvement_bp, "goal improvement", signed=True)
    residual_risk_reduction_bp = _score(
        residual_risk_reduction_bp, "residual risk reduction", signed=True
    )
    boundary_uncertainty_reduction_bp = _score(
        boundary_uncertainty_reduction_bp,
        "boundary uncertainty reduction",
        signed=True,
    )
    expected_information_gain_bp = _score(
        expected_information_gain_bp, "expected information gain"
    )
    reasons = []
    if novel_evidence and evidence_gain_bp > 0:
        reasons.append("novel_evidence")
    if goal_improvement_bp >= MIN_GOAL_PROGRESS_BP:
        reasons.append("goal_improvement")
    if residual_risk_reduction_bp >= MIN_RISK_PROGRESS_BP:
        reasons.append("risk_reduction")
    if boundary_uncertainty_reduction_bp >= MIN_BOUNDARY_PROGRESS_BP:
        reasons.append("boundary_resolution")
    if novel_experiment and expected_information_gain_bp >= MIN_INFORMATION_GAIN_BP:
        reasons.append("discriminating_experiment")
    if terminal:
        reasons.append("terminal")
    reasons = sorted(reasons)
    payload = {
        "evidence_gain_bp": evidence_gain_bp,
        "uncertainty_reduction_bp": uncertainty_reduction_bp,
        "goal_improvement_bp": goal_improvement_bp,
        "residual_risk_reduction_bp": residual_risk_reduction_bp,
        "boundary_uncertainty_reduction_bp": boundary_uncertainty_reduction_bp,
        "expected_information_gain_bp": expected_information_gain_bp,
        "novel_evidence": bool(novel_evidence),
        "novel_experiment": bool(novel_experiment),
        "terminal": bool(terminal),
        "accepted": bool(reasons),
        "reasons": tuple(reasons),
    }
    return ProgressCertificate(**payload, signature=stable_hash(payload))


def collision_severity_bp(
    *,
    surprise_bp: int,
    invariant_bp: int,
    boundary_bp: int,
    dimension_bp: int,
    repeat_bp: int,
    conflict_bp: int,
    critical_boundary: bool = False,
    critical_invariant: bool = False,
) -> int:
    if critical_boundary or critical_invariant:
        return SCORE_SCALE
    components = {
        "surprise": _score(surprise_bp, "collision surprise"),
        "invariant": _score(invariant_bp, "collision invariant violation"),
        "boundary": _score(boundary_bp, "collision boundary violation"),
        "dimension": _score(dimension_bp, "collision dimension leakage"),
        "repeat": _score(repeat_bp, "collision repeat pressure"),
        "conflict": _score(conflict_bp, "collision evidence conflict"),
    }
    value = sum(COLLISION_WEIGHTS[name] * score for name, score in components.items()) // 100
    return min(SCORE_SCALE, max(0, value))


def collision_severity(
    *,
    surprise: float,
    invariant_violation: float,
    boundary_violation: float,
    dimensional_leakage: float,
    retry_repetition: float,
    evidence_conflict: float,
    unauthorized: bool = False,
    invariant_breach: bool = False,
) -> float:
    values = (
        surprise,
        invariant_violation,
        boundary_violation,
        dimensional_leakage,
        retry_repetition,
        evidence_conflict,
    )
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("collision components must lie in [0, 1]")
    return collision_severity_bp(
        surprise_bp=round(surprise * SCORE_SCALE),
        invariant_bp=round(invariant_violation * SCORE_SCALE),
        boundary_bp=round(boundary_violation * SCORE_SCALE),
        dimension_bp=round(dimensional_leakage * SCORE_SCALE),
        repeat_bp=round(retry_repetition * SCORE_SCALE),
        conflict_bp=round(evidence_conflict * SCORE_SCALE),
        critical_boundary=unauthorized,
        critical_invariant=invariant_breach,
    ) / SCORE_SCALE


def quantize_continuous(
    minimum: float,
    maximum: float,
    levels: int,
) -> tuple[float, ...]:
    minimum = float(minimum)
    maximum = float(maximum)
    levels = int(levels)
    if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum < minimum:
        raise ValueError("invalid quantization interval")
    if levels < 2:
        raise ValueError("quantization requires at least two levels")
    step = (maximum - minimum) / (levels - 1)
    return tuple(minimum + step * index for index in range(levels))


def boundary_proximity_risk(boundary_membership_bp: int) -> int:
    return membership_uncertainty_bp(boundary_membership_bp)


def dimension_leakage(expected: Iterable[str], observed: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(observed) - set(expected)))


def convergence_score(
    *,
    goal_loss_bp: int,
    unresolved_uncertainty_bp: int,
    residual_risk_bp: int,
) -> int:
    values = (
        _score(goal_loss_bp, "goal loss"),
        _score(unresolved_uncertainty_bp, "unresolved uncertainty"),
        _score(residual_risk_bp, "residual risk"),
    )
    return SCORE_SCALE - sum(values) // len(values)


class BoundedTransitionKernel:
    def __init__(
        self,
        *,
        max_active_objects: int = 64,
        max_active_relations: int = 256,
        max_active_dimensions: int = 16,
        max_active_hypotheses: int = 16,
        max_active_evidence_atoms: int = 128,
        max_quantization_levels: int = 17,
        max_interaction_order: int = 1,
        max_candidate_actions: int = 16,
        max_decomposition_depth: int = 8,
        max_branch_factor: int = 16,
        max_retries: int = 1,
        collision_threshold_bp: int = 5_000,
    ):
        self.max_active_objects = int(max_active_objects)
        self.max_active_relations = int(max_active_relations)
        self.max_active_dimensions = int(max_active_dimensions)
        self.max_active_hypotheses = int(max_active_hypotheses)
        self.max_active_evidence_atoms = int(max_active_evidence_atoms)
        self.max_quantization_levels = int(max_quantization_levels)
        self.max_interaction_order = int(max_interaction_order)
        self.max_candidate_actions = int(max_candidate_actions)
        self.max_decomposition_depth = int(max_decomposition_depth)
        self.max_branch_factor = int(max_branch_factor)
        self.max_retries = int(max_retries)
        self.collision_threshold_bp = _score(
            collision_threshold_bp, "collision threshold"
        )
        DimensionBudget(
            max_active_objects=self.max_active_objects,
            max_active_relations=self.max_active_relations,
            max_active_dimensions=self.max_active_dimensions,
            max_active_hypotheses=self.max_active_hypotheses,
            max_quantization_levels=self.max_quantization_levels,
            max_interaction_order=self.max_interaction_order,
            max_candidate_actions=self.max_candidate_actions,
            max_active_evidence_atoms=self.max_active_evidence_atoms,
            max_decomposition_depth=self.max_decomposition_depth,
            max_branch_factor=self.max_branch_factor,
            max_retries_per_attempt=max(0, self.max_retries),
        )

    def derive_boundary(
        self,
        *,
        runtime: RuntimeState,
        source_snapshot_hash: str,
        memberships: Optional[Mapping[str, int]] = None,
    ) -> BoundaryState:
        return build_boundary(
            runtime.governance,
            runtime.authority,
            source_snapshot_hash,
            memberships,
        )

    def derive_dimension_budget(
        self,
        *,
        boundary: BoundaryState,
        authority: AuthorityManifest,
        dimension_scores: Optional[Mapping[str, int]] = None,
    ) -> DimensionBudget:
        scores = dimension_scores or {}
        candidates = []
        for dimension in boundary.experimental_dimensions:
            score = int(scores.get(dimension, 0))
            if not -SCORE_SCALE <= score <= SCORE_SCALE:
                raise PolicyError(f"invalid dimension utility: {dimension}")
            candidates.append((dimension, score))
        ranked = sorted(candidates, key=lambda item: (-item[1], item[0]))
        selected = tuple(name for name, _ in ranked[: self.max_active_dimensions])
        retry_limit = min(self.max_retries, max(0, authority.max_retries_per_action))
        payload = {
            "selected_dimensions": selected,
            "dimension_utility_bp": tuple(ranked),
            "max_active_objects": self.max_active_objects,
            "max_active_relations": self.max_active_relations,
            "max_active_dimensions": self.max_active_dimensions,
            "max_active_hypotheses": self.max_active_hypotheses,
            "max_quantization_levels": self.max_quantization_levels,
            "max_active_evidence_atoms": self.max_active_evidence_atoms,
            "max_interaction_order": self.max_interaction_order,
            "max_candidate_actions": self.max_candidate_actions,
            "max_decomposition_depth": self.max_decomposition_depth,
            "max_branch_factor": self.max_branch_factor,
            "max_retries_per_attempt": retry_limit,
        }
        return DimensionBudget(**payload, signature=stable_hash(payload))

    @staticmethod
    def _action_atoms(action: EONAction) -> tuple[str, ...]:
        return _canonical_strings((*action.evidence, *action.required_tests))

    def project_evidence(
        self,
        *,
        runtime: RuntimeState,
        action: EONAction,
        budget: DimensionBudget,
        evidence: Optional[Mapping[str, EvidenceArtifact]] = None,
        gate: Optional["GateDecision"] = None,
    ) -> FiniteEvidenceState:
        atoms = self._action_atoms(action)
        if len(atoms) > budget.max_active_evidence_atoms:
            raise PolicyError("evidence universe exceeds the finite OIEC cap")
        projected = empty_evidence_state(atoms)
        artifacts = evidence if evidence is not None else runtime.evidence_registry
        eligible = [
            artifact
            for _, artifact in sorted(artifacts.items())
            if artifact.action_id == action.action_id
            and artifact.source_snapshot_hash == action.source_snapshot_hash
        ]
        for artifact in eligible:
            if artifact.polarity not in {"support", "counterexample", "conflict"}:
                raise PolicyError(f"invalid evidence polarity: {artifact.polarity}")
            requirements = set(artifact.requirement_ids)
            if artifact.description in atoms:
                requirements.add(artifact.description)
            if artifact.kind in atoms:
                requirements.add(artifact.kind)
            for atom in sorted(requirements.intersection(atoms)):
                projected = update_evidence(
                    projected,
                    atom=atom,
                    artifact_id=artifact.artifact_id,
                    quality_bp=artifact.quality_bp,
                    conflict=artifact.polarity == "conflict",
                )
        if gate is not None and gate.action_id == action.action_id:
            gate_artifacts = [
                runtime.evidence_registry[artifact_id]
                for artifact_id in sorted(gate.evidence_ids)
                if artifact_id in runtime.evidence_registry
            ]
            for atom in sorted(set(gate.satisfied_requirements).intersection(atoms)):
                candidates = [
                    artifact
                    for artifact in gate_artifacts
                    if artifact.action_id == action.action_id
                    and artifact.source_snapshot_hash == action.source_snapshot_hash
                ]
                if candidates:
                    best_quality = max(artifact.quality_bp for artifact in candidates)
                    representative = min(
                        artifact.artifact_id
                        for artifact in candidates
                        if artifact.quality_bp == best_quality
                    )
                    projected = update_evidence(
                        projected,
                        atom=atom,
                        artifact_id=representative,
                        quality_bp=best_quality,
                        conflict=any(artifact.polarity == "conflict" for artifact in candidates),
                    )
        return projected

    @staticmethod
    def make_attempt_key(
        *,
        source_snapshot_hash: str,
        action_id: str,
        evidence_signature: str,
        boundary_signature: str,
        dimension_signature: str,
    ) -> AttemptKey:
        return make_attempt_key(
            source_snapshot_hash=source_snapshot_hash,
            action_id=action_id,
            evidence_signature=evidence_signature,
            boundary_signature=boundary_signature,
            dimension_signature=dimension_signature,
        )

    @staticmethod
    def validate_action(
        *,
        workspace: "Workspace",
        policy: "PolicyEngine",
        boundary: BoundaryState,
        budget: DimensionBudget,
        action: EONAction,
        varied_dimensions: Sequence[str],
    ) -> str:
        for target in action.targets:
            policy.require_oiec_boundary_target(workspace, boundary, target)
        policy.require_oiec_dimension_action(budget, varied_dimensions)
        effective_risk = policy.effective_risk(
            action.model_risk,
            action.operation,
            action.summary,
            action.targets,
            action.command_capabilities,
        )
        if RISK_ORDER[action.effective_risk] < RISK_ORDER[effective_risk]:
            raise PolicyError("OIEC cannot lower the PolicyEngine effective risk floor")
        return effective_risk

    def prepare(
        self,
        *,
        runtime: RuntimeState,
        workspace: "Workspace",
        policy: "PolicyEngine",
        action: EONAction,
        varied_dimensions: Sequence[str] = (),
        evidence: Optional[Mapping[str, EvidenceArtifact]] = None,
        dimension_scores: Optional[Mapping[str, int]] = None,
        memberships: Optional[Mapping[str, int]] = None,
        gate: Optional["GateDecision"] = None,
        expected_snapshot_hash: str = "",
    ) -> PreparedTransition:
        current_snapshot = workspace.snapshot_hash()
        expected_snapshot = expected_snapshot_hash or action.source_snapshot_hash
        if current_snapshot != expected_snapshot:
            raise PolicyError("OIEC source snapshot mismatch")
        if action.authority_hash != runtime.authority.authority_hash:
            raise PolicyError("OIEC action authority hash mismatch")
        boundary = self.derive_boundary(
            runtime=runtime,
            source_snapshot_hash=current_snapshot,
            memberships=memberships,
        )
        budget = self.derive_dimension_budget(
            boundary=boundary,
            authority=runtime.authority,
            dimension_scores=dimension_scores,
        )
        if len(boundary.semantic_objects) > budget.max_active_objects:
            raise PolicyError("semantic object count exceeds the OIEC active-state cap")
        if len(boundary.semantic_relations) > budget.max_active_relations:
            raise PolicyError("semantic relation count exceeds the OIEC active-state cap")
        effective_risk = self.validate_action(
            workspace=workspace,
            policy=policy,
            boundary=boundary,
            budget=budget,
            action=action,
            varied_dimensions=varied_dimensions,
        )
        if action.effective_risk != "L0":
            if gate is None or gate.action_id != action.action_id:
                raise PolicyError("OIEC requires the existing action evidence gate")
            if gate.verdict not in {"APPROVE", "APPROVE_WITH_LIMITS"}:
                raise PolicyError("OIEC evidence gate is not approving")
        finite_evidence = self.project_evidence(
            runtime=runtime,
            action=action,
            budget=budget,
            evidence=evidence,
            gate=gate,
        )
        attempt = self.make_attempt_key(
            source_snapshot_hash=current_snapshot,
            action_id=action.action_id,
            evidence_signature=finite_evidence.signature,
            boundary_signature=boundary.signature,
            dimension_signature=budget.signature,
        )
        failed = runtime.failed_attempts.get(attempt.digest, 0)
        if failed > budget.max_retries_per_attempt:
            raise PolicyError("OIEC no-blind-retry gate blocked attempt")
        return PreparedTransition(
            boundary=boundary,
            budget=budget,
            evidence=finite_evidence,
            attempt=attempt,
            effective_risk=effective_risk,
            gate_decision_id=gate.decision_id if gate is not None else "",
        )

    @staticmethod
    def measure_collision(**components: Any) -> int:
        return collision_severity_bp(**components)

    @staticmethod
    def certify_progress(**metrics: Any) -> ProgressCertificate:
        return certify_progress(**metrics)

    def accept_observation(
        self,
        *,
        runtime: RuntimeState,
        prepared: PreparedTransition,
        evidence_after: FiniteEvidenceState,
        collision_severity_bp: int,
        metrics_before: TransitionMetrics,
        metrics_after: TransitionMetrics,
        dimension_scores: Optional[Mapping[str, int]] = None,
        memberships: Optional[Mapping[str, int]] = None,
        terminal: bool = False,
    ) -> ProgressCertificate:
        severity = _score(collision_severity_bp, "collision severity")
        evidence_gain = max(
            0,
            evidence_mass(evidence_after) - evidence_mass(prepared.evidence),
        )
        if severity >= self.collision_threshold_bp:
            runtime.failed_attempts[prepared.attempt.digest] = (
                runtime.failed_attempts.get(prepared.attempt.digest, 0) + 1
            )
        certificate = certify_progress(
            evidence_gain_bp=min(SCORE_SCALE, evidence_gain),
            uncertainty_reduction_bp=(
                metrics_before.uncertainty_bp - metrics_after.uncertainty_bp
            ),
            goal_improvement_bp=(
                metrics_before.goal_loss_bp - metrics_after.goal_loss_bp
            ),
            residual_risk_reduction_bp=(
                metrics_before.residual_risk_bp - metrics_after.residual_risk_bp
            ),
            boundary_uncertainty_reduction_bp=(
                prepared.boundary.boundary_uncertainty_bp
                - metrics_after.boundary_uncertainty_bp
            ),
            expected_information_gain_bp=metrics_after.expected_information_gain_bp,
            novel_evidence=evidence_after.signature != prepared.evidence.signature,
            novel_experiment=metrics_after.novel_experiment,
            terminal=terminal,
        )
        if not certificate.accepted:
            raise PolicyError("OIEC transition has no progress certificate")
        next_boundary = self.derive_boundary(
            runtime=runtime,
            source_snapshot_hash=prepared.attempt.source_snapshot_hash,
            memberships=memberships,
        )
        next_budget = self.derive_dimension_budget(
            boundary=next_boundary,
            authority=runtime.authority,
            dimension_scores=dimension_scores,
        )
        runtime.boundary_state = next_boundary
        runtime.dimension_budget = next_budget
        runtime.finite_evidence = evidence_after
        runtime.last_progress = certificate
        runtime.transition_index += 1
        return certificate


__all__ = [
    "AttemptKey",
    "BoundaryState",
    "BoundedTransitionKernel",
    "DimensionBudget",
    "DimensionCandidate",
    "FiniteEvidenceState",
    "PreparedTransition",
    "ProgressCertificate",
    "TransitionMetrics",
    "binary_entropy",
    "boundary_proximity_risk",
    "build_boundary",
    "canonical_json",
    "certify_progress",
    "collision_severity",
    "collision_severity_bp",
    "convergence_score",
    "dimension_leakage",
    "dimension_utility",
    "empty_evidence_state",
    "evidence_mass",
    "make_attempt_key",
    "membership_uncertainty_bp",
    "quantize_continuous",
    "require_boundary_target",
    "require_dimension_action",
    "stable_hash",
    "update_evidence",
]
