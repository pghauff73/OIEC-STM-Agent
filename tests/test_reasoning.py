from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace
from types import SimpleNamespace

import ourd
from ourd import OURDAgent
from ourd.cfel import record_collision
from ourd.errors import PolicyError, ProviderError, StateError
from ourd.hypotheses import bounded_hypothesis_set
from ourd.models import DimensionBudget, RuntimeState
from ourd.persistence import EventStore, StateStore
from ourd.providers.base import ProviderConfig
from ourd.reasoning import (
    CandidateSet,
    FalsifierReport,
    Hypothesis,
    ReasoningBudget,
    ReasoningCertificate,
    ReasoningEdge,
    ReasoningMetrics,
    ReasoningNode,
    ReasoningPath,
    ReasoningStep,
    ReasoningTopology,
    SuperReasoningKernel,
    VerifierReport,
    derive_reasoning_budget,
    make_reasoning_edge,
    should_continue_reasoning,
    validate_reasoning_topology,
)
from ourd.reasoning.falsifier import falsify_reasoning_path
from ourd.reasoning.generator import (
    DEFAULT_PERSPECTIVES,
    parse_json_object,
    perspective_names,
    reasoning_object_tool,
)
from ourd.reasoning.models import SCORE_SCALE, stable_hash
from ourd.reasoning.scoring import derive_reasoning_confidence_bp, rank_reasoning_paths
from ourd.reasoning.verifier import PROCESS_CHECKS, verify_reasoning_path
from ourd.workspace import Workspace
from tests.helpers import RepoFixture


def response(text: str) -> SimpleNamespace:
    return SimpleNamespace(output=[], output_text=text)


class ReasoningToolSchemaTests(unittest.TestCase):
    def test_reasoning_object_tool_declares_openai_function_type(self) -> None:
        tool = reasoning_object_tool(("answer",), required_keys=("answer",))
        self.assertEqual("function", tool["type"])
        self.assertEqual("submit_oiec_reasoning_object", tool["name"])


class FakeReasoningProvider:
    def __init__(
        self,
        *,
        critical_falsifier: bool = False,
        reject_verifier: bool = False,
        conclusion: str = "Use the verified bounded candidate.",
        max_reasoning_samples: int = 64,
    ):
        self.config = ProviderConfig(
            model="fake-reasoning",
            max_reasoning_samples=max_reasoning_samples,
        )
        self.critical_falsifier = critical_falsifier
        self.reject_verifier = reject_verifier
        self.conclusion = conclusion
        self.requests = []

    def preflight(self):
        return {"status": "ready", "model": self.config.model}

    def create_response(self, *, instructions, input_items, tools):
        return self.create_responses(
            requests=[
                {
                    "instructions": instructions,
                    "input_items": input_items,
                    "tools": tools,
                }
            ],
            max_responses=1,
        )[0]

    def create_responses(self, *, requests, max_responses):
        if len(requests) > max_responses:
            raise ProviderError("fake provider cap exceeded")
        values = []
        for request in requests:
            self.requests.append(request)
            instructions = request["instructions"].casefold()
            payload = json.loads(request["input_items"][0]["content"])
            if "proposer" in instructions:
                problem = payload["problem"]
                inference_by_perspective = {
                    "direct": "deductive",
                    "mechanistic": "causal",
                    "counterexample_first": "defeasible",
                    "assumption_inversion": "abductive",
                    "causal": "inductive",
                    "mathematical": "computational",
                    "evidence_synthesis": "probabilistic",
                    "abductive": "analogical",
                }
                hypothesis_ids = [item["hypothesis_id"] for item in payload["hypotheses"]]
                evidence_ids = problem.get("evidence_ids", [])
                values.append(
                    response(
                        json.dumps(
                            {
                                "conclusion": self.conclusion,
                                "hypothesis_ids": hypothesis_ids[:1],
                                "provider_confidence_bp": 10_000,
                                "estimated_cost_bp": 500,
                                "goal_relevance_bp": 9_000,
                                "risk_bp": 500,
                                "steps": [
                                    {
                                        "claim": f"The {payload['perspective']} path supports the bounded candidate.",
                                        "premises": ["problem", *hypothesis_ids[:1]],
                                        "evidence_ids": evidence_ids[:1],
                                        "inference": inference_by_perspective.get(
                                            payload["perspective"], "constraint"
                                        ),
                                        "confidence_bp": 10_000,
                                        "assumptions": [],
                                        "falsifier": "A declared counterexample defeats this step.",
                                    }
                                ],
                            }
                        )
                    )
                )
            elif "process verifier" in instructions:
                candidate = payload["candidate"]
                checks = {name: not self.reject_verifier for name in PROCESS_CHECKS}
                values.append(
                    response(
                        json.dumps(
                            {
                                "steps": [
                                    {
                                        "step_id": item["step_id"],
                                        "checks": checks,
                                        "failures": [],
                                    }
                                    for item in candidate["steps"]
                                ],
                                "contradictions": [],
                            }
                        )
                    )
                )
            elif "falsifier" in instructions:
                candidate = payload["candidate"]
                values.append(
                    response(
                        json.dumps(
                            {
                                "searched_falsifiers": ["declared counterexample"],
                                "counterexamples": (
                                    ["critical counterexample"] if self.critical_falsifier else []
                                ),
                                "contradicted_step_ids": (
                                    [candidate["steps"][0]["step_id"]]
                                    if self.critical_falsifier
                                    else []
                                ),
                                "unresolved_defeat_conditions": [],
                                "critical": self.critical_falsifier,
                                "survival_bp": 9_000,
                            }
                        )
                    )
                )
            elif "synthesizer" in instructions:
                values.append(
                    response(
                        json.dumps(
                            {
                                "conclusion": "The verified bounded candidate wins.",
                                "source_path_ids": [payload["selected_winner"]],
                            }
                        )
                    )
                )
            else:
                raise AssertionError(f"unexpected reasoning role: {request['instructions']}")
        return values


class MalformedReasoningProvider(FakeReasoningProvider):
    def create_responses(self, *, requests, max_responses):
        self.requests.extend(requests)
        return [response("not-json") for _ in requests]


