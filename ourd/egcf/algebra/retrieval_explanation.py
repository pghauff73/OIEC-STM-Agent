from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .algorithm_transfer import AlgorithmTransferAssessment
from .unified_retrieval import UnifiedProblemRequirements, UnifiedRetrievalDecision


RETRIEVAL_EXPLANATION_VERSION = "saa-retrieval-explanation-v1"


@dataclass(frozen=True)
class CounterfactualFitChange:
    component: str
    dimension: str
    current: str
    required_change: str
    would_remove_blocker: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "dimension": self.dimension,
            "current": self.current,
            "required_change": self.required_change,
            "would_remove_blocker": self.would_remove_blocker,
        }


@dataclass(frozen=True)
class RetrievalExplanation:
    schema_version: int
    explanation_version: str
    decision_signature: str
    status: str
    selected_reasons: Tuple[str, ...]
    rejected_reasons: Tuple[str, ...]
    counterfactual_changes: Tuple[CounterfactualFitChange, ...]
    fit_gap_dimensions: Tuple[str, ...]
    explanation_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "explanation_version": self.explanation_version,
            "decision_signature": self.decision_signature,
            "status": self.status,
            "selected_reasons": list(self.selected_reasons),
            "rejected_reasons": list(self.rejected_reasons),
            "counterfactual_changes": [item.to_dict() for item in self.counterfactual_changes],
            "fit_gap_dimensions": list(self.fit_gap_dimensions),
            "explanation_signature": self.explanation_signature,
        }


def _finalize(
    *,
    decision_signature: str,
    status: str,
    selected: list[str],
    rejected: list[str],
    changes: list[CounterfactualFitChange],
    dimensions: set[str],
    extra_payload: Any,
) -> RetrievalExplanation:
    payload = {
        "version": RETRIEVAL_EXPLANATION_VERSION,
        "decision_signature": decision_signature,
        "status": status,
        "selected_reasons": selected,
        "rejected_reasons": rejected,
        "counterfactual_changes": [item.to_dict() for item in changes],
        "fit_gap_dimensions": sorted(dimensions),
        "source": extra_payload,
    }
    return RetrievalExplanation(
        schema_version=1,
        explanation_version=RETRIEVAL_EXPLANATION_VERSION,
        decision_signature=decision_signature,
        status=status,
        selected_reasons=tuple(selected),
        rejected_reasons=tuple(rejected),
        counterfactual_changes=tuple(changes),
        fit_gap_dimensions=tuple(sorted(dimensions)),
        explanation_signature=sha256_json(payload),
    )


def explain_algorithm_transfer(assessment: AlgorithmTransferAssessment) -> RetrievalExplanation:
    if not isinstance(assessment, AlgorithmTransferAssessment):
        raise EGCFError("SAA-10.3 transfer explanation requires AlgorithmTransferAssessment")
    selected: list[str] = []
    rejected: list[str] = []
    changes: list[CounterfactualFitChange] = []
    dimensions: set[str] = set()
    if assessment.transfer_without_requalification:
        selected.append("source algorithm transfer preserves semantic, boundary, invariant, dynamics and evidence contracts")
        status = "EXPLAINED_EXACT_TRANSFER"
    elif assessment.blocking_gaps:
        rejected.extend(assessment.blocking_gaps)
        dimensions.add("SEMANTIC_TRANSFER_CONTRACT")
        changes.append(
            CounterfactualFitChange(
                "MATHEMATICAL_ALGORITHM",
                "SEMANTIC_TRANSFER_CONTRACT",
                "; ".join(assessment.blocking_gaps),
                "resolve and independently qualify semantic equivalence before transfer",
                False,
            )
        )
        status = "EXPLAINED_BLOCKED_TRANSFER"
    else:
        status = "EXPLAINED_TRANSFER_REQUALIFICATION_DELTA"
    for dimension in assessment.adaptation_gaps:
        dimensions.add(dimension)
        changes.append(
            CounterfactualFitChange(
                "MATHEMATICAL_ALGORITHM",
                dimension,
                f"source and target {dimension.casefold()} differ",
                "adapt only this contract dimension and requalify in the target domain",
                True,
            )
        )
    return _finalize(
        decision_signature=assessment.assessment_signature,
        status=status,
        selected=selected,
        rejected=rejected,
        changes=changes,
        dimensions=dimensions,
        extra_payload=assessment.to_dict(),
    )


