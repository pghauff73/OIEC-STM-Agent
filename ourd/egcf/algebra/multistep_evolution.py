from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact
from .algorithm_adaptation import ALLOWED_ADAPTATION_DIMENSIONS


MULTISTEP_EVOLUTION_VERSION = "saa-multistep-evolution-v1"
MAX_EVOLUTION_STEPS = 16


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _grounded_evidence(store: Any, evidence_ids: Sequence[str]) -> tuple[Tuple[str, ...], Tuple[str, ...]]:
    grounded: list[str] = []
    groups: set[str] = set()
    for evidence_id in sorted({str(value).strip() for value in evidence_ids if str(value).strip()}):
        try:
            record = store.get(evidence_id)
        except Exception as exc:
            raise EGCFError(f"SAA-11.3 evolution evidence is not registered: {evidence_id}") from exc
        if not isinstance(record, EvidenceArtifact):
            raise EGCFError("SAA-11.3 evolution evidence must reference EvidenceArtifact")
        if record.success is not True or record.simulated:
            raise EGCFError("SAA-11.3 evolution evidence must be successful and non-simulated")
        if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
            raise EGCFError("SAA-11.3 evolution evidence must be deterministic/human grounded")
        grounded.append(evidence_id)
        if record.independence_group:
            groups.add(record.independence_group)
    if not grounded:
        raise EGCFError("SAA-11.3 evolution qualification requires grounded evidence")
    if not groups:
        raise EGCFError("SAA-11.3 evolution evidence requires an independence group")
    return tuple(grounded), tuple(sorted(groups))


@dataclass(frozen=True)
class EvolutionStepDescriptor:
    index: int
    parent_ref: str
    candidate_ref: str
    changed_dimension: str
    edge_signature: str
    candidate_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "parent_ref": self.parent_ref,
            "candidate_ref": self.candidate_ref,
            "changed_dimension": self.changed_dimension,
            "edge_signature": self.edge_signature,
            "candidate_signature": self.candidate_signature,
        }


@dataclass(frozen=True)
class MultiStepEvolutionPlan:
    schema_version: int
    evolution_version: str
    root_algorithm_ref: str
    final_candidate_ref: str
    frozen_invariants: Tuple[str, ...]
    allowed_dimensions: Tuple[str, ...]
    steps: Tuple[EvolutionStepDescriptor, ...]
    one_dimension_per_step: bool
    plan_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evolution_version": self.evolution_version,
            "root_algorithm_ref": self.root_algorithm_ref,
            "final_candidate_ref": self.final_candidate_ref,
            "frozen_invariants": list(self.frozen_invariants),
            "allowed_dimensions": list(self.allowed_dimensions),
            "steps": [item.to_dict() for item in self.steps],
            "one_dimension_per_step": self.one_dimension_per_step,
            "plan_signature": self.plan_signature,
        }


@dataclass(frozen=True)
class EvolutionStepQualification:
    schema_version: int
    evolution_version: str
    plan_signature: str
    candidate_ref: str
    changed_dimension: str
    invariant_results: Tuple[Tuple[str, bool], ...]
    grounded_evidence_ids: Tuple[str, ...]
    independence_groups: Tuple[str, ...]
    independent_review: bool
    status: str
    step_qualified: bool
    qualification_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evolution_version": self.evolution_version,
            "plan_signature": self.plan_signature,
            "candidate_ref": self.candidate_ref,
            "changed_dimension": self.changed_dimension,
            "invariant_results": {name: value for name, value in self.invariant_results},
            "grounded_evidence_ids": list(self.grounded_evidence_ids),
            "independence_groups": list(self.independence_groups),
            "independent_review": self.independent_review,
            "status": self.status,
            "step_qualified": self.step_qualified,
            "qualification_signature": self.qualification_signature,
        }


@dataclass(frozen=True)
class MultiStepEvolutionAssessment:
    schema_version: int
    evolution_version: str
    plan_signature: str
    final_candidate_ref: str
    qualified_step_count: int
    total_step_count: int
    invariant_preservation_complete: bool
    status: str
    evolution_qualified: bool
    blocking_steps: Tuple[str, ...]
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evolution_version": self.evolution_version,
            "plan_signature": self.plan_signature,
            "final_candidate_ref": self.final_candidate_ref,
            "qualified_step_count": self.qualified_step_count,
            "total_step_count": self.total_step_count,
            "invariant_preservation_complete": self.invariant_preservation_complete,
            "status": self.status,
            "evolution_qualified": self.evolution_qualified,
            "blocking_steps": list(self.blocking_steps),
            "assessment_signature": self.assessment_signature,
        }


