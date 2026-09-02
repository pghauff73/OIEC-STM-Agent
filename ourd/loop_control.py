from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .models import ProgressCertificate, RuntimeState, SCORE_SCALE
from .oiec import certify_progress, stable_hash


_WS = re.compile(r"\s+")
_VOLATILE_KEYS = {
    "action_id",
    "artifact_id",
    "call_id",
    "collision_id",
    "decision_id",
    "event_id",
    "evidence_ids",
    "reference_message_id",
    "run_id",
    "source_event_id",
    "transaction_id",
}


def _semantic_value(value: Any, *, key: str = "") -> Any:
    """Project model-supplied material into a bounded semantic identity."""

    if key in _VOLATILE_KEYS or key.endswith("_id"):
        return "<identity>"
    if isinstance(value, Mapping):
        return {
            str(name): _semantic_value(item, key=str(name))
            for name, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_semantic_value(item, key=key) for item in value]
    if isinstance(value, str):
        text = _WS.sub(" ", value).strip()
        if len(text) > 1024:
            return {
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "length": len(text),
            }
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def semantic_step_signature(calls: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    material = [
        {"name": str(name), "args": _semantic_value(dict(arguments))}
        for name, arguments in calls
    ]
    return stable_hash(material)


def _evidence_atom(artifact: Any) -> str:
    return stable_hash(
        {
            "kind": artifact.kind,
            "description": artifact.description,
            "sha256": artifact.sha256,
            "source_snapshot_hash": artifact.source_snapshot_hash,
            "path": artifact.path,
            "command_capability": artifact.command_capability,
            "success": artifact.success,
            "requirement_ids": sorted(set(artifact.requirement_ids)),
            "quality_bp": int(artifact.quality_bp),
            "polarity": artifact.polarity,
        }
    )


def _collision_atom(collision: Any) -> str:
    return stable_hash(
        {
            "expected": _semantic_value(collision.expected),
            "observed": _semantic_value(collision.observed),
            "objects": sorted(set(collision.objects)),
            "boundary": collision.boundary,
            "active_dimension": collision.active_dimension,
            "frozen_dimensions": sorted(set(collision.frozen_dimensions)),
            "severity_bp": int(collision.severity_bp),
        }
    )


def _stable_evidence_refs(state: RuntimeState, evidence_ids: Sequence[str]) -> list[str]:
    return sorted(
        _evidence_atom(state.evidence_registry[evidence_id])
        for evidence_id in evidence_ids
        if evidence_id in state.evidence_registry
    )


def _control_atoms(state: RuntimeState) -> tuple[str, ...]:
    atoms: list[str] = []
    governance = state.governance
    if governance.established:
        atoms.append(
            "governance:"
            + stable_hash(
                {
                    "goal": governance.goal,
                    "constraints": sorted(set(governance.constraints)),
                    "assumptions": sorted(set(governance.assumptions)),
                    "uncertainties": sorted(set(governance.uncertainties)),
                    "objects": sorted(set(governance.objects)),
                    "relations": sorted(set(governance.relations)),
                    "boundaries": sorted(set(governance.boundaries)),
                    "excluded_scope": sorted(set(governance.excluded_scope)),
                    "allowed_paths": sorted(set(governance.allowed_paths)),
                    "dimensions": sorted(set(governance.dimensions)),
                    "invariants": sorted(set(governance.invariants)),
                    "authority_hash": governance.authority_hash,
                }
            )
        )
    if state.pending_action is not None:
        action = state.pending_action
        atoms.append(
            "action:"
            + stable_hash(
                {
                    "summary": action.summary,
                    "operation": action.operation,
                    "targets": sorted(set(action.targets)),
                    "preconditions": sorted(set(action.preconditions)),
                    "postconditions": sorted(set(action.postconditions)),
                    "preserve": sorted(set(action.preserve)),
                    "evidence": sorted(set(action.evidence)),
                    "model_risk": action.model_risk,
                    "effective_risk": action.effective_risk,
                    "authority_hash": action.authority_hash,
                    "source_snapshot_hash": action.source_snapshot_hash,
                    "candidate_hash": action.candidate_hash,
                    "command_capabilities": sorted(set(action.command_capabilities)),
                    "commands": list(action.commands),
                    "required_tests": sorted(set(action.required_tests)),
                    "varied_dimensions": sorted(set(action.varied_dimensions)),
                    "use_limit": int(action.use_limit),
                }
            )
        )
    if state.last_gate is not None:
        gate = state.last_gate
        atoms.append(
            "gate:"
            + stable_hash(
                {
                    "proposed_verdict": gate.proposed_verdict,
                    "verdict": gate.verdict,
                    "evidence_categories": {
                        name: _stable_evidence_refs(state, values)
                        for name, values in sorted(gate.evidence_categories.items())
                    },
                    "satisfied_requirements": sorted(set(gate.satisfied_requirements)),
                    "uncovered": sorted(set(gate.uncovered)),
                    "limits": _semantic_value(gate.limits),
                    "reason": gate.reason,
                }
            )
        )
    transaction_rank = {
        "PREPARED": 1,
        "APPLIED": 2,
        "VERIFIED": 3,
        "FINALIZED": 4,
        "ROLLED_BACK": 4,
        "DISCARDED": 4,
        "FAILED": 4,
    }
    for record in sorted(
        state.transactions.values(),
        key=lambda item: (
            item.candidate_hash,
            item.operation,
            tuple(sorted(item.targets)),
            item.status,
        ),
    ):
        atoms.append(
            "transaction:"
            + stable_hash(
                {
                    "operation": record.operation,
                    "targets": sorted(set(record.targets)),
                    "source_snapshot_hash": record.source_snapshot_hash,
                    "candidate_hash": record.candidate_hash,
                    "status": record.status,
                    "status_rank": transaction_rank.get(record.status, 0),
                    "applied_snapshot_hash": record.applied_snapshot_hash,
                    "verification_evidence": _stable_evidence_refs(
                        state, record.verification_evidence_ids
                    ),
                }
            )
        )
    if state.boundary_state is not None:
        atoms.append("boundary:" + state.boundary_state.signature)
    if state.dimension_budget is not None:
        atoms.append("dimensions:" + state.dimension_budget.signature)
    if state.changed_files:
        atoms.append("changed-files:" + stable_hash(sorted(set(state.changed_files))))
    return tuple(sorted(set(atoms)))


def _hypothesis_atoms(state: RuntimeState) -> tuple[tuple[str, ...], tuple[str, ...]]:
    definitions: list[str] = []
    evidence_links: list[str] = []
    if state.hypothesis_state is None:
        return (), ()
    for hypothesis in state.hypothesis_state.hypotheses:
        definitions.append(
            stable_hash(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "proposition": hypothesis.proposition,
                    "assumptions": hypothesis.assumptions,
                    "predictions": hypothesis.predictions,
                    "falsifiers": hypothesis.falsifiers,
                    "verification_status": hypothesis.verification_status,
                }
            )
        )
        for link in hypothesis.evidence_links:
            evidence_links.append(
                stable_hash(
                    {
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "evidence_fingerprint": link.evidence_fingerprint,
                        "relation": link.relation,
                        "quality_bp": link.quality_bp,
                        "source_snapshot_hash": link.source_snapshot_hash,
                        "relation_epistemic_status": link.relation_epistemic_status,
                    }
                )
            )
    return tuple(sorted(set(definitions))), tuple(sorted(set(evidence_links)))


