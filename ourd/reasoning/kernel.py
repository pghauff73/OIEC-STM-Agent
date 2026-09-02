from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Iterable, Mapping, Sequence

from ..errors import PolicyError
from .ablation import AblationConfiguration
from .budget import derive_reasoning_budget, should_continue_reasoning
from .contradictions import (
    build_contradiction_records,
    cap_confidence_for_contradictions,
    unresolved_critical_contradictions,
)
from .context import choose_reasoning_operation
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
        ablation: AblationConfiguration | None = None,
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
        self.ablation = ablation or AblationConfiguration(path_count=self.max_candidates)

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
        candidate_cap = min(self.max_candidates, self.ablation.path_count)
        if provider_sample_cap is not None:
            candidate_cap = min(candidate_cap, max(1, int(provider_sample_cap)))
        budget = derive_reasoning_budget(
            dimension_budget=dimension_budget,
            uncertainty_bp=problem.uncertainty_bp,
            difficulty_bp=problem.difficulty_bp,
            verifier_disagreement_bp=verifier_disagreement_bp,
            configured_max_candidates=candidate_cap,
            configured_max_provider_calls=self.max_provider_calls,
            minimum_voi_bp=self.minimum_voi_bp,
        )
        if not self.ablation.adaptive_compute_enabled:
            candidate_count = min(self.ablation.path_count, budget.maximum_candidates)
            budget = replace(
                budget,
                candidate_count=candidate_count,
                verifier_count=candidate_count,
                falsifier_count=(
                    candidate_count
                    if not self.ablation.falsifier_enabled
                    else min(2, candidate_count)
                ),
                max_generation_attempts=(
                    candidate_count
                    if not self.ablation.diversity_filter_enabled
                    else min(budget.maximum_candidates, candidate_count * 2)
                ),
                signature="",
            )
        elif not self.ablation.falsifier_enabled:
            budget = replace(
                budget,
                falsifier_count=budget.candidate_count,
                signature="",
            )
        if not budget.signature:
            payload = asdict(budget)
            payload.pop("schema_version", None)
            payload.pop("signature", None)
            budget = replace(budget, signature=stable_hash(payload))
        return budget

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
        if not self.ablation.hypothesis_state_enabled:
            direct_material = {
                "problem_id": problem.problem_id,
                "proposition": problem.statement,
            }
            direct_id = f"hypothesis:{stable_hash(direct_material)}"
            active_state = self.build_hypothesis_state(
                (
                    {
                        "hypothesis_id": direct_id,
                        "proposition": problem.statement,
                        "prior_bp": SCORE_SCALE,
                        "posterior_bp": SCORE_SCALE,
                        "supporting_evidence": problem.evidence_ids,
                        "conflicting_evidence": (),
                        "assumptions": (),
                        "falsifiers": (),
                        "status": "ACTIVE",
                    },
                ),
                problem_id=problem.problem_id,
                max_hypotheses=1,
                mutually_exclusive=False,
            )
        elif isinstance(hypotheses, HypothesisSet):
            if hypotheses.problem_id != problem.problem_id:
                raise PolicyError("hypothesis state conflicts with reasoning problem")
            if len(hypotheses.hypotheses) > budget.max_hypotheses:
                raise PolicyError("hypothesis state exceeds the derived reasoning budget")
            if hypotheses.mutually_exclusive != problem.mutually_exclusive_hypotheses:
                raise PolicyError("hypothesis state exclusivity conflicts with reasoning problem")
            active_state = hypotheses
        else:
            active_state = self.build_hypothesis_state(
                hypotheses,
                problem_id=problem.problem_id,
                max_hypotheses=budget.max_hypotheses,
                mutually_exclusive=problem.mutually_exclusive_hypotheses,
            )
        active = active_state.hypotheses
        candidates = search_reasoning_candidates(
            provider=provider,
            problem=problem,
            hypotheses=active,
            declared_evidence_ids=declared,
            budget=budget,
            ablation=self.ablation,
        )
        falsifier_updates = ()
        if self.ablation.hypothesis_state_enabled and self.ablation.falsifier_enabled:
            active_state, falsifier_updates = self.apply_falsifier_updates(
                active_state,
                candidates=candidates,
            )
        active = active_state.hypotheses
        if falsifier_updates:
            candidates = replace(candidates, hypothesis_updates=falsifier_updates, signature="")
            candidate_payload = asdict(candidates)
            candidate_payload.pop("schema_version", None)
            candidate_payload.pop("signature", None)
            candidates = replace(candidates, signature=stable_hash(candidate_payload))
        topology = build_reasoning_topology(
            problem=problem,
            hypotheses=active,
            candidates=candidates,
        )
        internal_reasoning_evidence = tuple(
            sorted(
                {
                    *(report.report_id for report in candidates.verifier_reports),
                    *(report.report_id for report in candidates.falsifier_reports),
                }
            )
        )
        validate_reasoning_topology(
            topology,
            budget=budget,
            declared_evidence_ids=(*declared, *internal_reasoning_evidence),
        )
        certificate = self.certify(
            problem=problem,
            hypotheses=active,
            budget=budget,
            candidates=candidates,
            topology=topology,
            previous_certificate=previous_certificate,
        )
        if (
            certificate.decision == "ACCEPT"
            and candidates.selected_path_id
            and self.ablation.hypothesis_state_enabled
        ):
            active = self.support_selected_hypotheses(
                active,
                candidates=candidates,
            )
            certificate = self.certify(
                problem=problem,
                hypotheses=active,
                budget=budget,
                candidates=candidates,
                topology=topology,
                previous_certificate=previous_certificate,
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
        disagreement = self.verifier_disagreement_bp(candidates)
        selected_metrics = next(
            (item for item in candidates.metrics if item.path_id == candidates.selected_path_id),
            None,
        )
        contradictions = build_contradiction_records(candidates)
        critical_contradictions = unresolved_critical_contradictions(contradictions)
        confidence = cap_confidence_for_contradictions(
            derive_reasoning_confidence_bp(candidates),
            contradictions,
        )
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
            selected_contradiction_ids = tuple(
                item.contradiction_id
                for item in contradictions
                if item.left_claim_id.startswith(candidates.selected_path_id)
            )
            contradiction_count = len(selected_contradiction_ids)
        else:
            selected_contradiction_ids = tuple(
                item.contradiction_id for item in contradictions
            )
            contradiction_count = len(contradictions)
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
            if candidates.synthesis is not None and candidates.synthesis.verified:
                reasons.append("synthesis_verified")
            elif (
                candidates.synthesis is not None
                and (
                    not self.ablation.synthesis_verification_enabled
                    or not self.ablation.verifier_enabled
                )
            ):
                reasons.append("synthesis_verification_disabled")
            if critical_contradictions:
                reasons.append("critical_contradiction_unresolved")
            required_reasons = {
                "process_verified",
                "falsifier_survived",
                "derived_confidence",
                "uncertainty_not_increased",
                "assumptions_resolved",
                (
                    "synthesis_verified"
                    if (
                        self.ablation.synthesis_verification_enabled
                        and self.ablation.verifier_enabled
                    )
                    else "synthesis_verification_disabled"
                ),
            }
            if required_reasons <= set(reasons):
                decision = (
                    "STOP_UNRESOLVED" if critical_contradictions else "ACCEPT"
                )
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
        next_operation = choose_reasoning_operation(
            budget=budget,
            expected_gains_bp={
                "GENERATE_HYPOTHESIS": problem.uncertainty_bp if not candidates.selected_path_id else 0,
                "RETRIEVE_EVIDENCE": max(0, problem.uncertainty_bp - (
                    selected_metrics.evidence_support_bp if selected_metrics else 0
                )),
                "RUN_READ_ONLY_EXPERIMENT": max(0, uncertainty_after // 2),
                "VERIFY_AGAIN": disagreement,
                "SEARCH_COUNTEREXAMPLE": max(
                    0,
                    SCORE_SCALE
                    - (selected_metrics.falsifier_bp if selected_metrics else 0),
                ),
                "REFINE_DIMENSION": max(0, problem.difficulty_bp // 2),
            },
        )
        if decision in {"REVISE", "REGENERATE"} and next_operation.operation == "STOP":
            decision = "STOP_NO_VALUE"
            reasons.append("no_positive_value_of_information")
        if (
            decision == "ACCEPT"
            and previous_certificate is not None
            and previous_certificate.problem_hash == problem.signature
            and previous_certificate.ablation_config_hash == self.ablation.signature
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
        selected_verifier_score = selected_metrics.verifier_bp if selected_metrics else 0
        selected_falsifier_score = selected_metrics.falsifier_bp if selected_metrics else 0
        if decision == "ACCEPT":
            terminal_state = "SOLUTION"
        elif compute_spent >= budget.max_compute_bp:
            terminal_state = "COMPUTE_BUDGET_EXHAUSTED"
        elif not candidates.selected_path_id:
            terminal_state = "NO_SURVIVING_HYPOTHESIS"
        elif decision == "STOP_NO_VALUE":
            terminal_state = "EPISTEMIC_STOP"
        else:
            terminal_state = "INSUFFICIENT_EVIDENCE"
        hypothesis_signature = self.hypothesis_collection_signature(hypotheses)
        payload = {
            "problem_hash": problem.signature,
            "boundary_signature": problem.boundary_signature,
            "dimension_signature": problem.dimension_signature,
            "hypothesis_signature": hypothesis_signature,
            "topology_signature": topology.signature,
            "candidate_set_signature": candidates.signature,
            "synthesis_signature": (
                candidates.synthesis.signature if candidates.synthesis is not None else ""
            ),
            "score_config_id": candidates.score_config_id,
            "score_config_hash": candidates.score_config_hash,
            "ablation_id": self.ablation.ablation_id,
            "ablation_config_hash": self.ablation.signature,
            "active_hypothesis_ids": tuple(
                item.hypothesis_id for item in hypotheses if item.status != "FALSIFIED"
            ),
            "candidate_count": len(candidates.paths),
            "surviving_candidate_count": len(candidates.surviving_path_ids),
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
            "verifier_score_bp": selected_verifier_score,
            "falsification_score_bp": selected_falsifier_score,
            "contradiction_count": contradiction_count,
            "unresolved_contradiction_ids": selected_contradiction_ids,
            "uncertainty_before_bp": problem.uncertainty_bp,
            "uncertainty_after_bp": uncertainty_after,
            "disagreement_bp": disagreement,
            "residual_risk_bp": selected_metrics.risk_bp if selected_metrics else SCORE_SCALE,
            "compute_spent_bp": compute_spent,
            "unresolved_assumptions": unresolved_assumptions,
            "reasoning_topology_hash": topology.signature,
            "derived_confidence_bp": confidence,
            "decision": decision,
            "terminal_state": terminal_state,
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
    def hypothesis_collection_signature(hypotheses: Sequence[Hypothesis]) -> str:
        return stable_hash(
            [asdict(item) for item in sorted(hypotheses, key=lambda item: item.hypothesis_id)]
        )

    @staticmethod
    def apply_falsifier_updates(
        state: HypothesisSet,
        *,
        candidates: CandidateSet,
    ) -> tuple[HypothesisSet, tuple[Any, ...]]:
        paths = {path.path_id: path for path in candidates.paths}
        updates = []
        current = state
        for report in candidates.falsifier_reports:
            challenges = (
                *report.counterexamples,
                *report.alternative_explanations,
                *report.boundary_cases,
                *report.reversed_causal_directions,
                *report.invalid_invariants,
            )
            if not challenges and not report.contradicted_step_ids:
                continue
            path = paths[report.path_id]
            current, new_updates = apply_collision_update(
                current,
                objects=path.hypothesis_ids,
                falsifier=str(challenges[0] if challenges else "contradicted reasoning step"),
                evidence_ids=(report.report_id,),
                collision_id=f"reasoning-collision:{report.signature}",
                severity_bp=report.severity_bp,
            )
            updates.extend(new_updates)
        return current, tuple(sorted(updates, key=lambda item: item.update_id))

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
