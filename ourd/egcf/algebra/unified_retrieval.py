from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .reasoning_fit import (
    ReasoningRetrievalResult,
    ReasoningTaskRequirements,
    retrieve_reasoning_algorithms,
)
from .semantic_units import SemanticConcept


UNIFIED_RETRIEVAL_VERSION = "saa-unified-retrieval-v1"
MAX_UNIFIED_MATHEMATICAL_RESULTS = 64


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


@dataclass(frozen=True)
class UnifiedProblemRequirements:
    problem_id: str
    input_concepts: Tuple[SemanticConcept, ...]
    desired_mathematical_output_count: int = 0
    mathematical_domain: str = ""
    reasoning_desired_outputs: Tuple[str, ...] = ()
    reasoning_applicability: Tuple[str, ...] = ()
    required_invariants: Tuple[str, ...] = ()
    available_evidence_requirements: Tuple[str, ...] = ()
    max_reasoning_steps: int = 1024
    require_mathematical_algorithm: bool = True
    require_reasoning_algorithm: bool = True

    def canonical(self) -> "UnifiedProblemRequirements":
        if not str(self.problem_id).strip():
            raise EGCFError("SAA-10 unified retrieval requires problem_id")
        if self.desired_mathematical_output_count < 0:
            raise EGCFError("desired mathematical output count cannot be negative")
        if self.max_reasoning_steps < 1 or self.max_reasoning_steps > 1024:
            raise EGCFError("unified reasoning step budget outside supported range")
        for concept in self.input_concepts:
            if not isinstance(concept, SemanticConcept) or not concept.canonical_eligible:
                raise EGCFError("SAA-10 requires canonically resolved input concepts")
        return UnifiedProblemRequirements(
            problem_id=str(self.problem_id).strip(),
            input_concepts=tuple(sorted(self.input_concepts, key=lambda item: item.concept_signature)),
            desired_mathematical_output_count=int(self.desired_mathematical_output_count),
            mathematical_domain=_text(self.mathematical_domain),
            reasoning_desired_outputs=tuple(sorted({_text(value) for value in self.reasoning_desired_outputs if _text(value)})),
            reasoning_applicability=tuple(sorted({_text(value) for value in self.reasoning_applicability if _text(value)})),
            required_invariants=tuple(sorted({_text(value) for value in self.required_invariants if _text(value)})),
            available_evidence_requirements=tuple(sorted({_text(value) for value in self.available_evidence_requirements if _text(value)})),
            max_reasoning_steps=int(self.max_reasoning_steps),
            require_mathematical_algorithm=bool(self.require_mathematical_algorithm),
            require_reasoning_algorithm=bool(self.require_reasoning_algorithm),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "input_concept_signatures": [item.concept_signature for item in self.input_concepts],
            "desired_mathematical_output_count": self.desired_mathematical_output_count,
            "mathematical_domain": self.mathematical_domain,
            "reasoning_desired_outputs": list(self.reasoning_desired_outputs),
            "reasoning_applicability": list(self.reasoning_applicability),
            "required_invariants": list(self.required_invariants),
            "available_evidence_requirements": list(self.available_evidence_requirements),
            "max_reasoning_steps": self.max_reasoning_steps,
            "require_mathematical_algorithm": self.require_mathematical_algorithm,
            "require_reasoning_algorithm": self.require_reasoning_algorithm,
        }


@dataclass(frozen=True)
class MathematicalFitAssessment:
    canonical_algorithm_id: str
    status: str
    fit_score_bp: int
    semantic_input_fit_bp: int
    output_shape_fit_bp: int
    domain_fit_bp: int
    matched_input_meanings: Tuple[str, ...]
    unmatched_input_meanings: Tuple[str, ...]
    blocking_gaps: Tuple[str, ...]
    fit_signature: str

    @property
    def eligible(self) -> bool:
        return not self.blocking_gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_algorithm_id": self.canonical_algorithm_id,
            "status": self.status,
            "fit_score_bp": self.fit_score_bp,
            "semantic_input_fit_bp": self.semantic_input_fit_bp,
            "output_shape_fit_bp": self.output_shape_fit_bp,
            "domain_fit_bp": self.domain_fit_bp,
            "matched_input_meanings": list(self.matched_input_meanings),
            "unmatched_input_meanings": list(self.unmatched_input_meanings),
            "blocking_gaps": list(self.blocking_gaps),
            "fit_signature": self.fit_signature,
            "eligible": self.eligible,
        }


