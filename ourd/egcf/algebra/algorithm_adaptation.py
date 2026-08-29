from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .retrieval_explanation import RetrievalExplanation


ALGORITHM_ADAPTATION_VERSION = "saa-controlled-algorithm-adaptation-v1"
MAX_ADAPTATION_STEPS = 16
ALLOWED_ADAPTATION_DIMENSIONS = {
    "MATHEMATICAL_INPUT_SEMANTICS",
    "MATHEMATICAL_OUTPUT_SHAPE",
    "MATHEMATICAL_DOMAIN",
    "MATHEMATICAL_CONTRACT",
    "REASONING_INPUT_SEMANTICS",
    "REASONING_OUTPUT_SEMANTICS",
    "REASONING_APPLICABILITY",
    "REASONING_INVARIANTS",
    "REASONING_EVIDENCE_CAPABILITY",
    "REASONING_TERMINATION_BUDGET",
    "REASONING_CONTRACT",
    "BOUNDARY_CONTRACT",
    "INVARIANT_CONTRACT",
    "DYNAMICS_CONTRACT",
    "EVIDENCE_CONTRACT",
    "MISSING_MATHEMATICAL_ALGORITHM",
    "MISSING_REASONING_ALGORITHM",
}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split())


@dataclass(frozen=True)
class AdaptationStep:
    index: int
    component: str
    dimension: str
    base_algorithm_id: str
    current_contract: str
    target_contract: str
    proposed_change: Mapping[str, Any]
    step_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "component": self.component,
            "dimension": self.dimension,
            "base_algorithm_id": self.base_algorithm_id,
            "current_contract": self.current_contract,
            "target_contract": self.target_contract,
            "proposed_change": dict(self.proposed_change),
            "step_signature": self.step_signature,
        }


@dataclass(frozen=True)
class ControlledAdaptationPlan:
    schema_version: int
    adaptation_version: str
    source_explanation_signature: str
    steps: Tuple[AdaptationStep, ...]
    one_dimension_per_step: bool
    qualification_required: bool
    canonical_reuse_eligible: bool
    plan_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adaptation_version": self.adaptation_version,
            "source_explanation_signature": self.source_explanation_signature,
            "steps": [item.to_dict() for item in self.steps],
            "one_dimension_per_step": self.one_dimension_per_step,
            "qualification_required": self.qualification_required,
            "canonical_reuse_eligible": self.canonical_reuse_eligible,
            "plan_signature": self.plan_signature,
        }


@dataclass(frozen=True)
class AdaptedAlgorithmCandidate:
    schema_version: int
    adaptation_version: str
    base_algorithm_id: str
    component: str
    changed_dimension: str
    change_material: Mapping[str, Any]
    parent_candidate_signature: str
    candidate_signature: str
    epistemic_status: str
    qualification_required: bool
    canonical_reuse_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adaptation_version": self.adaptation_version,
            "base_algorithm_id": self.base_algorithm_id,
            "component": self.component,
            "changed_dimension": self.changed_dimension,
            "change_material": dict(self.change_material),
            "parent_candidate_signature": self.parent_candidate_signature,
            "candidate_signature": self.candidate_signature,
            "epistemic_status": self.epistemic_status,
            "qualification_required": self.qualification_required,
            "canonical_reuse_eligible": self.canonical_reuse_eligible,
        }