class BatchReasoningProvider(FakeReasoningProvider):
    reasoning_role_batch_size = 2

    def create_responses(self, *, requests, max_responses):
        values = []
        for request in requests:
            instructions = request["instructions"].casefold()
            payload = json.loads(request["input_items"][0]["content"])
            if "proposer micro-batch" in instructions:
                self.requests.append(request)
                hypothesis_ids = [item["hypothesis_id"] for item in payload["hypotheses"]]
                evidence_ids = payload["problem"].get("evidence_ids", [])
                candidates = []
                for item in payload["requests"]:
                    perspective = item["perspective"]
                    candidates.append(
                        {
                            "conclusion": self.conclusion,
                            "hypothesis_ids": hypothesis_ids[:1],
                            "provider_confidence_bp": 10_000,
                            "estimated_cost_bp": 500,
                            "goal_relevance_bp": 9_000,
                            "risk_bp": 500,
                            "steps": [
                                {
                                    "claim": f"The {perspective} path supports the bounded candidate.",
                                    "premises": ["problem", *hypothesis_ids[:1]],
                                    "evidence_ids": evidence_ids[:1],
                                    "inference": item["perspective_contract"][
                                        "primary_inference_mode"
                                    ],
                                    "confidence_bp": 10_000,
                                    "assumptions": [],
                                    "falsifier": "A declared counterexample defeats this step.",
                                }
                            ],
                        }
                    )
                values.append(response(json.dumps({"candidates": candidates})))
            elif "verifier micro-batch" in instructions:
                self.requests.append(request)
                reports = []
                for candidate in payload["candidates"]:
                    reports.append(
                        {
                            "steps": [
                                {
                                    "step_id": step["step_id"],
                                    "all_checks_evaluated": True,
                                    "failed_checks": [],
                                    "failures": [],
                                }
                                for step in candidate["steps"]
                            ],
                            "contradictions": [],
                            "missing_assumptions": [],
                        }
                    )
                values.append(response(json.dumps({"reports": reports})))
            elif "falsifier micro-batch" in instructions:
                self.requests.append(request)
                reports = [
                    {
                        "searched_falsifiers": ["declared counterexample"],
                        "counterexamples": [],
                        "contradicted_step_ids": [],
                        "unresolved_defeat_conditions": [],
                        "critical": False,
                        "survival_bp": 9_000,
                    }
                    for _candidate in payload["candidates"]
                ]
                values.append(response(json.dumps({"reports": reports})))
            else:
                values.extend(
                    super().create_responses(requests=(request,), max_responses=max_responses)
                )
        return values


def dimension_budget(*, candidates: int = 4, hypotheses: int = 4) -> DimensionBudget:
    return DimensionBudget(
        max_active_objects=8,
        max_active_relations=128,
        max_active_dimensions=4,
        max_active_hypotheses=hypotheses,
        max_candidate_actions=candidates,
        max_active_evidence_atoms=16,
        max_decomposition_depth=4,
        max_branch_factor=4,
    )


def problem(kernel: SuperReasoningKernel, *, evidence_ids=("e1",), uncertainty_bp=0):
    return kernel.create_problem(
        statement="Which bounded candidate should be selected?",
        goal="Select the strongest evidence-grounded candidate",
        source_snapshot_hash="snapshot",
        boundary_signature="boundary",
        dimension_signature="dimension",
        evidence_ids=evidence_ids,
        uncertainty_bp=uncertainty_bp,
        difficulty_bp=0,
        mutually_exclusive_hypotheses=True,
    )


def hypotheses():
    return (
        Hypothesis(
            hypothesis_id="h1",
            proposition="The bounded candidate is valid.",
            prior_bp=SCORE_SCALE,
            posterior_bp=SCORE_SCALE,
            supporting_evidence=("e1",),
            falsifiers=("critical counterexample",),
            status="ACTIVE",
            signature="h1-signature",
        ),
    )


def simple_path(path_id: str, *, confidence: int = 8_000) -> ReasoningPath:
    step = ReasoningStep(
        step_id="step-01",
        claim="A bounded claim.",
        premises=("problem", "h1"),
        evidence_ids=("e1",),
        inference="deductive",
        confidence_bp=confidence,
        falsifier="counterexample",
        signature=f"{path_id}-step",
    )
    return ReasoningPath(
        path_id=path_id,
        perspective=path_id,
        hypothesis_ids=("h1",),
        steps=(step,),
        conclusion="Use the bounded candidate.",
        provider_confidence_bp=confidence,
        estimated_cost_bp=500,
        goal_relevance_bp=8_000,
        risk_bp=500,
        signature=f"{path_id}-signature",
    )


class ReasoningModelTests(unittest.TestCase):
    def test_qwen_thinking_prefix_is_not_part_of_structured_state(self) -> None:
        payload = parse_json_object(
            "private scratch content\n</think>\n```json\n{\"answer\": 42}\n```"
        )
        self.assertEqual({"answer": 42}, payload)

    def test_all_requested_reasoning_primitives_are_public(self) -> None:
        names = (
            "ReasoningProblem",
            "Hypothesis",
            "HypothesisSet",
            "HypothesisUpdateRecord",
            "ReasoningNode",
            "ReasoningEdge",
            "ReasoningTopology",
            "ReasoningStep",
            "ReasoningPath",
            "VerifierReport",
            "FalsifierReport",
            "CandidateSet",
            "ReasoningMetrics",
            "ReasoningCertificate",
            "ReasoningBudget",
            "SuperReasoningKernel",
        )
        self.assertEqual(len(names), 16)
        for name in names:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(ourd, name))

    def test_hypothesis_status_and_scores_are_bounded(self) -> None:
        with self.assertRaises(ValueError):
            Hypothesis("h", "claim", posterior_bp=10_001)
        with self.assertRaises(ValueError):
            Hypothesis("h", "claim", status="CERTAIN")

    def test_mutually_exclusive_posteriors_are_normalized(self) -> None:
        kernel = SuperReasoningKernel()
        normalized = kernel.build_hypotheses(
            [
                {"hypothesis_id": "a", "proposition": "A", "posterior_bp": 4_000},
                {"hypothesis_id": "b", "proposition": "B", "posterior_bp": 4_000},
            ],
            max_hypotheses=4,
            mutually_exclusive=True,
        )
        self.assertEqual((5_000, 5_000), tuple(item.posterior_bp for item in normalized))


class ReasoningTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = ReasoningBudget(
            maximum_candidates=4,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
        )

    def test_topology_rejects_unknown_nodes(self) -> None:
        topology = ReasoningTopology(
            problem_id="p",
            nodes=(ReasoningNode("a", "claim", "A"),),
            edges=(ReasoningEdge("e", "a", "missing", "supports"),),
        )
        with self.assertRaises(PolicyError):
            validate_reasoning_topology(topology, budget=self.budget, declared_evidence_ids=())

    def test_positive_reasoning_cycle_fails_closed(self) -> None:
        topology = ReasoningTopology(
            problem_id="p",
            nodes=(ReasoningNode("a", "claim", "A"), ReasoningNode("b", "claim", "B")),
            edges=(
                ReasoningEdge("e1", "a", "b", "supports"),
                ReasoningEdge("e2", "b", "a", "entails"),
            ),
        )
        with self.assertRaises(PolicyError):
            validate_reasoning_topology(topology, budget=self.budget, declared_evidence_ids=())

    def test_contradiction_edges_may_point_backward(self) -> None:
        topology = ReasoningTopology(
            problem_id="p",
            nodes=(ReasoningNode("a", "claim", "A"), ReasoningNode("b", "counterexample", "B")),
            edges=(
                make_reasoning_edge("a", "b", "supports", "deductive"),
                make_reasoning_edge("b", "a", "contradicts", "defeasible"),
            ),
        )
        validate_reasoning_topology(topology, budget=self.budget, declared_evidence_ids=())

    def test_topology_signature_is_order_independent(self) -> None:
        nodes = (ReasoningNode("a", "claim", "A"), ReasoningNode("b", "claim", "B"))
        edges = (ReasoningEdge("e", "a", "b", "supports"),)
        first = ReasoningTopology(problem_id="p", nodes=nodes, edges=edges)
        second = ReasoningTopology(problem_id="p", nodes=tuple(reversed(nodes)), edges=edges)
        material = lambda value: {
            "problem_id": value.problem_id,
            "nodes": [asdict(item) for item in value.nodes],
            "edges": [asdict(item) for item in value.edges],
        }
        self.assertEqual(stable_hash(material(first)), stable_hash(material(second)))

    def test_decision_requires_traceable_candidate_conclusion(self) -> None:
        topology = ReasoningTopology(
            problem_id="p",
            nodes=(ReasoningNode("decision:p", "decision", "Choose A", path_id="path:a"),),
            edges=(),
        )
        with self.assertRaises(PolicyError):
            validate_reasoning_topology(topology, budget=self.budget, declared_evidence_ids=())

    def test_reasoning_branch_factor_is_enforced(self) -> None:
        budget = replace(self.budget, max_branch_factor=1)
        topology = ReasoningTopology(
            problem_id="p",
            nodes=(
                ReasoningNode("a", "claim", "A"),
                ReasoningNode("b", "claim", "B"),
                ReasoningNode("c", "claim", "C"),
            ),
            edges=(
                ReasoningEdge("e1", "a", "b", "entails"),
                ReasoningEdge("e2", "a", "c", "entails"),
            ),
        )
        with self.assertRaises(PolicyError):
            validate_reasoning_topology(topology, budget=budget, declared_evidence_ids=())


