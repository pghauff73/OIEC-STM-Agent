from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Iterable, Mapping, Sequence

from ..errors import PolicyError
from .budget import derive_reasoning_budget, should_continue_reasoning
from .hypotheses import apply_collision_update, build_hypothesis_set
from .models import (
    CandidateSet,
    Hypothesis,
    HypothesisSet,
    ReasoningBudget,
    ReasoningCertificate,
    ReasoningProblem,
    ReasoningTopology,
    SCORE_SCALE,
    bounded_score,
    stable_hash,
)
from .scoring import derive_reasoning_confidence_bp
from .search import search_reasoning_candidates
from .topology import (
    build_reasoning_topology,
    legacy_reasoning_topology_payload,
    reasoning_topology_payload,
    validate_reasoning_topology,
)


class SuperReasoningKernel:
    def __init__(
        self,
        *,
        max_candidates: int = 16,
        max_provider_calls: int = 64,
        minimum_voi_bp: int = 100,
        acceptance_confidence_bp: int = 5_000,
        acceptance_verifier_bp: int = 5_000,
        acceptance_falsifier_bp: int = 5_000,
    ):
        self.max_candidates = max(1, int(max_candidates))
        self.max_provider_calls = max(4, int(max_provider_calls))
        self.minimum_voi_bp = bounded_score(minimum_voi_bp, "minimum value of information")
        self.acceptance_confidence_bp = bounded_score(
            acceptance_confidence_bp,
            "reasoning acceptance confidence",
        )
        self.acceptance_verifier_bp = bounded_score(
            acceptance_verifier_bp,
            "reasoning acceptance verifier",
        )
        self.acceptance_falsifier_bp = bounded_score(
            acceptance_falsifier_bp,
            "reasoning acceptance falsifier",
        )

    @staticmethod
    def create_problem(
        *,
        statement: str,
        goal: str,
        source_snapshot_hash: str,
        boundary_signature: str,
        dimension_signature: str,
        evidence_ids: Iterable[str] = (),
        uncertainty_bp: int = 0,
        difficulty_bp: int = 0,
        mutually_exclusive_hypotheses: bool = False,
    ) -> ReasoningProblem:
        material = {
            "statement": str(statement).strip(),
            "goal": str(goal).strip(),
            "source_snapshot_hash": str(source_snapshot_hash),
            "boundary_signature": str(boundary_signature),
            "dimension_signature": str(dimension_signature),
            "evidence_ids": tuple(sorted({str(value) for value in evidence_ids if str(value)})),
            "uncertainty_bp": bounded_score(uncertainty_bp, "problem uncertainty"),
            "difficulty_bp": bounded_score(difficulty_bp, "problem difficulty"),
            "mutually_exclusive_hypotheses": bool(mutually_exclusive_hypotheses),
        }
        problem_id = f"problem:{stable_hash(material)}"
        return ReasoningProblem(
            problem_id=problem_id,
            **material,
            signature=stable_hash({**material, "problem_id": problem_id}),
        )

    @staticmethod
    def build_hypothesis_state(
        proposals: Sequence[Mapping[str, Any] | Hypothesis],
        *,
        problem_id: str,
        max_hypotheses: int,
        mutually_exclusive: bool = False,
    ) -> HypothesisSet:
        return build_hypothesis_set(
            proposals,
            problem_id=problem_id,
            max_hypotheses=max_hypotheses,
            mutually_exclusive=mutually_exclusive,
        )

    @staticmethod
    def build_hypotheses(
        proposals: Sequence[Mapping[str, Any] | Hypothesis],
        *,
        max_hypotheses: int,
        mutually_exclusive: bool = False,
    ) -> tuple[Hypothesis, ...]:
        return build_hypothesis_set(
            proposals,
            problem_id="compatibility:hypothesis-pool",
            max_hypotheses=max_hypotheses,
            mutually_exclusive=mutually_exclusive,
        ).hypotheses

    def derive_budget(
        self,
        *,
        dimension_budget: Any,
        problem: ReasoningProblem,
        verifier_disagreement_bp: int = 0,
        provider_sample_cap: int | None = None,
    ) -> ReasoningBudget:
        candidate_cap = self.max_candidates
        if provider_sample_cap is not None:
            candidate_cap = min(candidate_cap, max(1, int(provider_sample_cap)))
        return derive_reasoning_budget(
            dimension_budget=dimension_budget,
            uncertainty_bp=problem.uncertainty_bp,
            difficulty_bp=problem.difficulty_bp,
            verifier_disagreement_bp=verifier_disagreement_bp,
            configured_max_candidates=candidate_cap,
            configured_max_provider_calls=self.max_provider_calls,
            minimum_voi_bp=self.minimum_voi_bp,
        )

    def run(
        self,
        *,
        provider: Any,
        problem: ReasoningProblem,
        hypotheses: Sequence[Hypothesis] | HypothesisSet,
        dimension_budget: Any,
        declared_evidence_ids: Iterable[str],
        previous_certificate: ReasoningCertificate | None = None,
        previous_candidates: CandidateSet | None = None,
    ) -> tuple[
        tuple[Hypothesis, ...],
        ReasoningBudget,
        CandidateSet,
        ReasoningTopology,
        ReasoningCertificate,
    ]:
        declared = tuple(sorted({str(value) for value in declared_evidence_ids if str(value)}))
        if set(problem.evidence_ids) - set(declared):
            raise PolicyError("reasoning problem references unavailable evidence")
        disagreement = self.verifier_disagreement_bp(previous_candidates)
        provider_cap = int(
            getattr(getattr(provider, "config", None), "max_reasoning_samples", self.max_candidates)
        )
        budget = self.derive_budget(
            dimension_budget=dimension_budget,
            problem=problem,
            verifier_disagreement_bp=disagreement,
            provider_sample_cap=provider_cap,
        )
        if isinstance(hypotheses, HypothesisSet):
            if hypotheses.problem_id != problem.problem_id:
                raise PolicyError("hypothesis state conflicts with reasoning problem")
            if len(hypotheses.hypotheses) > budget.max_hypotheses:
                raise PolicyError("hypothesis state exceeds the derived reasoning budget")
            if hypotheses.mutually_exclusive != problem.mutually_exclusive_hypotheses:
                raise PolicyError("hypothesis state exclusivity conflicts with reasoning problem")
            active = hypotheses.hypotheses
        else:
            active = self.build_hypothesis_state(
                hypotheses,
                problem_id=problem.problem_id,
                max_hypotheses=budget.max_hypotheses,
                mutually_exclusive=problem.mutually_exclusive_hypotheses,
            ).hypotheses
        candidates = search_reasoning_candidates(
            provider=provider,
            problem=problem,
            hypotheses=active,
            declared_evidence_ids=declared,
            budget=budget,
        )
        topology = build_reasoning_topology(
            problem=problem,
            hypotheses=active,
            candidates=candidates,
        )
        validate_reasoning_topology(
            topology,
            budget=budget,
            declared_evidence_ids=declared,
        )
        certificate = self.certify(
            problem=problem,
            hypotheses=active,
            budget=budget,
            candidates=candidates,
            topology=topology,
            previous_certificate=previous_certificate,
        )
        if certificate.decision == "ACCEPT" and candidates.selected_path_id:
            active = self.support_selected_hypotheses(
                active,
                candidates=candidates,
            )
        return active, budget, candidates, topology, certificate

    def certify(
        self,
        *,
        problem: ReasoningProblem,
        hypotheses: Sequence[Hypothesis],
        budget: ReasoningBudget,
        candidates: CandidateSet,
        topology: ReasoningTopology,
        previous_certificate: ReasoningCertificate | None = None,
    ) -> ReasoningCertificate:
        selected_metrics = next(
            (item for item in candidates.metrics if item.path_id == candidates.selected_path_id),
            None,
        )
        confidence = derive_reasoning_confidence_bp(candidates)
        if candidates.selected_path_id:
            selected_verifier = next(
                report
                for report in candidates.verifier_reports
                if report.path_id == candidates.selected_path_id
            )
            selected_falsifier = next(
                report
                for report in candidates.falsifier_reports
                if report.path_id == candidates.selected_path_id
            )
            contradiction_count = len(selected_verifier.contradictions) + len(
                selected_falsifier.counterexamples
            )
        else:
            contradiction_count = sum(
                len(report.contradictions) for report in candidates.verifier_reports
            ) + sum(
                len(report.counterexamples) for report in candidates.falsifier_reports
            )
        selected_hypothesis_ids = {
            hypothesis_id
            for path in candidates.paths
            if path.path_id == candidates.selected_path_id
            for hypothesis_id in path.hypothesis_ids
        }
        unresolved_assumptions = tuple(
            sorted(
                {
                    assumption
                    for path in candidates.paths
                    if path.path_id == candidates.selected_path_id
                    for step in path.steps
                    for assumption in step.assumptions
                }
                | {
                    assumption
                    for hypothesis in hypotheses
                    if hypothesis.hypothesis_id in selected_hypothesis_ids
                    for assumption in hypothesis.assumptions
                }
            )
        )
        compute_spent = min(
            SCORE_SCALE,
            sum(path.estimated_cost_bp for path in candidates.paths),
        )
        uncertainty_after = (
            selected_metrics.uncertainty_bp if selected_metrics is not None else problem.uncertainty_bp
        )
        reasons = []
        decision = "STOP_UNRESOLVED"
        if selected_metrics is not None:
            if selected_metrics.verifier_bp >= self.acceptance_verifier_bp:
                reasons.append("process_verified")
            if selected_metrics.falsifier_bp >= self.acceptance_falsifier_bp:
                reasons.append("falsifier_survived")
            if confidence >= self.acceptance_confidence_bp:
                reasons.append("derived_confidence")
            if uncertainty_after <= problem.uncertainty_bp:
                reasons.append("uncertainty_not_increased")
            if not unresolved_assumptions:
                reasons.append("assumptions_resolved")
            if {
                "process_verified",
                "falsifier_survived",
                "derived_confidence",
                "uncertainty_not_increased",
                "assumptions_resolved",
            } <= set(reasons):
                decision = "ACCEPT"
            elif should_continue_reasoning(
                budget=budget,
                expected_quality_gain_bp=max(0, problem.uncertainty_bp - uncertainty_after),
                cost_bp=compute_spent,
                cost_weight=25,
            ):
                decision = "REVISE"
            else:
                decision = "STOP_NO_VALUE"
        elif should_continue_reasoning(
            budget=budget,
            expected_quality_gain_bp=problem.uncertainty_bp,
            cost_bp=compute_spent,
            cost_weight=25,
        ):
            decision = "REGENERATE"
            reasons.append("no_surviving_candidate")
        else:
            decision = "STOP_NO_VALUE"
            reasons.append("no_positive_value_of_information")
        if (
            decision == "ACCEPT"
            and previous_certificate is not None
            and previous_certificate.problem_hash == problem.signature
        ):
            improved = any(
                (
                    payload_value,
                    previous_value,
                    comparison,
                )
                for payload_value, previous_value, comparison in (
                    (
                        selected_metrics.evidence_support_bp if selected_metrics else 0,
                        previous_certificate.evidence_coverage_bp,
                        "greater",
                    ),
                    (
                        uncertainty_after,
                        previous_certificate.uncertainty_after_bp,
                        "less",
                    ),
                    (
                        contradiction_count,
                        previous_certificate.contradiction_count,
                        "less",
                    ),
                    (
                        confidence,
                        previous_certificate.derived_confidence_bp,
                        "greater",
                    ),
                )
                if (
                    payload_value > previous_value
                    if comparison == "greater"
                    else payload_value < previous_value
                )
            )
            if not improved:
                decision = "STOP_NO_VALUE"
                reasons = ["no_reasoning_progress"]
        payload = {
            "problem_hash": problem.signature,
            "boundary_signature": problem.boundary_signature,
            "dimension_signature": problem.dimension_signature,
            "active_hypothesis_ids": tuple(
                item.hypothesis_id for item in hypotheses if item.status != "FALSIFIED"
            ),
            "candidate_count": len(candidates.paths),
            "winning_candidate_id": candidates.selected_path_id,
            "verifier_report_ids": tuple(
                item.report_id for item in candidates.verifier_reports
            ),
            "falsifier_report_ids": tuple(
                item.report_id for item in candidates.falsifier_reports
            ),
            "evidence_coverage_bp": (
                selected_metrics.evidence_support_bp if selected_metrics is not None else 0
            ),
            "contradiction_count": contradiction_count,
            "uncertainty_before_bp": problem.uncertainty_bp,
            "uncertainty_after_bp": uncertainty_after,
            "compute_spent_bp": compute_spent,
            "unresolved_assumptions": unresolved_assumptions,
            "reasoning_topology_hash": topology.signature,
            "derived_confidence_bp": confidence,
            "decision": decision,
            "reasons": tuple(reasons),
        }
        certificate = ReasoningCertificate(**payload)
        canonical_payload = asdict(certificate)
        canonical_payload.pop("schema_version", None)
        canonical_payload.pop("signature", None)
        return replace(certificate, signature=stable_hash(canonical_payload))

    @staticmethod
    def require_problem_integrity(problem: ReasoningProblem) -> None:
        payload = asdict(problem)
        payload.pop("schema_version", None)
        signature = payload.pop("signature", "")
        if signature != stable_hash(payload):
            raise PolicyError("reasoning problem signature mismatch")

    @staticmethod
    def require_candidate_integrity(candidates: CandidateSet) -> None:
        payload = asdict(candidates)
        payload.pop("schema_version", None)
        signature = payload.pop("signature", "")
        if signature != stable_hash(payload):
            raise PolicyError("reasoning candidate-set signature mismatch")

    @staticmethod
    def require_topology_integrity(topology: ReasoningTopology) -> None:
        payload = reasoning_topology_payload(topology)
        if topology.signature == stable_hash(payload):
            return
        if topology.schema_version == 1 and topology.signature == stable_hash(
            legacy_reasoning_topology_payload(topology)
        ):
            return
        if topology.signature != stable_hash(payload):
            raise PolicyError("reasoning topology signature mismatch")

    @staticmethod
    def require_certificate_integrity(certificate: ReasoningCertificate) -> None:
        payload = asdict(certificate)
        payload.pop("schema_version", None)
        signature = payload.pop("signature", "")
        if signature != stable_hash(payload):
            raise PolicyError("reasoning certificate signature mismatch")

    @staticmethod
    def verifier_disagreement_bp(candidates: CandidateSet | None) -> int:
        if candidates is None or not candidates.verifier_reports:
            return 0
        counts: dict[str, int] = {}
        for report in candidates.verifier_reports:
            counts[report.verdict] = counts.get(report.verdict, 0) + 1
        majority = max(counts.values())
        return SCORE_SCALE - majority * SCORE_SCALE // len(candidates.verifier_reports)

    @staticmethod
    def support_selected_hypotheses(
        hypotheses: Sequence[Hypothesis],
        *,
        candidates: CandidateSet,
    ) -> tuple[Hypothesis, ...]:
        selected = next(
            path for path in candidates.paths if path.path_id == candidates.selected_path_id
        )
        selected_evidence = {
            evidence_id for step in selected.steps for evidence_id in step.evidence_ids
        }
        updated = []
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id not in selected.hypothesis_ids:
                updated.append(hypothesis)
                continue
            material = {
                **asdict(hypothesis),
                "supporting_evidence": tuple(
                    sorted(set(hypothesis.supporting_evidence) | selected_evidence)
                ),
                "status": "UNRESOLVED" if hypothesis.assumptions else "SUPPORTED",
            }
            material.pop("signature", None)
            updated.append(Hypothesis(**material, signature=stable_hash(material)))
        return tuple(sorted(updated, key=lambda item: item.hypothesis_id))

    @staticmethod
    def apply_collision(
        hypotheses: Sequence[Hypothesis],
        *,
        objects: Iterable[str],
        falsifier: str,
        evidence_ids: Iterable[str],
        severity_bp: int,
        mutually_exclusive: bool = False,
    ) -> tuple[Hypothesis, ...]:
        state = build_hypothesis_set(
            hypotheses,
            problem_id="compatibility:collision",
            max_hypotheses=max(1, len(hypotheses)),
            mutually_exclusive=mutually_exclusive,
        )
        collision_key = f"collision:{stable_hash({'objects': tuple(sorted(objects)), 'falsifier': falsifier, 'evidence_ids': tuple(sorted(evidence_ids)), 'severity_bp': severity_bp})}"
        updated, _ = apply_collision_update(
            state,
            objects=objects,
            falsifier=falsifier,
            evidence_ids=evidence_ids,
            collision_id=collision_key,
            severity_bp=severity_bp,
        )
        return updated.hypotheses


__all__ = ["SuperReasoningKernel"]