def explain_unified_retrieval(
    decision: UnifiedRetrievalDecision,
    requirements: UnifiedProblemRequirements,
) -> RetrievalExplanation:
    if not isinstance(decision, UnifiedRetrievalDecision):
        raise EGCFError("SAA-10.3 requires UnifiedRetrievalDecision")
    task = requirements.canonical()
    selected: list[str] = []
    rejected: list[str] = []
    changes: list[CounterfactualFitChange] = []
    dimensions: set[str] = set()

    if decision.selected_mathematical_algorithm_id:
        chosen = next(
            (item for item in decision.mathematical_candidates if item.canonical_algorithm_id == decision.selected_mathematical_algorithm_id),
            None,
        )
        if chosen:
            selected.append(
                f"mathematical algorithm {chosen.canonical_algorithm_id} selected with fit {chosen.fit_score_bp}/10000"
            )
    for item in decision.mathematical_candidates:
        if item.canonical_algorithm_id == decision.selected_mathematical_algorithm_id:
            continue
        for gap in item.blocking_gaps:
            rejected.append(f"mathematical {item.canonical_algorithm_id}: {gap}")
            lower = gap.casefold()
            if "input meaning" in lower:
                dimension = "MATHEMATICAL_INPUT_SEMANTICS"
            elif "output count" in lower:
                dimension = "MATHEMATICAL_OUTPUT_SHAPE"
            elif "domain" in lower:
                dimension = "MATHEMATICAL_DOMAIN"
            else:
                dimension = "MATHEMATICAL_CONTRACT"
            dimensions.add(dimension)
            changes.append(CounterfactualFitChange("MATHEMATICAL_ALGORITHM", dimension, gap, "satisfy this exact contract", True))

    if decision.reasoning_result is not None:
        if decision.selected_reasoning_id:
            chosen = next((item for item in decision.reasoning_result.candidates if item.reasoning_id == decision.selected_reasoning_id), None)
            if chosen:
                selected.append(
                    f"reasoning algorithm {chosen.reasoning_id} selected with fit {chosen.fit_score_bp}/10000"
                )
        for item in decision.reasoning_result.candidates:
            if item.reasoning_id == decision.selected_reasoning_id:
                continue
            for gap in item.blocking_gaps:
                rejected.append(f"reasoning {item.reasoning_id}: {gap}")
                lower = gap.casefold()
                if "inputs" in lower:
                    dimension = "REASONING_INPUT_SEMANTICS"
                elif "outputs" in lower:
                    dimension = "REASONING_OUTPUT_SEMANTICS"
                elif "applicability" in lower:
                    dimension = "REASONING_APPLICABILITY"
                elif "invariant" in lower:
                    dimension = "REASONING_INVARIANTS"
                elif "evidence" in lower:
                    dimension = "REASONING_EVIDENCE_CAPABILITY"
                elif "termination" in lower or "budget" in lower:
                    dimension = "REASONING_TERMINATION_BUDGET"
                else:
                    dimension = "REASONING_CONTRACT"
                dimensions.add(dimension)
                changes.append(CounterfactualFitChange("REASONING_ALGORITHM", dimension, gap, "satisfy this exact contract", True))

    for missing in decision.missing_components:
        dimension = "MISSING_" + missing
        dimensions.add(dimension)
        changes.append(
            CounterfactualFitChange(missing, dimension, "no eligible qualified candidate", "provide, adapt, or qualify a candidate that satisfies the explicit problem contract", True)
        )

    if decision.required_components_satisfied:
        status = "EXPLAINED_COMPLETE_KNOWN_SOLUTION"
    elif decision.selected_mathematical_algorithm_id or decision.selected_reasoning_id:
        status = "EXPLAINED_PARTIAL_FIT_WITH_DELTA"
    else:
        status = "EXPLAINED_CONFIRMED_RETRIEVAL_GAP"
    return _finalize(
        decision_signature=decision.decision_signature,
        status=status,
        selected=selected,
        rejected=rejected,
        changes=changes,
        dimensions=dimensions,
        extra_payload={"problem": task.to_dict(), "decision": decision.to_dict()},
    )