def build_controlled_adaptation_plan(
    explanation: RetrievalExplanation,
    *,
    selected_mathematical_algorithm_id: str | None = None,
    selected_reasoning_id: str | None = None,
) -> ControlledAdaptationPlan:
    if not isinstance(explanation, RetrievalExplanation):
        raise EGCFError("SAA-11 requires RetrievalExplanation")
    raw_steps = list(explanation.counterfactual_changes)
    if len(raw_steps) > MAX_ADAPTATION_STEPS:
        raise EGCFError("SAA-11 adaptation plan exceeds bounded step count")
    steps: list[AdaptationStep] = []
    for index, change in enumerate(raw_steps):
        dimension = str(change.dimension).strip().upper()
        if dimension not in ALLOWED_ADAPTATION_DIMENSIONS:
            raise EGCFError(f"unsupported SAA-11 adaptation dimension: {dimension}")
        component = str(change.component).strip().upper()
        if component == "MATHEMATICAL_ALGORITHM":
            base_id = selected_mathematical_algorithm_id or ""
        elif component == "REASONING_ALGORITHM":
            base_id = selected_reasoning_id or ""
        else:
            base_id = ""
        material = {
            "action": "SATISFY_EXACT_COUNTERFACTUAL_CONTRACT",
            "dimension": dimension,
            "required_change": change.required_change,
        }
        payload = {
            "version": ALGORITHM_ADAPTATION_VERSION,
            "index": index,
            "component": component,
            "dimension": dimension,
            "base_algorithm_id": base_id,
            "current": change.current,
            "target": change.required_change,
            "material": material,
        }
        steps.append(
            AdaptationStep(
                index=index,
                component=component,
                dimension=dimension,
                base_algorithm_id=base_id,
                current_contract=change.current,
                target_contract=change.required_change,
                proposed_change=material,
                step_signature=sha256_json(payload),
            )
        )
    plan_payload = {
        "version": ALGORITHM_ADAPTATION_VERSION,
        "source_explanation_signature": explanation.explanation_signature,
        "step_signatures": [item.step_signature for item in steps],
        "policy": "ONE_DECLARED_DIMENSION_PER_STEP",
    }
    return ControlledAdaptationPlan(
        schema_version=1,
        adaptation_version=ALGORITHM_ADAPTATION_VERSION,
        source_explanation_signature=explanation.explanation_signature,
        steps=tuple(steps),
        one_dimension_per_step=True,
        qualification_required=bool(steps),
        canonical_reuse_eligible=False,
        plan_signature=sha256_json(plan_payload),
    )


def create_adapted_candidate(
    step: AdaptationStep,
    *,
    change_material: Mapping[str, Any],
    parent_candidate_signature: str = "",
) -> AdaptedAlgorithmCandidate:
    if not isinstance(step, AdaptationStep):
        raise EGCFError("SAA-11 candidate creation requires AdaptationStep")
    if step.dimension not in ALLOWED_ADAPTATION_DIMENSIONS:
        raise EGCFError("SAA-11 step uses unsupported adaptation dimension")
    if not isinstance(change_material, Mapping) or not change_material:
        raise EGCFError("SAA-11 adaptation requires explicit change material")
    declared = str(change_material.get("dimension", step.dimension)).strip().upper()
    if declared != step.dimension:
        raise EGCFError("SAA-11 forbids changing a dimension other than the current step")
    forbidden = set(change_material.get("also_changes", ()))
    if forbidden:
        raise EGCFError("SAA-11 one-dimension gate rejects multi-dimensional adaptation")
    payload = {
        "version": ALGORITHM_ADAPTATION_VERSION,
        "base_algorithm_id": step.base_algorithm_id,
        "component": step.component,
        "changed_dimension": step.dimension,
        "change_material": dict(change_material),
        "parent_candidate_signature": str(parent_candidate_signature),
    }
    signature = sha256_json(payload)
    return AdaptedAlgorithmCandidate(
        schema_version=1,
        adaptation_version=ALGORITHM_ADAPTATION_VERSION,
        base_algorithm_id=step.base_algorithm_id,
        component=step.component,
        changed_dimension=step.dimension,
        change_material=dict(change_material),
        parent_candidate_signature=str(parent_candidate_signature),
        candidate_signature=signature,
        epistemic_status="UNQUALIFIED_ADAPTED_ALGORITHM_CANDIDATE",
        qualification_required=True,
        canonical_reuse_eligible=False,
    )
