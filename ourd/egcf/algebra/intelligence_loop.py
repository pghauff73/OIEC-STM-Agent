from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from ...retrieve_first import RetrieveFirstReceipt
from ..errors import EGCFError
from ..ids import sha256_json
from .algorithm_adaptation import ControlledAdaptationPlan
from .experiment_aggregation import RepeatedExperimentAggregate
from .multistep_evolution import MultiStepEvolutionAssessment
from .retrieval_explanation import RetrievalExplanation


INTELLIGENCE_LOOP_VERSION = "saa-closed-intelligence-improvement-loop-v1"


@dataclass(frozen=True)
class IntelligenceImprovementDecision:
    schema_version: int
    loop_version: str
    phase: str
    status: str
    next_action: str
    terminal: bool
    permitted_actions: Tuple[str, ...]
    blocking_reasons: Tuple[str, ...]
    selected_mathematical_algorithm_id: str | None
    selected_reasoning_id: str | None
    candidate_ref: str | None
    promoted_canonical_algorithm_ref: str | None
    retrieval_receipt_signature: str
    explanation_signature: str
    adaptation_plan_signature: str
    evolution_assessment_signature: str
    experiment_aggregate_signature: str
    promotion_ref: str
    post_promotion_receipt_signature: str
    decision_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "loop_version": self.loop_version,
            "phase": self.phase,
            "status": self.status,
            "next_action": self.next_action,
            "terminal": self.terminal,
            "permitted_actions": list(self.permitted_actions),
            "blocking_reasons": list(self.blocking_reasons),
            "selected_mathematical_algorithm_id": self.selected_mathematical_algorithm_id,
            "selected_reasoning_id": self.selected_reasoning_id,
            "candidate_ref": self.candidate_ref,
            "promoted_canonical_algorithm_ref": self.promoted_canonical_algorithm_ref,
            "retrieval_receipt_signature": self.retrieval_receipt_signature,
            "explanation_signature": self.explanation_signature,
            "adaptation_plan_signature": self.adaptation_plan_signature,
            "evolution_assessment_signature": self.evolution_assessment_signature,
            "experiment_aggregate_signature": self.experiment_aggregate_signature,
            "promotion_ref": self.promotion_ref,
            "post_promotion_receipt_signature": self.post_promotion_receipt_signature,
            "decision_signature": self.decision_signature,
        }


def _decision(
    *,
    receipt: RetrieveFirstReceipt,
    phase: str,
    status: str,
    next_action: str,
    terminal: bool,
    permitted_actions: Tuple[str, ...],
    blocking_reasons: Tuple[str, ...] = (),
    candidate_ref: str | None = None,
    promoted_canonical_algorithm_ref: str | None = None,
    explanation: RetrievalExplanation | None = None,
    adaptation_plan: ControlledAdaptationPlan | None = None,
    evolution_assessment: MultiStepEvolutionAssessment | None = None,
    experiment_aggregate: RepeatedExperimentAggregate | None = None,
    promotion_ref: str = "",
    post_promotion_receipt: RetrieveFirstReceipt | None = None,
) -> IntelligenceImprovementDecision:
    payload = {
        "version": INTELLIGENCE_LOOP_VERSION,
        "phase": phase,
        "status": status,
        "next_action": next_action,
        "terminal": terminal,
        "permitted_actions": list(permitted_actions),
        "blocking_reasons": list(blocking_reasons),
        "selected_mathematical_algorithm_id": receipt.selected_mathematical_algorithm_id,
        "selected_reasoning_id": receipt.selected_reasoning_id,
        "candidate_ref": candidate_ref,
        "promoted_canonical_algorithm_ref": promoted_canonical_algorithm_ref,
        "retrieval_receipt_signature": receipt.receipt_signature,
        "explanation_signature": explanation.explanation_signature if explanation else "",
        "adaptation_plan_signature": adaptation_plan.plan_signature if adaptation_plan else "",
        "evolution_assessment_signature": evolution_assessment.assessment_signature if evolution_assessment else "",
        "experiment_aggregate_signature": experiment_aggregate.aggregate_signature if experiment_aggregate else "",
        "promotion_ref": promotion_ref,
        "post_promotion_receipt_signature": post_promotion_receipt.receipt_signature if post_promotion_receipt else "",
    }
    return IntelligenceImprovementDecision(
        schema_version=1,
        loop_version=INTELLIGENCE_LOOP_VERSION,
        phase=phase,
        status=status,
        next_action=next_action,
        terminal=terminal,
        permitted_actions=permitted_actions,
        blocking_reasons=blocking_reasons,
        selected_mathematical_algorithm_id=receipt.selected_mathematical_algorithm_id,
        selected_reasoning_id=receipt.selected_reasoning_id,
        candidate_ref=candidate_ref,
        promoted_canonical_algorithm_ref=promoted_canonical_algorithm_ref,
        retrieval_receipt_signature=receipt.receipt_signature,
        explanation_signature=explanation.explanation_signature if explanation else "",
        adaptation_plan_signature=adaptation_plan.plan_signature if adaptation_plan else "",
        evolution_assessment_signature=evolution_assessment.assessment_signature if evolution_assessment else "",
        experiment_aggregate_signature=experiment_aggregate.aggregate_signature if experiment_aggregate else "",
        promotion_ref=promotion_ref,
        post_promotion_receipt_signature=post_promotion_receipt.receipt_signature if post_promotion_receipt else "",
        decision_signature=sha256_json(payload),
    )