def _concept_matches_meaning(concept: SemanticConcept, meaning: str, ontology: Any | None) -> bool:
    target = _text(meaning)
    direct = {
        concept.canonical_name,
        concept.meaning,
        *concept.aliases,
    }
    if target in {_text(value) for value in direct}:
        return True
    if ontology is None or not hasattr(ontology, "meanings_equivalent"):
        return False
    for value in direct:
        try:
            if ontology.meanings_equivalent(value, target):
                return True
        except Exception:
            continue
    return False


def evaluate_mathematical_fit(
    item: dict[str, Any],
    requirements: UnifiedProblemRequirements,
    *,
    ontology: Any | None = None,
) -> MathematicalFitAssessment:
    task = requirements.canonical()
    canonical_id = str(item.get("canonical_id", ""))
    payload = item.get("payload") or {}
    input_rows = payload.get("inputs", ())
    algorithm_meanings = tuple(
        _text(row.get("canonical_meaning", ""))
        for row in input_rows
        if _text(row.get("canonical_meaning", ""))
    )
    matched: list[str] = []
    unmatched: list[str] = []
    for meaning in algorithm_meanings:
        if any(_concept_matches_meaning(concept, meaning, ontology) for concept in task.input_concepts):
            matched.append(meaning)
        else:
            unmatched.append(meaning)
    semantic_fit = 10000 if not algorithm_meanings else (10000 * len(matched)) // len(algorithm_meanings)

    output_count = int(payload.get("output_count", 0))
    if task.desired_mathematical_output_count:
        output_fit = 10000 if output_count == task.desired_mathematical_output_count else 0
    else:
        output_fit = 10000
    candidate_domain = _text(payload.get("domain", ""))
    domain_fit = 10000 if not task.mathematical_domain or candidate_domain == task.mathematical_domain else 0

    blockers: list[str] = []
    if unmatched:
        blockers.append("unmatched representative input meanings: " + ", ".join(sorted(unmatched)))
    if task.desired_mathematical_output_count and output_count != task.desired_mathematical_output_count:
        blockers.append(
            f"mathematical output count {output_count} != required {task.desired_mathematical_output_count}"
        )
    if task.mathematical_domain and candidate_domain != task.mathematical_domain:
        blockers.append(f"mathematical domain {candidate_domain or '<none>'} != required {task.mathematical_domain}")
    score = (60 * semantic_fit + 20 * output_fit + 20 * domain_fit) // 100
    if blockers:
        status = "INELIGIBLE_MATHEMATICAL_FIT"
    elif score >= 9000:
        status = "GOOD_MATHEMATICAL_FIT"
    elif score >= 6500:
        status = "PARTIAL_MATHEMATICAL_FIT"
    else:
        status = "POOR_MATHEMATICAL_FIT"
    fit_payload = {
        "version": UNIFIED_RETRIEVAL_VERSION,
        "canonical_algorithm_id": canonical_id,
        "problem": task.to_dict(),
        "algorithm_meanings": list(algorithm_meanings),
        "matched": sorted(matched),
        "unmatched": sorted(unmatched),
        "semantic_fit": semantic_fit,
        "output_fit": output_fit,
        "domain_fit": domain_fit,
        "score": score,
        "blocking_gaps": blockers,
    }
    return MathematicalFitAssessment(
        canonical_algorithm_id=canonical_id,
        status=status,
        fit_score_bp=score,
        semantic_input_fit_bp=semantic_fit,
        output_shape_fit_bp=output_fit,
        domain_fit_bp=domain_fit,
        matched_input_meanings=tuple(sorted(matched)),
        unmatched_input_meanings=tuple(sorted(unmatched)),
        blocking_gaps=tuple(blockers),
        fit_signature=sha256_json(fit_payload),
    )


@dataclass(frozen=True)
class UnifiedRetrievalDecision:
    schema_version: int
    retrieval_version: str
    problem_signature: str
    mathematical_candidates: Tuple[MathematicalFitAssessment, ...]
    selected_mathematical_algorithm_id: str | None
    reasoning_result: ReasoningRetrievalResult | None
    selected_reasoning_id: str | None
    required_components_satisfied: bool
    missing_components: Tuple[str, ...]
    status: str
    decision_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "retrieval_version": self.retrieval_version,
            "problem_signature": self.problem_signature,
            "mathematical_candidates": [item.to_dict() for item in self.mathematical_candidates],
            "selected_mathematical_algorithm_id": self.selected_mathematical_algorithm_id,
            "reasoning_result": self.reasoning_result.to_dict() if self.reasoning_result else None,
            "selected_reasoning_id": self.selected_reasoning_id,
            "required_components_satisfied": self.required_components_satisfied,
            "missing_components": list(self.missing_components),
            "status": self.status,
            "decision_signature": self.decision_signature,
        }