@dataclass(frozen=True)
class VerifiedProjection:
    """Deterministic system projection, never populated directly by model prose."""

    workspace_snapshot_hash: str
    evidence_atoms: tuple[str, ...]
    collision_atoms: tuple[str, ...]
    control_atoms: tuple[str, ...]
    hypothesis_definition_atoms: tuple[str, ...] = ()
    hypothesis_evidence_atoms: tuple[str, ...] = ()
    active_evidence_atoms: tuple[str, ...] = ()
    boundary_uncertainty_bp: int = 0
    signature: str = ""


@dataclass(frozen=True)
class TransitionAssessment:
    certificate: ProgressCertificate
    allowed: bool
    terminal_state: str
    reason: str
    cycle_kind: str
    period: int
    step_signature: str
    before_signature: str
    after_signature: str
    new_evidence_count: int
    new_collision_count: int
    new_control_count: int
    new_hypothesis_definition_count: int
    new_hypothesis_evidence_count: int
    control_only: bool
    control_only_streak: int
    max_control_only_progress: int

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "certificate": asdict(self.certificate)}


def verified_projection(
    state: RuntimeState,
    workspace_snapshot_hash: str,
    active_evidence_ids: Sequence[str] = (),
) -> VerifiedProjection:
    evidence_atoms = tuple(
        sorted({_evidence_atom(artifact) for artifact in state.evidence_registry.values()})
    )
    collision_atoms = tuple(
        sorted({_collision_atom(collision) for collision in state.collisions})
    )
    control_atoms = _control_atoms(state)
    hypothesis_definitions, hypothesis_evidence = _hypothesis_atoms(state)
    active_evidence_atoms = tuple(
        sorted(
            {
                _evidence_atom(state.evidence_registry[evidence_id])
                for evidence_id in active_evidence_ids
                if evidence_id in state.evidence_registry
            }
        )
    )
    boundary_uncertainty = (
        int(state.boundary_state.boundary_uncertainty_bp)
        if state.boundary_state is not None
        else 0
    )
    material = {
        "workspace_snapshot_hash": workspace_snapshot_hash,
        "evidence_atoms": evidence_atoms,
        "collision_atoms": collision_atoms,
        "control_atoms": control_atoms,
        "hypothesis_definition_atoms": hypothesis_definitions,
        "hypothesis_evidence_atoms": hypothesis_evidence,
        "active_evidence_atoms": active_evidence_atoms,
        "boundary_uncertainty_bp": boundary_uncertainty,
    }
    return VerifiedProjection(
        workspace_snapshot_hash=workspace_snapshot_hash,
        evidence_atoms=evidence_atoms,
        collision_atoms=collision_atoms,
        control_atoms=control_atoms,
        hypothesis_definition_atoms=hypothesis_definitions,
        hypothesis_evidence_atoms=hypothesis_evidence,
        active_evidence_atoms=active_evidence_atoms,
        boundary_uncertainty_bp=boundary_uncertainty,
        signature=stable_hash(material),
    )