def make_multistep_evolution_plan(
    lineage_store: Any,
    final_candidate_ref: str,
    *,
    frozen_invariants: Sequence[str],
    allowed_dimensions: Sequence[str] = (),
    max_steps: int = MAX_EVOLUTION_STEPS,
) -> MultiStepEvolutionPlan:
    if not hasattr(lineage_store, "ancestors") or not hasattr(lineage_store, "get_candidate"):
        raise EGCFError("SAA-11.3 requires AdaptationLineageStore")
    limit = int(max_steps)
    if limit < 1 or limit > MAX_EVOLUTION_STEPS:
        raise EGCFError("SAA-11.3 max evolution steps outside supported range")
    final_ref = str(final_candidate_ref).strip()
    lineage_store.get_candidate(final_ref)
    ancestors = lineage_store.ancestors(final_ref)
    candidate_ancestors = [ref for ref in ancestors if ref.startswith("adapted-candidate:sha256:")]
    root_candidates = list(reversed(candidate_ancestors)) + [final_ref]
    if len(root_candidates) > limit:
        raise EGCFError("SAA-11.3 evolution path exceeds bounded step count")
    root_ref = next((ref for ref in reversed(ancestors) if not ref.startswith("adapted-candidate:sha256:")), "")
    if not root_ref:
        raise EGCFError("SAA-11.3 evolution path has no canonical root")
    frozen = tuple(sorted({_text(value) for value in frozen_invariants if _text(value)}))
    if not frozen:
        raise EGCFError("SAA-11.3 requires at least one frozen invariant")
    allowed = tuple(sorted({str(value).strip().upper() for value in allowed_dimensions if str(value).strip()}))
    if allowed and any(value not in ALLOWED_ADAPTATION_DIMENSIONS for value in allowed):
        raise EGCFError("SAA-11.3 allowed dimensions contain an unsupported adaptation dimension")
    edge_by_child = {item["child_ref"]: item for item in lineage_store.edges()}
    steps: list[EvolutionStepDescriptor] = []
    previous = root_ref
    for index, candidate_ref in enumerate(root_candidates):
        envelope = lineage_store.get_candidate(candidate_ref)
        payload = envelope["payload"]
        dimension = str(payload["changed_dimension"]).strip().upper()
        if dimension not in ALLOWED_ADAPTATION_DIMENSIONS:
            raise EGCFError("SAA-11.3 stored candidate uses unsupported changed dimension")
        if allowed and dimension not in allowed:
            raise EGCFError(f"SAA-11.3 candidate changes frozen-out dimension: {dimension}")
        edge = edge_by_child.get(candidate_ref)
        if edge is None or edge["parent_ref"] != previous:
            raise EGCFError("SAA-11.3 lineage path is discontinuous")
        edge_payload = edge["payload"]
        steps.append(
            EvolutionStepDescriptor(
                index=index,
                parent_ref=previous,
                candidate_ref=candidate_ref,
                changed_dimension=dimension,
                edge_signature=str(edge_payload["edge_signature"]),
                candidate_signature=str(payload["candidate_signature"]),
            )
        )
        previous = candidate_ref
    material = {
        "version": MULTISTEP_EVOLUTION_VERSION,
        "root_algorithm_ref": root_ref,
        "final_candidate_ref": final_ref,
        "frozen_invariants": list(frozen),
        "allowed_dimensions": list(allowed),
        "steps": [item.to_dict() for item in steps],
        "policy": "EACH_INTERMEDIATE_STEP_REQUALIFIES_FROZEN_INVARIANTS",
    }
    return MultiStepEvolutionPlan(
        schema_version=1,
        evolution_version=MULTISTEP_EVOLUTION_VERSION,
        root_algorithm_ref=root_ref,
        final_candidate_ref=final_ref,
        frozen_invariants=frozen,
        allowed_dimensions=allowed,
        steps=tuple(steps),
        one_dimension_per_step=True,
        plan_signature=sha256_json(material),
    )