def evaluate_intelligence_improvement_loop(
    receipt: RetrieveFirstReceipt,
    *,
    explanation: RetrievalExplanation | None = None,
    adaptation_plan: ControlledAdaptationPlan | None = None,
    evolution_assessment: MultiStepEvolutionAssessment | None = None,
    experiment_aggregate: RepeatedExperimentAggregate | None = None,
    candidate_ref: str | None = None,
    promotion_ref: str = "",
    promoted_canonical_algorithm_ref: str | None = None,
    promoted_component: str = "",
    post_promotion_receipt: RetrieveFirstReceipt | None = None,
) -> IntelligenceImprovementDecision:
    if not isinstance(receipt, RetrieveFirstReceipt):
        raise EGCFError("SAA-12 requires RetrieveFirstReceipt")

    if not receipt.retrieval_attempted or not receipt.required_search_completed:
        return _decision(
            receipt=receipt,
            phase="RETRIEVE",
            status="LOOP_BLOCKED_RETRIEVAL_INCOMPLETE",
            next_action="COMPLETE_REQUIRED_QUALIFIED_RETRIEVAL",
            terminal=False,
            permitted_actions=("RETRIEVE",),
            blocking_reasons=("required canonical stores have not been completely searched",),
        )

    if receipt.status == "REUSE_QUALIFIED_KNOWN_SOLUTION" and not receipt.generation_scope and not promotion_ref:
        return _decision(
            receipt=receipt,
            phase="REUSE",
            status="KNOWN_SOLUTION_REUSE_COMPLETE",
            next_action="USE_QUALIFIED_KNOWN_SOLUTION",
            terminal=True,
            permitted_actions=("REUSE", "MONITOR_EVIDENCE"),
        )

    if explanation is None:
        return _decision(
            receipt=receipt,
            phase="EXPLAIN_GAP",
            status="LOOP_REQUIRES_DETERMINISTIC_FIT_EXPLANATION",
            next_action="EXPLAIN_RETRIEVAL_DELTA",
            terminal=False,
            permitted_actions=("EXPLAIN_GAP",),
        )
    if explanation.decision_signature != receipt.retrieval_decision_signature:
        raise EGCFError("SAA-12 retrieval explanation does not belong to the receipt decision")

    if adaptation_plan is None:
        return _decision(
            receipt=receipt,
            phase="PLAN_ADAPTATION",
            status="LOOP_REQUIRES_BOUNDED_ADAPTATION_PLAN",
            next_action="BUILD_ONE_DIMENSION_ADAPTATION_PLAN",
            terminal=False,
            permitted_actions=("PLAN_ADAPTATION",),
            explanation=explanation,
        )
    if adaptation_plan.source_explanation_signature != explanation.explanation_signature:
        raise EGCFError("SAA-12 adaptation plan does not derive from the supplied explanation")

    if evolution_assessment is None:
        return _decision(
            receipt=receipt,
            phase="EVOLVE",
            status="LOOP_REQUIRES_INVARIANT_PRESERVING_EVOLUTION",
            next_action="QUALIFY_EACH_EVOLUTION_STEP",
            terminal=False,
            permitted_actions=("ADAPT_ONE_DIMENSION", "QUALIFY_EVOLUTION_STEP"),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            candidate_ref=candidate_ref,
        )
    if not evolution_assessment.evolution_qualified:
        return _decision(
            receipt=receipt,
            phase="EVOLVE",
            status="LOOP_BLOCKED_EVOLUTION_NOT_QUALIFIED",
            next_action="REVISE_OR_GATHER_STEP_EVIDENCE",
            terminal=False,
            permitted_actions=("GATHER_EVIDENCE", "REVISE_ADAPTATION"),
            blocking_reasons=evolution_assessment.blocking_steps,
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            candidate_ref=evolution_assessment.final_candidate_ref,
        )
    candidate_ref = candidate_ref or evolution_assessment.final_candidate_ref
    if candidate_ref != evolution_assessment.final_candidate_ref:
        raise EGCFError("SAA-12 candidate reference disagrees with qualified evolution endpoint")

    if experiment_aggregate is None:
        return _decision(
            receipt=receipt,
            phase="EXPERIMENT",
            status="LOOP_REQUIRES_REPEATED_COMPARATIVE_EVIDENCE",
            next_action="RUN_AND_AGGREGATE_BOUNDED_AB_EXPERIMENTS",
            terminal=False,
            permitted_actions=("RUN_AB_EXPERIMENT", "AGGREGATE_EXPERIMENTS"),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            candidate_ref=candidate_ref,
        )
    if not experiment_aggregate.sustained_improvement_qualified:
        return _decision(
            receipt=receipt,
            phase="EXPERIMENT",
            status="LOOP_BLOCKED_SUSTAINED_IMPROVEMENT_NOT_QUALIFIED",
            next_action="GATHER_MORE_INDEPENDENT_EVIDENCE_OR_REVISE",
            terminal=False,
            permitted_actions=("RUN_AB_EXPERIMENT", "REVISE_ADAPTATION", "STOP"),
            blocking_reasons=(experiment_aggregate.status,),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            experiment_aggregate=experiment_aggregate,
            candidate_ref=candidate_ref,
        )

    if not promotion_ref or not promoted_canonical_algorithm_ref:
        return _decision(
            receipt=receipt,
            phase="QUALIFY_AND_PROMOTE",
            status="LOOP_REQUIRES_CANONICAL_QUALIFICATION_AND_PROMOTION",
            next_action="RUN_NORMAL_CANONICAL_QUALIFICATION_THEN_RECORD_PROMOTION",
            terminal=False,
            permitted_actions=("QUALIFY_CANONICALLY", "RECORD_PROMOTION"),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            experiment_aggregate=experiment_aggregate,
            candidate_ref=candidate_ref,
        )

    component = str(promoted_component).strip().upper()
    if component not in {"MATHEMATICAL_ALGORITHM", "REASONING_ALGORITHM"}:
        raise EGCFError("SAA-12 promoted_component must identify mathematical or reasoning algorithm")

    if post_promotion_receipt is None:
        return _decision(
            receipt=receipt,
            phase="RE_RETRIEVE",
            status="LOOP_REQUIRES_POST_PROMOTION_RETRIEVAL",
            next_action="RETRIEVE_FROM_UPDATED_CANONICAL_STORES",
            terminal=False,
            permitted_actions=("RETRIEVE",),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            experiment_aggregate=experiment_aggregate,
            candidate_ref=candidate_ref,
            promotion_ref=promotion_ref,
            promoted_canonical_algorithm_ref=promoted_canonical_algorithm_ref,
        )
    if not post_promotion_receipt.retrieval_attempted or not post_promotion_receipt.required_search_completed:
        return _decision(
            receipt=receipt,
            phase="RE_RETRIEVE",
            status="LOOP_BLOCKED_POST_PROMOTION_RETRIEVAL_INCOMPLETE",
            next_action="COMPLETE_POST_PROMOTION_RETRIEVAL",
            terminal=False,
            permitted_actions=("RETRIEVE",),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            experiment_aggregate=experiment_aggregate,
            candidate_ref=candidate_ref,
            promotion_ref=promotion_ref,
            promoted_canonical_algorithm_ref=promoted_canonical_algorithm_ref,
            post_promotion_receipt=post_promotion_receipt,
        )

    selected = (
        post_promotion_receipt.selected_mathematical_algorithm_id
        if component == "MATHEMATICAL_ALGORITHM"
        else post_promotion_receipt.selected_reasoning_id
    )
    if selected != promoted_canonical_algorithm_ref:
        return _decision(
            receipt=receipt,
            phase="VERIFY_CLOSURE",
            status="LOOP_POST_PROMOTION_RETRIEVAL_DID_NOT_SELECT_PROMOTED_KNOWLEDGE",
            next_action="EXPLAIN_NEW_FIT_OR_STOP",
            terminal=False,
            permitted_actions=("EXPLAIN_GAP", "STOP"),
            blocking_reasons=("promoted canonical algorithm is not the selected qualified fit after store update",),
            explanation=explanation,
            adaptation_plan=adaptation_plan,
            evolution_assessment=evolution_assessment,
            experiment_aggregate=experiment_aggregate,
            candidate_ref=candidate_ref,
            promotion_ref=promotion_ref,
            promoted_canonical_algorithm_ref=promoted_canonical_algorithm_ref,
            post_promotion_receipt=post_promotion_receipt,
        )

    return _decision(
        receipt=receipt,
        phase="VERIFY_CLOSURE",
        status="CLOSED_LOOP_IMPROVEMENT_VERIFIED",
        next_action="REUSE_PROMOTED_QUALIFIED_KNOWLEDGE",
        terminal=True,
        permitted_actions=("REUSE", "MONITOR_EVIDENCE"),
        explanation=explanation,
        adaptation_plan=adaptation_plan,
        evolution_assessment=evolution_assessment,
        experiment_aggregate=experiment_aggregate,
        candidate_ref=candidate_ref,
        promotion_ref=promotion_ref,
        promoted_canonical_algorithm_ref=promoted_canonical_algorithm_ref,
        post_promotion_receipt=post_promotion_receipt,
    )