class LoopProgressController:
    """Mandatory progress, control-budget and bounded semantic-cycle controller."""

    def __init__(
        self,
        *,
        window: int = 12,
        max_period: int = 4,
        max_control_only_progress: int = 2,
        initial_control_only_streak: int = 0,
    ) -> None:
        self.window = max(4, min(int(window), 64))
        self.max_period = max(1, min(int(max_period), self.window // 2))
        self.max_control_only_progress = max(0, min(int(max_control_only_progress), 16))
        self.control_only_streak = max(0, int(initial_control_only_streak))
        self._steps: list[str] = []
        self._states: list[str] = []
        self._assessments: list[TransitionAssessment] = []

    def project(
        self,
        state: RuntimeState,
        workspace_snapshot_hash: str,
        active_evidence_ids: Sequence[str] = (),
    ) -> VerifiedProjection:
        return verified_projection(
            state,
            workspace_snapshot_hash,
            active_evidence_ids,
        )

    def assess(
        self,
        *,
        before: VerifiedProjection,
        after: VerifiedProjection,
        step_signature: str,
        terminal: bool = False,
    ) -> TransitionAssessment:
        new_persisted_evidence = set(after.evidence_atoms) - set(before.evidence_atoms)
        new_active_evidence = (
            set(after.active_evidence_atoms) - set(before.active_evidence_atoms)
        )
        new_evidence = new_persisted_evidence | new_active_evidence
        new_collisions = set(after.collision_atoms) - set(before.collision_atoms)
        new_control = set(after.control_atoms) - set(before.control_atoms)
        new_hypothesis_definitions = (
            set(after.hypothesis_definition_atoms) - set(before.hypothesis_definition_atoms)
        )
        new_hypothesis_evidence = (
            set(after.hypothesis_evidence_atoms) - set(before.hypothesis_evidence_atoms)
        )

        evidence_count = len(new_evidence)
        collision_count = len(new_collisions)
        control_count = len(new_control)
        hypothesis_definition_count = len(new_hypothesis_definitions)
        hypothesis_evidence_count = len(new_hypothesis_evidence)
        evidence_gain_bp = min(
            SCORE_SCALE,
            (evidence_count * 1_000) + (collision_count * 500),
        )
        # This is a bookkeeping metric only. The relation between grounded
        # evidence and a hypothesis remains model-proposed, so it does not by
        # itself count as verified epistemic progress.
        hypothesis_resolution_bp = min(SCORE_SCALE, hypothesis_evidence_count * 1_000)
        boundary_reduction = (
            int(before.boundary_uncertainty_bp) - int(after.boundary_uncertainty_bp)
        )
        has_epistemic_progress = bool(
            evidence_count or collision_count or boundary_reduction >= 100
        )
        has_control_progress = bool(
            control_count or hypothesis_definition_count or hypothesis_evidence_count
        )
        control_only = bool(has_control_progress and not has_epistemic_progress)

        base_certificate = certify_progress(
            evidence_gain_bp=evidence_gain_bp,
            uncertainty_reduction_bp=0,
            goal_improvement_bp=0,
            residual_risk_reduction_bp=0,
            boundary_uncertainty_reduction_bp=boundary_reduction,
            expected_information_gain_bp=0,
            novel_evidence=bool(evidence_count or collision_count),
            novel_experiment=False,
            terminal=terminal,
        )
        reasons = set(base_certificate.reasons)
        if hypothesis_resolution_bp > 0:
            reasons.add("hypothesis_bookkeeping")

        if terminal:
            self.control_only_streak = 0
        elif control_only:
            self.control_only_streak += 1
        elif has_epistemic_progress:
            self.control_only_streak = 0

        accepted = bool(base_certificate.accepted)
        if control_only and self.control_only_streak <= self.max_control_only_progress:
            reasons.add("bounded_control_progress")
            accepted = True
        if control_only and self.control_only_streak > self.max_control_only_progress:
            accepted = False

        certificate = replace(
            base_certificate,
            hypothesis_resolution_bp=hypothesis_resolution_bp,
            accepted=accepted,
            reasons=tuple(sorted(reasons)),
            signature="",
        )
        certificate = replace(
            certificate,
            signature=stable_hash(
                {
                    "certificate": {
                        key: value
                        for key, value in asdict(certificate).items()
                        if key != "signature"
                    },
                    "before": before.signature,
                    "after": after.signature,
                    "step": step_signature,
                    "control_only_streak": self.control_only_streak,
                    "max_control_only_progress": self.max_control_only_progress,
                }
            ),
        )

        cycle_kind = ""
        period = 0
        reason = "verified progress accepted"
        allowed = bool(certificate.accepted)
        terminal_state = "CONTINUE"

        if terminal:
            allowed = True
            terminal_state = "SOLUTION_OR_MODEL_FINAL"
            reason = "terminal response recorded; model output remains unverified unless evidence supports it"
        elif control_only and self.control_only_streak > self.max_control_only_progress:
            allowed = False
            cycle_kind = "CONTROL_ONLY_BUDGET_EXHAUSTED"
            terminal_state = "CYCLE_STOP"
            reason = (
                f"control-only progress streak {self.control_only_streak} exceeded bounded allowance "
                f"{self.max_control_only_progress}; new verified evidence is required"
            )
        elif not certificate.accepted:
            allowed = False
            cycle_kind = "NO_VERIFIED_PROGRESS"
            terminal_state = "CYCLE_STOP"
            reason = "nonterminal autonomous step produced no verified epistemic or bounded control progress"
        else:
            recent_states = self._states[-self.window :]
            if after.signature in recent_states and after.signature != before.signature:
                allowed = False
                cycle_kind = "VERIFIED_STATE_CYCLE"
                terminal_state = "CYCLE_STOP"
                reason = "verified system state returned to a previously observed state"
            else:
                candidate_steps = [*self._steps[-self.window :], step_signature]
                candidate_assessments = [*self._assessments[-self.window :]]
                for candidate_period in range(1, self.max_period + 1):
                    if len(candidate_steps) < candidate_period * 2:
                        continue
                    if (
                        candidate_steps[-candidate_period:]
                        != candidate_steps[-2 * candidate_period : -candidate_period]
                    ):
                        continue
                    comparison = candidate_assessments[-(2 * candidate_period - 1) :]
                    comparison_epistemic = sum(
                        item.new_evidence_count + item.new_collision_count
                        for item in comparison
                    )
                    if evidence_count + collision_count + comparison_epistemic == 0:
                        allowed = False
                        cycle_kind = "SEMANTIC_PERIODIC_CYCLE"
                        period = candidate_period
                        terminal_state = "CYCLE_STOP"
                        reason = (
                            "semantic tool/action pattern repeated without new positive verified epistemic evidence"
                        )
                        break

        assessment = TransitionAssessment(
            certificate=certificate,
            allowed=allowed,
            terminal_state=terminal_state,
            reason=reason,
            cycle_kind=cycle_kind,
            period=period,
            step_signature=step_signature,
            before_signature=before.signature,
            after_signature=after.signature,
            new_evidence_count=evidence_count,
            new_collision_count=collision_count,
            new_control_count=control_count,
            new_hypothesis_definition_count=hypothesis_definition_count,
            new_hypothesis_evidence_count=hypothesis_evidence_count,
            control_only=control_only,
            control_only_streak=self.control_only_streak,
            max_control_only_progress=self.max_control_only_progress,
        )
        self._steps.append(step_signature)
        self._states.append(after.signature)
        self._assessments.append(assessment)
        self._steps = self._steps[-self.window :]
        self._states = self._states[-self.window :]
        self._assessments = self._assessments[-self.window :]
        return assessment

    def exhaust_budget(
        self,
        *,
        projection: VerifiedProjection,
        step_signature: str,
        maximum_steps: int,
    ) -> TransitionAssessment:
        assessment = self.assess(
            before=projection,
            after=projection,
            step_signature=step_signature,
            terminal=False,
        )
        stopped = replace(
            assessment,
            allowed=False,
            terminal_state="CYCLE_STOP",
            reason=(
                f"bounded autonomous step budget exhausted after {int(maximum_steps)} steps; "
                "synthesize the verified observations without further tool use"
            ),
            cycle_kind="COMPUTE_BUDGET_EXHAUSTED",
            period=0,
        )
        self._assessments[-1] = stopped
        return stopped


def model_belief_record(
    *,
    step: int,
    output_text: str,
    calls: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    text = output_text or ""
    step_signature = semantic_step_signature(calls)
    return {
        "step": int(step),
        "epistemic_status": "UNVERIFIED_MODEL_BELIEF",
        "output_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "output_text_length": len(text),
        "proposed_tool_names": [name for name, _ in calls],
        "semantic_step_signature": step_signature,
        "note": "model prose, confidence, assumptions, hypotheses and tool proposals are not verified system facts",
    }