class ReasoningBudgetTests(unittest.TestCase):
    def test_default_four_perspectives_are_independent(self) -> None:
        self.assertEqual(DEFAULT_PERSPECTIVES[:4], perspective_names(4))
        self.assertEqual(4, len(set(perspective_names(4))))

    def test_candidate_count_is_capped_by_dimension_budget(self) -> None:
        budget = derive_reasoning_budget(
            dimension_budget=dimension_budget(candidates=2),
            uncertainty_bp=10_000,
            difficulty_bp=10_000,
            verifier_disagreement_bp=10_000,
        )
        self.assertEqual(2, budget.candidate_count)

    def test_adaptive_compute_increases_with_uncertainty(self) -> None:
        low = derive_reasoning_budget(
            dimension_budget=dimension_budget(candidates=16),
            uncertainty_bp=0,
            difficulty_bp=0,
        )
        high = derive_reasoning_budget(
            dimension_budget=dimension_budget(candidates=16),
            uncertainty_bp=10_000,
            difficulty_bp=10_000,
        )
        self.assertGreater(high.candidate_count, low.candidate_count)

    def test_no_positive_value_of_information_stops_search(self) -> None:
        budget = ReasoningBudget(
            maximum_candidates=4,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
            minimum_voi_bp=100,
        )

    def test_provider_sample_cap_limits_kernel_budget(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=16)
        provider = FakeReasoningProvider(max_reasoning_samples=2)
        _, budget, candidates, _, _ = kernel.run(
            provider=provider,
            problem=problem(kernel, uncertainty_bp=10_000),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(candidates=16),
            declared_evidence_ids=("e1",),
        )
        self.assertEqual(2, budget.candidate_count)
        self.assertEqual(2, len(candidates.paths))
        self.assertFalse(
            should_continue_reasoning(
                budget=budget,
                expected_quality_gain_bp=100,
                cost_bp=1_000,
            )
        )

    def test_invalid_proposer_uses_next_bounded_perspective(self) -> None:
        class FirstInvalidProposer(FakeReasoningProvider):
            def __init__(self) -> None:
                super().__init__(max_reasoning_samples=2)
                self.invalidated = False
                self.repairs = []

            def create_responses(self, *, requests, max_responses):
                values = super().create_responses(
                    requests=requests,
                    max_responses=max_responses,
                )
                revised = []
                for request, value in zip(requests, values):
                    if "proposer" in request["instructions"].casefold() and not self.invalidated:
                        self.invalidated = True
                        value = response(json.dumps({"conclusion": "", "steps": []}))
                    revised.append(value)
                return revised

            def record_reasoning_repair(self, *, role, reason, item_ids):
                self.repairs.append((role, reason, tuple(item_ids)))

        kernel = SuperReasoningKernel(max_candidates=16)
        provider = FirstInvalidProposer()
        _, budget, candidates, _, certificate = kernel.run(
            provider=provider,
            problem=problem(kernel, uncertainty_bp=10_000),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(candidates=16),
            declared_evidence_ids=("e1",),
        )
        self.assertEqual(2, budget.candidate_count)
        self.assertEqual(4, budget.max_generation_attempts)
        self.assertEqual(2, len(candidates.paths))
        self.assertEqual("ACCEPT", certificate.decision)
        self.assertTrue(provider.repairs)
        self.assertEqual("proposer", provider.repairs[0][0])
        self.assertIn("conclusion and non-empty steps", provider.repairs[0][1])

    def test_four_path_role_micro_batches_use_ten_provider_calls(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        provider = BatchReasoningProvider()
        _, budget, candidates, _, certificate = kernel.run(
            provider=provider,
            problem=problem(kernel, uncertainty_bp=5_000),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(candidates=4),
            declared_evidence_ids=("e1",),
        )
        self.assertEqual(4, budget.candidate_count)
        self.assertEqual(4, len(candidates.paths))
        self.assertEqual("ACCEPT", certificate.decision)
        self.assertEqual(10, len(provider.requests))
        final_request = provider.requests[-1]
        self.assertIn("verifier micro-batch", final_request["instructions"].casefold())
        final_payload = json.loads(final_request["input_items"][0]["content"])
        self.assertEqual(1, len(final_payload["candidates"]))


class VerificationAndScoringTests(unittest.TestCase):
    def test_rejected_candidate_cannot_poison_validated_topology(self) -> None:
        class OneInvalidEvidenceProvider(FakeReasoningProvider):
            def create_responses(self, *, requests, max_responses):
                values = super().create_responses(
                    requests=requests,
                    max_responses=max_responses,
                )
                revised = []
                for request, value in zip(requests, values):
                    instructions = request["instructions"].casefold()
                    supplied = json.loads(request["input_items"][0]["content"])
                    if (
                        "proposer" in instructions
                        and supplied.get("perspective") == "mechanistic"
                    ):
                        payload = json.loads(value.output_text)
                        payload["steps"][0]["evidence_ids"] = ["undeclared:evidence"]
                        value = response(json.dumps(payload))
                    revised.append(value)
                return revised

        kernel = SuperReasoningKernel(max_candidates=2)
        _, _, candidates, topology, certificate = kernel.run(
            provider=OneInvalidEvidenceProvider(),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(candidates=2),
            declared_evidence_ids=("e1",),
        )
        rejected = next(
            path
            for path in candidates.paths
            if next(
                report
                for report in candidates.verifier_reports
                if report.path_id == path.path_id
            ).verdict
            == "REJECT"
        )
        self.assertNotIn(rejected.path_id, candidates.surviving_path_ids)
        self.assertFalse(any(node.path_id == rejected.path_id for node in topology.nodes))
        self.assertEqual("ACCEPT", certificate.decision)

    def test_weakest_step_controls_path_verifier_score(self) -> None:
        first = ReasoningStep(
            "step-01", "First", premises=("problem", "h1"), evidence_ids=("e1",), confidence_bp=8_000
        )
        second = ReasoningStep(
            "step-02", "Second", premises=("step-01",), evidence_ids=("e1",), confidence_bp=8_000
        )
        path = replace(simple_path("p"), steps=(first, second))
        checks = {name: True for name in PROCESS_CHECKS}
        weak_checks = dict(checks)
        for name in PROCESS_CHECKS[:4]:
            weak_checks[name] = False
        report = verify_reasoning_path(
            path=path,
            hypotheses=hypotheses(),
            declared_evidence_ids=("e1",),
            payload={
                "steps": [
                    {"step_id": "step-01", "checks": checks, "failures": []},
                    {"step_id": "step-02", "checks": weak_checks, "failures": []},
                ],
                "contradictions": [],
            },
        )
        self.assertEqual(0, report.score_bp)
        self.assertEqual("REJECT", report.verdict)

    def test_missing_evidence_rejects_candidate(self) -> None:
        path = simple_path("p")
        report = verify_reasoning_path(
            path=path,
            hypotheses=hypotheses(),
            declared_evidence_ids=(),
            payload={
                "steps": [
                    {
                        "step_id": "step-01",
                        "checks": {name: True for name in PROCESS_CHECKS},
                        "failures": [],
                    }
                ],
                "contradictions": [],
            },
        )
        self.assertEqual(0, report.score_bp)
        self.assertEqual("REJECT", report.verdict)

    def test_untraceable_grounding_rejects_candidate(self) -> None:
        path = replace(
            simple_path("p"),
            steps=(
                ReasoningStep(
                    "step-01",
                    "Unsupported claim",
                    premises=("h1",),
                    confidence_bp=8_000,
                ),
            ),
        )
        report = verify_reasoning_path(
            path=path,
            hypotheses=(
                Hypothesis(
                    "h1",
                    "Unsupported hypothesis",
                    prior_bp=5_000,
                    posterior_bp=5_000,
                ),
            ),
            declared_evidence_ids=(),
            payload={
                "steps": [
                    {
                        "step_id": "step-01",
                        "checks": {name: True for name in PROCESS_CHECKS},
                        "failures": [],
                    }
                ],
                "contradictions": [],
            },
        )
        self.assertEqual("REJECT", report.verdict)
        self.assertIn("step-01: no grounding trace", report.failures)

    def test_critical_falsifier_prevents_selection(self) -> None:
        path = simple_path("p")
        report = falsify_reasoning_path(
            path=path,
            payload={
                "searched_falsifiers": ["counterexample"],
                "counterexamples": ["found"],
                "contradicted_step_ids": ["step-01"],
                "unresolved_defeat_conditions": [],
                "critical": True,
                "survival_bp": 10_000,
            },
        )
        self.assertEqual(0, report.survival_bp)
        self.assertEqual("REJECT", report.verdict)

    def test_candidate_ties_use_lexical_path_id(self) -> None:
        paths = (simple_path("path:b"), simple_path("path:a"))
        reports = tuple(
            VerifierReport(f"v:{path.path_id}", path.path_id, (("step-01", 8_000),), score_bp=8_000, verdict="ACCEPT")
            for path in paths
        )
        falsifiers = tuple(
            FalsifierReport(f"f:{path.path_id}", path.path_id, survival_bp=8_000, verdict="SURVIVES")
            for path in paths
        )
        metrics = tuple(
            ReasoningMetrics(path.path_id, total_score_bp=5_000) for path in paths
        )
        ranked = rank_reasoning_paths(
            paths=paths,
            metrics=metrics,
            verifier_reports=reports,
            falsifier_reports=falsifiers,
        )
        self.assertEqual("path:a", ranked[0].path_id)

    def test_provider_confidence_cannot_override_verifier(self) -> None:
        path = simple_path("path:a", confidence=10_000)
        candidates = CandidateSet(
            problem_id="p",
            paths=(path,),
            verifier_reports=(VerifierReport("v", path.path_id, score_bp=0, verdict="REJECT"),),
            falsifier_reports=(FalsifierReport("f", path.path_id, survival_bp=0, verdict="REJECT"),),
            metrics=(ReasoningMetrics(path.path_id, uncertainty_bp=10_000),),
            selected_path_id=path.path_id,
        )
        self.assertLess(derive_reasoning_confidence_bp(candidates), 5_000)


class SuperReasoningKernelTests(unittest.TestCase):
    def test_top_two_candidates_are_falsified(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        provider = FakeReasoningProvider()
        _, _, candidates, _, certificate = kernel.run(
            provider=provider,
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        falsifier_calls = [
            item
            for item in provider.requests
            if "adversarial oiec-sr falsifier" in item["instructions"].casefold()
        ]
        self.assertEqual(2, len(falsifier_calls))
        self.assertEqual("ACCEPT", certificate.decision)
        self.assertTrue(candidates.selected_path_id)

    def test_accepted_winner_marks_selected_hypothesis_supported(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        active = kernel.run(
            provider=FakeReasoningProvider(),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )[0]
        self.assertEqual("SUPPORTED", active[0].status)

    def test_new_candidate_wording_alone_is_not_reasoning_progress(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        reasoning_problem = problem(kernel)
        first = kernel.run(
            provider=FakeReasoningProvider(conclusion="Candidate wording A"),
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        second = kernel.run(
            provider=FakeReasoningProvider(conclusion="Candidate wording B"),
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
            previous_certificate=first[-1],
            previous_candidates=first[2],
        )
        self.assertEqual("STOP_NO_VALUE", second[-1].decision)
        self.assertEqual(("no_reasoning_progress",), second[-1].reasons)

    def test_unresolved_hypothesis_assumption_blocks_acceptance(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        assumed = replace(hypotheses()[0], assumptions=("The input is complete.",))
        active, _, _, _, certificate = kernel.run(
            provider=FakeReasoningProvider(),
            problem=problem(kernel),
            hypotheses=(assumed,),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        self.assertNotEqual("ACCEPT", certificate.decision)
        self.assertEqual(("The input is complete.",), certificate.unresolved_assumptions)
        self.assertEqual("ACTIVE", active[0].status)

    def test_identical_inputs_have_identical_certificate(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        inputs = {
            "problem": problem(kernel),
            "hypotheses": hypotheses(),
            "dimension_budget": dimension_budget(),
            "declared_evidence_ids": ("e1",),
        }
        first = kernel.run(provider=FakeReasoningProvider(), **inputs)[-1]
        second = kernel.run(provider=FakeReasoningProvider(), **inputs)[-1]
        self.assertEqual(first.signature, second.signature)

    def test_honest_stop_when_falsification_defeats_every_candidate(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        certificate = kernel.run(
            provider=FakeReasoningProvider(critical_falsifier=True),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )[-1]
        self.assertIn(certificate.decision, {"STOP_NO_VALUE", "STOP_UNRESOLVED", "REGENERATE"})
        self.assertFalse(certificate.winning_candidate_id)

    def test_super_reasoning_kernel_cannot_mutate_workspace(self) -> None:
        fixture = RepoFixture()
        try:
            workspace = Workspace(fixture.root)
            before = workspace.snapshot_hash()
            kernel = SuperReasoningKernel(max_candidates=4)
            kernel.run(
                provider=FakeReasoningProvider(),
                problem=problem(kernel),
                hypotheses=hypotheses(),
                dimension_budget=dimension_budget(),
                declared_evidence_ids=("e1",),
            )
            self.assertEqual(before, workspace.snapshot_hash())
        finally:
            fixture.close()


class ReasoningPersistenceAndIntegrationTests(unittest.TestCase):
    def test_runtime_v2_preserves_production_hypothesis_state(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            state_dir.mkdir()
            production_state, _ = bounded_hypothesis_set(
                None,
                [
                    {
                        "proposition": "Parser precedence is wrong",
                        "model_prior_bp": 4_000,
                        "assumptions": ["same grammar"],
                        "predictions": ["nested parse differs"],
                        "falsifiers": ["baseline parser matches"],
                    }
                ],
                max_hypotheses=4,
            )
            payload = RuntimeState(hypothesis_state=production_state).to_dict()
            payload["schema_version"] = 2
            for key in (
                "reasoning_problem",
                "reasoning_hypothesis_state",
                "hypothesis_pool",
                "hypothesis_updates",
                "reasoning_topology",
                "reasoning_candidates",
                "last_reasoning_certificate",
                "reasoning_transition_index",
            ):
                payload.pop(key, None)
            (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")
            store = StateStore(state_dir)
            try:
                migrated = store.load()
                self.assertEqual(6, migrated.schema_version)
                self.assertEqual(production_state.signature, migrated.hypothesis_state.signature)
                self.assertIsNone(migrated.reasoning_hypothesis_state)
            finally:
                store.close()
        finally:
            fixture.close()

    def test_runtime_v5_moves_legacy_sr_hypothesis_state_to_reasoning_key(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            state_dir.mkdir()
            kernel = SuperReasoningKernel()
            reasoning_problem = problem(kernel)
            reasoning_state = kernel.build_hypothesis_state(
                hypotheses(),
                problem_id=reasoning_problem.problem_id,
                max_hypotheses=4,
                mutually_exclusive=True,
            )
            state = RuntimeState(reasoning_problem=reasoning_problem)
            state.set_reasoning_hypothesis_state(reasoning_state)
            payload = state.to_dict()
            payload["schema_version"] = 5
            payload["hypothesis_state"] = payload.pop("reasoning_hypothesis_state")
            (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")
            store = StateStore(state_dir)
            try:
                migrated = store.load()
                self.assertEqual(6, migrated.schema_version)
                self.assertIsNone(migrated.hypothesis_state)
                self.assertEqual(
                    reasoning_state.signature,
                    migrated.reasoning_hypothesis_state.signature,
                )
            finally:
                store.close()
        finally:
            fixture.close()

    def test_runtime_v2_migrates_to_v6(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            state_dir.mkdir()
            payload = RuntimeState().to_dict()
            payload["schema_version"] = 2
            for key in (
                "reasoning_problem",
                "hypothesis_pool",
                "reasoning_hypothesis_state",
                "hypothesis_updates",
                "reasoning_topology",
                "reasoning_candidates",
                "last_reasoning_certificate",
                "reasoning_transition_index",
            ):
                payload.pop(key, None)
            (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")
            store = StateStore(state_dir)
            try:
                migrated = store.load()
                self.assertEqual(6, migrated.schema_version)
                events = list(EventStore(state_dir / "events.jsonl").events())
                self.assertEqual({"from_schema": 2, "to_schema": 6}, events[0]["payload"]["migration"])
            finally:
                store.close()
        finally:
            fixture.close()

    def test_runtime_v3_migrates_pool_to_authoritative_hypothesis_state(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            state_dir.mkdir()
            kernel = SuperReasoningKernel()
            reasoning_problem = problem(kernel)
            hypothesis = hypotheses()[0]
            payload = RuntimeState(
                reasoning_problem=reasoning_problem,
                reasoning_hypothesis_pool={hypothesis.hypothesis_id: hypothesis},
            ).to_dict()
            payload["schema_version"] = 3
            payload.pop("reasoning_hypothesis_state", None)
            payload.pop("hypothesis_updates", None)
            (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")
            store = StateStore(state_dir)
            try:
                migrated = store.load()
                self.assertEqual(6, migrated.schema_version)
                self.assertIsNotNone(migrated.reasoning_hypothesis_state)
                self.assertEqual(
                    reasoning_problem.problem_id,
                    migrated.reasoning_hypothesis_state.problem_id,
                )
                self.assertEqual(
                    migrated.reasoning_hypothesis_state.hypotheses[0],
                    migrated.reasoning_hypothesis_pool[hypothesis.hypothesis_id],
                )
                self.assertEqual([], migrated.reasoning_hypothesis_updates)
                events = list(EventStore(state_dir / "events.jsonl").events())
                self.assertEqual(
                    {"from_schema": 3, "to_schema": 6},
                    events[0]["payload"]["migration"],
                )
            finally:
                store.close()
        finally:
            fixture.close()

    def test_reasoning_state_round_trips(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            store = StateStore(state_dir)
            kernel = SuperReasoningKernel(max_candidates=4)
            reasoning_problem = problem(kernel)
            active, _, candidates, topology, certificate = kernel.run(
                provider=FakeReasoningProvider(),
                problem=reasoning_problem,
                hypotheses=hypotheses(),
                dimension_budget=dimension_budget(),
                declared_evidence_ids=("e1",),
            )
            state = RuntimeState(
                reasoning_problem=reasoning_problem,
                reasoning_topology=topology,
                reasoning_candidates=candidates,
                last_reasoning_certificate=certificate,
                reasoning_transition_index=1,
            )
            state.set_reasoning_hypothesis_state(
                kernel.build_hypothesis_state(
                    active,
                    problem_id=reasoning_problem.problem_id,
                    max_hypotheses=4,
                    mutually_exclusive=reasoning_problem.mutually_exclusive_hypotheses,
                )
            )
            store.save(state)
            store.close()
            reopened = StateStore(state_dir)
            try:
                loaded = reopened.load()
                self.assertEqual(certificate.signature, loaded.last_reasoning_certificate.signature)
                self.assertEqual(candidates.signature, loaded.reasoning_candidates.signature)
                self.assertEqual(topology.signature, loaded.reasoning_topology.signature)
                self.assertEqual(
                    state.reasoning_hypothesis_state.signature,
                    loaded.reasoning_hypothesis_state.signature,
                )
            finally:
                reopened.close()
        finally:
            fixture.close()

    def test_hypothesis_projection_drift_fails_closed_on_save(self) -> None:
        fixture = RepoFixture()
        try:
            store = StateStore(fixture.root / ".ourd-agent")
            kernel = SuperReasoningKernel()
            reasoning_problem = problem(kernel)
            state = RuntimeState(reasoning_problem=reasoning_problem)
            state.set_reasoning_hypothesis_state(
                kernel.build_hypothesis_state(
                    hypotheses(),
                    problem_id=reasoning_problem.problem_id,
                    max_hypotheses=4,
                    mutually_exclusive=True,
                )
            )
            state.reasoning_hypothesis_pool={}
            with self.assertRaisesRegex(StateError, "hypothesis pool conflicts"):
                store.save(state)
            store.close()
        finally:
            fixture.close()

    def test_hypothesis_updates_round_trip_with_authoritative_state(self) -> None:
        fixture = RepoFixture()
        try:
            state_dir = fixture.root / ".ourd-agent"
            kernel = SuperReasoningKernel()
            reasoning_problem = problem(kernel, evidence_ids=())
            hypothesis = hypotheses()[0]
            state = RuntimeState(
                reasoning_problem=reasoning_problem,
                reasoning_hypothesis_pool={hypothesis.hypothesis_id: hypothesis},
            )
            record_collision(
                state,
                action_id="action",
                expected="success",
                observed="failure",
                objects=["h1"],
                boundary="reasoning",
                active_dimension="hypothesis",
                frozen_dimensions=[],
                evidence_ids=["conflict"],
                severity_bp=6_000,
            )
            store = StateStore(state_dir)
            store.save(state)
            store.close()
            reopened = StateStore(state_dir)
            try:
                loaded = reopened.load()
                self.assertEqual(
                    state.reasoning_hypothesis_state.signature,
                    loaded.reasoning_hypothesis_state.signature,
                )
                self.assertEqual(
                    state.reasoning_hypothesis_updates[0].signature,
                    loaded.reasoning_hypothesis_updates[0].signature,
                )
                self.assertEqual(
                    loaded.reasoning_hypothesis_state.hypotheses[0],
                    loaded.reasoning_hypothesis_pool["h1"],
                )
            finally:
                reopened.close()
        finally:
            fixture.close()

    def test_multi_response_provider_preserves_order(self) -> None:
        class SequentialProvider:
            def __init__(self):
                self.config = ProviderConfig(model="sequential", max_reasoning_samples=2)
                self.values = ["first", "second"]

            def create_responses(self, *, requests, max_responses):
                if len(requests) > max_responses:
                    raise ProviderError("provider cap exceeded")
                return [self.values[index] for index, _ in enumerate(requests)]

        provider = SequentialProvider()
        responses = provider.create_responses(
            requests=[
                {"instructions": "a", "input_items": [], "tools": []},
                {"instructions": "b", "input_items": [], "tools": []},
            ],
            max_responses=2,
        )
        self.assertEqual(["first", "second"], responses)

    def test_multi_response_provider_returns_one_error_per_request(self) -> None:
        class SequentialProvider:
            def __init__(self):
                self.config = ProviderConfig(model="sequential", max_reasoning_samples=2)

            def create_response(self, **request):
                if request["instructions"] == "a":
                    raise ProviderError("first failed")
                return "second"

            def create_responses(self, *, requests, max_responses):
                if len(requests) > max_responses:
                    raise ProviderError("provider cap exceeded")
                responses = []
                for request in requests:
                    try:
                        responses.append(self.create_response(**request))
                    except ProviderError as exc:
                        responses.append({"type": "reasoning_error", "error": str(exc)})
                return responses

        provider = SequentialProvider()
        responses = provider.create_responses(
            requests=[
                {"instructions": "a", "input_items": [], "tools": []},
                {"instructions": "b", "input_items": [], "tools": []},
            ],
            max_responses=2,
        )
        self.assertEqual("reasoning_error", responses[0]["type"])
        self.assertEqual("second", responses[1])

    def test_agent_persists_reasoning_certificate_and_binds_eon(self) -> None:
        fixture = RepoFixture()
        try:
            provider = FakeReasoningProvider()
            with OURDAgent(fixture.root, provider=provider) as agent:
                agent.establish_governance(
                    goal="Select a bounded read action",
                    constraints=[],
                    assumptions=[],
                    uncertainties=[],
                    objects=["README"],
                    relations=[],
                    boundaries=["README.md"],
                    excluded_scope=[],
                    allowed_paths=["README.md"],
                    dimensions=["evidence quality"],
                    invariants=["workspace remains unchanged"],
                )
                result = agent.run_super_reasoning(
                    statement="Should README.md be inspected?",
                    goal="Choose a bounded read",
                    hypotheses=[
                        {
                            "hypothesis_id": "h1",
                            "proposition": "A bounded read is appropriate.",
                            "prior_bp": 10_000,
                            "posterior_bp": 10_000,
                            "falsifiers": ["critical counterexample"],
                        }
                    ],
                    uncertainty_bp=0,
                    difficulty_bp=0,
                    mutually_exclusive_hypotheses=True,
                )
                self.assertTrue(result["ok"])
                action = agent.propose_eon_action(
                    summary="Inspect README",
                    operation="read",
                    targets=["README.md"],
                    preconditions=[],
                    postconditions=[],
                    preserve=["workspace bytes"],
                    evidence=[],
                    risk="L0",
                    transaction_id="",
                    command_capabilities=[],
                    commands=[],
                    required_tests=[],
                    varied_dimensions=["evidence quality"],
                    expires_at="",
                    use_limit=1,
                )["eon_action"]
                self.assertEqual(
                    agent.state.last_reasoning_certificate.signature,
                    action["reasoning_certificate_signature"],
                )
                self.assertEqual(
                    agent.state.last_reasoning_certificate.winning_candidate_id,
                    action["reasoning_winning_path_id"],
                )
            reopened = OURDAgent(fixture.root, provider=FakeReasoningProvider())
            try:
                self.assertIsNotNone(reopened.state.last_reasoning_certificate)
            finally:
                reopened.close()
        finally:
            fixture.close()

    def test_sr_bound_eon_action_requires_current_accepted_certificate(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=FakeReasoningProvider()) as agent:
                agent.establish_governance(
                    goal="Bound read",
                    constraints=[], assumptions=[], uncertainties=[], objects=["README"],
                    relations=[], boundaries=[], excluded_scope=[], allowed_paths=["README.md"],
                    dimensions=["evidence quality"], invariants=[],
                )
                agent.run_super_reasoning(
                    statement="Read?",
                    goal="Choose read",
                    hypotheses=[{"hypothesis_id": "h1", "proposition": "Read", "prior_bp": 10_000, "posterior_bp": 10_000}],
                    mutually_exclusive_hypotheses=True,
                )
                agent.state.last_reasoning_certificate = replace(
                    agent.state.last_reasoning_certificate,
                    decision="REVISE",
                )
                with self.assertRaises(PolicyError):
                    agent.propose_eon_action(
                        summary="Inspect README", operation="read", targets=["README.md"],
                        preconditions=[], postconditions=[], preserve=[], evidence=[], risk="L0",
                        transaction_id="", command_capabilities=[], commands=[], required_tests=[],
                        varied_dimensions=["evidence quality"], expires_at="", use_limit=1,
                    )
        finally:
            fixture.close()

    def test_tampered_reasoning_certificate_cannot_bind_eon(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=FakeReasoningProvider()) as agent:
                agent.establish_governance(
                    goal="Bound read", constraints=[], assumptions=[], uncertainties=[],
                    objects=["README"], relations=[], boundaries=[], excluded_scope=[],
                    allowed_paths=["README.md"], dimensions=["evidence quality"], invariants=[],
                )
                agent.run_super_reasoning(
                    statement="Read?", goal="Choose read",
                    hypotheses=[{"hypothesis_id": "h1", "proposition": "Read", "prior_bp": 10_000, "posterior_bp": 10_000}],
                    mutually_exclusive_hypotheses=True,
                )
                agent.state.last_reasoning_certificate = replace(
                    agent.state.last_reasoning_certificate,
                    derived_confidence_bp=9_999,
                )
                with self.assertRaisesRegex(PolicyError, "signature mismatch"):
                    agent.propose_eon_action(
                        summary="Inspect README", operation="read", targets=["README.md"],
                        preconditions=[], postconditions=[], preserve=[], evidence=[], risk="L0",
                        transaction_id="", command_capabilities=[], commands=[], required_tests=[],
                        varied_dimensions=["evidence quality"], expires_at="", use_limit=1,
                    )
        finally:
            fixture.close()

    def test_malformed_reasoning_response_records_collision(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=MalformedReasoningProvider()) as agent:
                agent.establish_governance(
                    goal="Bound read", constraints=[], assumptions=[], uncertainties=[],
                    objects=["README"], relations=[], boundaries=[], excluded_scope=[],
                    allowed_paths=["README.md"], dimensions=["evidence quality"], invariants=[],
                )
                with self.assertRaises(ProviderError):
                    agent.run_super_reasoning(
                        statement="Read?", goal="Choose read",
                        hypotheses=[{"hypothesis_id": "h1", "proposition": "Read", "prior_bp": 10_000, "posterior_bp": 10_000}],
                        mutually_exclusive_hypotheses=True,
                    )
                self.assertEqual("super reasoning provider", agent.state.collisions[-1].boundary)
                self.assertIsNotNone(agent.state.reasoning_problem)
                self.assertIsNone(agent.state.last_reasoning_certificate)
        finally:
            fixture.close()

    def test_dispatch_contains_reasoning_provider_failure_as_tool_result(self) -> None:
        fixture = RepoFixture()
        try:
            with OURDAgent(fixture.root, provider=MalformedReasoningProvider()) as agent:
                agent.establish_governance(
                    goal="Bound read", constraints=[], assumptions=[], uncertainties=[],
                    objects=["README"], relations=[], boundaries=[], excluded_scope=[],
                    allowed_paths=["README.md"], dimensions=["evidence quality"], invariants=[],
                )
                result = agent.dispatch(
                    "run_super_reasoning",
                    {
                        "statement": "Read?",
                        "goal": "Choose read",
                        "hypotheses": [
                            {
                                "hypothesis_id": "h1",
                                "proposition": "Read",
                                "prior_bp": 10_000,
                                "posterior_bp": 10_000,
                            }
                        ],
                        "evidence_ids": [],
                        "uncertainty_bp": 0,
                        "difficulty_bp": 0,
                        "mutually_exclusive_hypotheses": True,
                    },
                )
            self.assertFalse(result["ok"])
            self.assertEqual("PROVIDER_FAILURE", result["error_code"])
            self.assertEqual("TRANSIENT", result["failure_class"])
            self.assertTrue(result["recoverable"])
            self.assertIn("ProviderError", result["error"])
        finally:
            fixture.close()

    def test_cfel_collision_updates_hypothesis_without_deleting_evidence(self) -> None:
        kernel = SuperReasoningKernel()
        reasoning_problem = problem(kernel, evidence_ids=())
        hypothesis = hypotheses()[0]
        state = RuntimeState(
            reasoning_problem=reasoning_problem,
            reasoning_hypothesis_pool={hypothesis.hypothesis_id: hypothesis},
            last_reasoning_certificate=ReasoningCertificate(
                problem_hash=reasoning_problem.signature,
                reasoning_topology_hash="topology",
                decision="ACCEPT",
            ),
        )
        record_collision(
            state,
            action_id="action",
            expected="success",
            observed="failure",
            objects=["h1"],
            boundary="reasoning",
            active_dimension="hypothesis",
            frozen_dimensions=[],
            evidence_ids=["conflict"],
            severity_bp=6_000,
        )
        revised = state.reasoning_hypothesis_pool["h1"]
        self.assertEqual(("e1",), revised.supporting_evidence)
        self.assertEqual(("conflict",), revised.conflicting_evidence)
        self.assertEqual("WEAKENED", revised.status)
        self.assertIsNotNone(state.reasoning_hypothesis_state)
        self.assertEqual(1, len(state.reasoning_hypothesis_updates))
        self.assertIsNone(state.last_reasoning_certificate)

    def test_cfel_matching_falsifier_marks_hypothesis_falsified(self) -> None:
        kernel = SuperReasoningKernel()
        reasoning_problem = problem(kernel, evidence_ids=())
        hypothesis = hypotheses()[0]
        state = RuntimeState(
            reasoning_problem=reasoning_problem,
            reasoning_hypothesis_pool={hypothesis.hypothesis_id: hypothesis},
        )
        record_collision(
            state,
            action_id="action",
            expected="hypothesis survives",
            observed="critical counterexample",
            objects=[],
            boundary="reasoning",
            active_dimension="falsification",
            frozen_dimensions=[],
            evidence_ids=["counterexample"],
            falsifier="critical counterexample",
            severity_bp=8_000,
        )
        self.assertEqual("FALSIFIED", state.reasoning_hypothesis_pool["h1"].status)
        self.assertEqual(
            0,
            state.reasoning_hypothesis_state.hypotheses[0].posterior_bp,
        )

    def test_cfel_collision_and_update_identity_replay_deterministically(self) -> None:
        kernel = SuperReasoningKernel()
        reasoning_problem = problem(kernel, evidence_ids=())
        hypothesis = hypotheses()[0]
        states = [
            RuntimeState(
                reasoning_problem=reasoning_problem,
                reasoning_hypothesis_pool={hypothesis.hypothesis_id: hypothesis},
            )
            for _ in range(2)
        ]
        records = []
        for state in states:
            records.append(
                record_collision(
                    state,
                    action_id="action",
                    expected="success",
                    observed="failure",
                    objects=["h1"],
                    boundary="reasoning",
                    active_dimension="hypothesis",
                    frozen_dimensions=[],
                    evidence_ids=["conflict"],
                    severity_bp=6_000,
                )
            )
        self.assertEqual(records[0].collision_id, records[1].collision_id)
        self.assertEqual(
            states[0].reasoning_hypothesis_updates[0].signature,
            states[1].reasoning_hypothesis_updates[0].signature,
        )
        self.assertEqual(
            states[0].reasoning_hypothesis_state.signature,
            states[1].reasoning_hypothesis_state.signature,
        )


if __name__ == "__main__":
    unittest.main()