def qualify_evolution_step(
    store: Any,
    plan: MultiStepEvolutionPlan,
    candidate_ref: str,
    *,
    invariant_results: Mapping[str, bool],
    evidence_ids: Sequence[str],
    independent_review: bool,
) -> EvolutionStepQualification:
    if not isinstance(plan, MultiStepEvolutionPlan):
        raise EGCFError("SAA-11.3 step qualification requires MultiStepEvolutionPlan")
    ref = str(candidate_ref).strip()
    descriptor = next((item for item in plan.steps if item.candidate_ref == ref), None)
    if descriptor is None:
        raise EGCFError("SAA-11.3 candidate is not part of the evolution plan")
    supplied = {_text(name): bool(value) for name, value in invariant_results.items()}
    if set(supplied) != set(plan.frozen_invariants):
        raise EGCFError("SAA-11.3 step must report every frozen invariant and no extras")
    grounded, groups = _grounded_evidence(store, evidence_ids)
    invariant_gate = all(supplied[name] is True for name in plan.frozen_invariants)
    if not invariant_gate:
        status = "EVOLUTION_STEP_INVARIANT_VIOLATION"
    elif not independent_review:
        status = "EVOLUTION_STEP_REVIEW_REQUIRED"
    else:
        status = "EVOLUTION_STEP_QUALIFIED"
    payload = {
        "version": MULTISTEP_EVOLUTION_VERSION,
        "plan_signature": plan.plan_signature,
        "candidate_ref": ref,
        "changed_dimension": descriptor.changed_dimension,
        "invariant_results": supplied,
        "grounded_evidence_ids": list(grounded),
        "independence_groups": list(groups),
        "independent_review": bool(independent_review),
        "status": status,
    }
    return EvolutionStepQualification(
        schema_version=1,
        evolution_version=MULTISTEP_EVOLUTION_VERSION,
        plan_signature=plan.plan_signature,
        candidate_ref=ref,
        changed_dimension=descriptor.changed_dimension,
        invariant_results=tuple(sorted(supplied.items())),
        grounded_evidence_ids=grounded,
        independence_groups=groups,
        independent_review=bool(independent_review),
        status=status,
        step_qualified=status == "EVOLUTION_STEP_QUALIFIED",
        qualification_signature=sha256_json(payload),
    )


def assess_multistep_evolution(
    plan: MultiStepEvolutionPlan,
    qualifications: Sequence[EvolutionStepQualification],
) -> MultiStepEvolutionAssessment:
    if not isinstance(plan, MultiStepEvolutionPlan):
        raise EGCFError("SAA-11.3 assessment requires MultiStepEvolutionPlan")
    by_ref: dict[str, EvolutionStepQualification] = {}
    for qualification in qualifications:
        if not isinstance(qualification, EvolutionStepQualification):
            raise EGCFError("SAA-11.3 assessment received invalid step qualification")
        if qualification.plan_signature != plan.plan_signature:
            raise EGCFError("SAA-11.3 step qualification belongs to a different plan")
        if qualification.candidate_ref in by_ref:
            raise EGCFError("SAA-11.3 duplicate step qualification")
        by_ref[qualification.candidate_ref] = qualification
    blocking: list[str] = []
    qualified = 0
    for step in plan.steps:
        item = by_ref.get(step.candidate_ref)
        if item is None:
            blocking.append(f"{step.candidate_ref}: MISSING_STEP_QUALIFICATION")
        elif not item.step_qualified:
            blocking.append(f"{step.candidate_ref}: {item.status}")
        else:
            qualified += 1
    complete = qualified == len(plan.steps) and not blocking
    status = "MULTISTEP_EVOLUTION_QUALIFIED" if complete else "MULTISTEP_EVOLUTION_BLOCKED"
    payload = {
        "version": MULTISTEP_EVOLUTION_VERSION,
        "plan_signature": plan.plan_signature,
        "final_candidate_ref": plan.final_candidate_ref,
        "qualification_signatures": sorted(item.qualification_signature for item in qualifications),
        "qualified_step_count": qualified,
        "total_step_count": len(plan.steps),
        "blocking_steps": blocking,
        "status": status,
    }
    return MultiStepEvolutionAssessment(
        schema_version=1,
        evolution_version=MULTISTEP_EVOLUTION_VERSION,
        plan_signature=plan.plan_signature,
        final_candidate_ref=plan.final_candidate_ref,
        qualified_step_count=qualified,
        total_step_count=len(plan.steps),
        invariant_preservation_complete=complete,
        status=status,
        evolution_qualified=complete,
        blocking_steps=tuple(blocking),
        assessment_signature=sha256_json(payload),
    )