def retrieve_unified_solution(
    canonical_algorithm_store: Any | None,
    reasoning_store: Any | None,
    requirements: UnifiedProblemRequirements,
    *,
    ontology: Any | None = None,
    mathematical_limit: int = 10,
    reasoning_limit: int = 10,
) -> UnifiedRetrievalDecision:
    task = requirements.canonical()
    if mathematical_limit < 1 or mathematical_limit > MAX_UNIFIED_MATHEMATICAL_RESULTS:
        raise EGCFError("mathematical retrieval limit outside supported range")
    problem_signature = sha256_json(
        {"version": UNIFIED_RETRIEVAL_VERSION, "problem": task.to_dict()}
    )

    math_assessments: list[MathematicalFitAssessment] = []
    if canonical_algorithm_store is not None:
        if not hasattr(canonical_algorithm_store, "list"):
            raise EGCFError("SAA-10 mathematical retrieval requires CanonicalAlgorithmStore")
        for item in canonical_algorithm_store.list():
            assessment = evaluate_mathematical_fit(item, task, ontology=ontology)
            math_assessments.append(assessment)
    math_assessments.sort(
        key=lambda item: (0 if item.eligible else 1, -item.fit_score_bp, item.canonical_algorithm_id)
    )
    math_candidates = tuple(math_assessments[:mathematical_limit])
    selected_math = next((item for item in math_candidates if item.eligible), None)

    reasoning_result: ReasoningRetrievalResult | None = None
    selected_reasoning_id: str | None = None
    if reasoning_store is not None:
        available_reasoning_inputs = tuple(
            sorted(
                {
                    concept.meaning
                    for concept in task.input_concepts
                }
            )
        )
        reasoning_requirements = ReasoningTaskRequirements(
            available_inputs=available_reasoning_inputs,
            desired_outputs=task.reasoning_desired_outputs,
            required_applicability=task.reasoning_applicability,
            required_invariants=task.required_invariants,
            available_evidence_requirements=task.available_evidence_requirements,
            max_steps=task.max_reasoning_steps,
        )
        reasoning_result = retrieve_reasoning_algorithms(
            reasoning_store,
            reasoning_requirements,
            limit=reasoning_limit,
            include_ineligible=True,
        )
        selected_reasoning_id = reasoning_result.selected_reasoning_id

    missing: list[str] = []
    if task.require_mathematical_algorithm and selected_math is None:
        missing.append("MATHEMATICAL_ALGORITHM")
    if task.require_reasoning_algorithm and selected_reasoning_id is None:
        missing.append("REASONING_ALGORITHM")
    satisfied = not missing
    if satisfied:
        status = "QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND"
    elif selected_math is not None or selected_reasoning_id is not None:
        status = "PARTIAL_QUALIFIED_KNOWN_SOLUTION_FOUND"
    else:
        status = "NO_QUALIFIED_KNOWN_SOLUTION_FIT"
    decision_payload = {
        "version": UNIFIED_RETRIEVAL_VERSION,
        "problem_signature": problem_signature,
        "mathematical_fit_signatures": [item.fit_signature for item in math_candidates],
        "selected_mathematical_algorithm_id": selected_math.canonical_algorithm_id if selected_math else None,
        "reasoning_result_signature": reasoning_result.result_signature if reasoning_result else None,
        "selected_reasoning_id": selected_reasoning_id,
        "required_components_satisfied": satisfied,
        "missing_components": missing,
        "status": status,
    }
    return UnifiedRetrievalDecision(
        schema_version=1,
        retrieval_version=UNIFIED_RETRIEVAL_VERSION,
        problem_signature=problem_signature,
        mathematical_candidates=math_candidates,
        selected_mathematical_algorithm_id=selected_math.canonical_algorithm_id if selected_math else None,
        reasoning_result=reasoning_result,
        selected_reasoning_id=selected_reasoning_id,
        required_components_satisfied=satisfied,
        missing_components=tuple(missing),
        status=status,
        decision_signature=sha256_json(decision_payload),
    )
