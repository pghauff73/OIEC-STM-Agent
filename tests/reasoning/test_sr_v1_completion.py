from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

from ourd.errors import PolicyError, ProviderError
from ourd.models import RuntimeState
from ourd.reasoning import (
    CausalEdge,
    Intervention,
    ReasoningBudget,
    ReasoningPath,
    ReasoningStep,
    ScoreConfiguration,
    SuperReasoningKernel,
    assess_causal_claim,
    choose_reasoning_operation,
    dimensional_equivalence,
    finite_domain_check,
    numerical_residual_check,
    project_reasoning_context,
    symbolic_equivalence,
)
from ourd.reasoning.adapters import evaluate_decimal_expression
from ourd.reasoning.contradictions import (
    build_contradiction_records,
    resolve_contradiction,
    unresolved_critical_contradictions,
)
from ourd.reasoning.diversity import (
    DEFAULT_DIVERSITY_CONFIGURATION,
    bind_diversity_scores,
    is_structural_duplicate,
    path_structure_signature,
)
from ourd.reasoning.falsifier import falsifier_request
from ourd.reasoning.generator import (
    DEFAULT_PERSPECTIVES,
    PERSPECTIVE_CONTRACTS,
    BoundedReasoningProvider,
    REASONING_OBJECT_TOOL_NAME,
    parse_reasoning_path,
    perspective_contract,
    proposer_request,
    reasoning_batch_tool,
)
from ourd.reasoning.models import (
    FalsifierReport,
    ReasoningMetrics,
    SynthesisResult,
    VerifierReport,
    stable_hash,
)
from ourd.reasoning.scoring import DEFAULT_SCORE_CONFIGURATION, score_reasoning_path
from ourd.reasoning.synthesis import synthesize_verified_result, synthesizer_request
from ourd.reasoning.verifier import (
    normalize_process_checks,
    verifier_request,
    verify_reasoning_paths,
)
from ourd_gui.reasoning_projection import (
    reasoning_json,
    reasoning_markdown,
    reasoning_projection,
    write_reasoning_export,
)
from tests.test_reasoning import (
    FakeReasoningProvider,
    PROCESS_CHECKS,
    dimension_budget,
    hypotheses,
    problem,
    response,
)


def make_path(
    *,
    path_id: str,
    perspective: str = "direct",
    inference: str = "deductive",
    conclusion: str = "Bounded conclusion",
    hypothesis_ids: tuple[str, ...] = ("h1",),
    evidence_ids: tuple[str, ...] = ("e1",),
) -> ReasoningPath:
    step = ReasoningStep(
        step_id=f"{path_id}:step",
        claim=f"Claim for {path_id}",
        premises=("problem", *hypothesis_ids),
        evidence_ids=evidence_ids,
        inference=inference,
        confidence_bp=9_000,
        falsifier="A counterexample defeats the claim.",
    )
    return ReasoningPath(
        path_id=path_id,
        perspective=perspective,
        hypothesis_ids=hypothesis_ids,
        steps=(step,),
        conclusion=conclusion,
        estimated_cost_bp=500,
        goal_relevance_bp=9_000,
        structure_signature=stable_hash(
            {
                "perspective": perspective,
                "inference": inference,
                "conclusion": conclusion,
                "hypothesis_ids": hypothesis_ids,
                "evidence_ids": evidence_ids,
            }
        ),
    )


def accepted_verifier(path: ReasoningPath) -> VerifierReport:
    return VerifierReport(
        report_id=f"verifier:{path.path_id}",
        path_id=path.path_id,
        step_scores=((path.steps[0].step_id, 10_000),),
        premise_validity_bp=10_000,
        evidence_support_bp=10_000,
        inference_quality_bp=10_000,
        consistency_bp=10_000,
        completeness_bp=10_000,
        weakest_step_bp=10_000,
        score_bp=10_000,
        verdict="ACCEPT",
    )


def surviving_falsifier(path: ReasoningPath) -> FalsifierReport:
    return FalsifierReport(
        report_id=f"falsifier:{path.path_id}",
        path_id=path.path_id,
        searched_falsifiers=("counterexample",),
        survival_bp=9_000,
        severity_bp=1_000,
        verdict="SURVIVES",
    )


class SynthesisProvider:
    def __init__(self, payload: dict, *, reject_verifier: bool = False):
        self.payload = payload
        self.reject_verifier = reject_verifier

    def create_responses(self, *, requests, max_responses):
        values = []
        for request in requests:
            instructions = request["instructions"].casefold()
            supplied = json.loads(request["input_items"][0]["content"])
            if "synthesizer" in instructions:
                values.append(response(json.dumps(self.payload)))
            elif "process verifier" in instructions:
                checks = {
                    name: not self.reject_verifier for name in PROCESS_CHECKS
                }
                values.append(
                    response(
                        json.dumps(
                            {
                                "steps": [
                                    {
                                        "step_id": step["step_id"],
                                        "checks": checks,
                                        "failures": [],
                                    }
                                    for step in supplied["candidate"]["steps"]
                                ],
                                "contradictions": [],
                            }
                        )
                    )
                )
            else:
                raise AssertionError(instructions)
        return values


class ContradictionProvider(FakeReasoningProvider):
    def create_responses(self, *, requests, max_responses):
        values = super().create_responses(requests=requests, max_responses=max_responses)
        adjusted = []
        for request, value in zip(requests, values):
            if "process verifier" not in request["instructions"].casefold():
                adjusted.append(value)
                continue
            payload = json.loads(value.output_text)
            payload["contradictions"] = ["The selected conclusion conflicts with evidence."]
            adjusted.append(response(json.dumps(payload)))
        return adjusted


class UsageProvider:
    def __init__(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int | None = None,
        tool_calls: int = 0,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = (
            input_tokens + output_tokens if total_tokens is None else total_tokens
        )
        self.tool_calls = tool_calls

    def create_responses(self, *, requests, max_responses):
        return tuple(
            SimpleNamespace(
                output_text="{}",
                output=[SimpleNamespace(type="function_call") for _ in range(self.tool_calls)],
                usage=SimpleNamespace(
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    total_tokens=self.total_tokens,
                ),
            )
            for _request in requests
        )


class StructuralDiversityTests(unittest.TestCase):
    def test_individual_reasoning_roles_use_structured_object_tool(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=2)
        current_problem = problem(kernel)
        current_hypotheses = hypotheses()
        winner = make_path(path_id="p1")
        budget = ReasoningBudget(
            minimum_candidates=2,
            maximum_candidates=2,
            candidate_count=2,
            verifier_count=2,
            falsifier_count=1,
        )
        requests = (
            proposer_request(
                problem=current_problem,
                hypotheses=current_hypotheses,
                perspective="direct",
                budget=budget,
            ),
            verifier_request(
                problem=current_problem,
                path=winner,
                hypotheses=current_hypotheses,
            ),
            falsifier_request(problem=current_problem, path=winner),
            synthesizer_request(
                problem=current_problem,
                winner=winner,
                survivors=(winner,),
            ),
        )
        for request in requests:
            self.assertEqual(
                (REASONING_OBJECT_TOOL_NAME,),
                tuple(tool["name"] for tool in request["tools"]),
            )
        falsifier_required = requests[2]["tools"][0]["parameters"]["required"]
        self.assertEqual([], falsifier_required)

    def test_semantic_duplicates_are_collapsed(self) -> None:
        first = make_path(path_id="p1", conclusion="Evidence supports bounded action")
        second = make_path(path_id="p2", conclusion="bounded action supports evidence")
        self.assertTrue(is_structural_duplicate(second, (first,)))

    def test_prose_only_difference_is_not_diversity(self) -> None:
        first = make_path(path_id="p1", conclusion="Claim, evidence: bounded.")
        second = make_path(path_id="p2", conclusion="bounded evidence claim")
        bound = bind_diversity_scores((first, second))
        self.assertEqual((0, 0), tuple(item.diversity_bp for item in bound))

    def test_distinct_strategies_are_retained(self) -> None:
        direct = make_path(path_id="p1", perspective="direct", inference="deductive")
        causal = make_path(path_id="p2", perspective="causal", inference="causal")
        self.assertFalse(is_structural_duplicate(causal, (direct,)))

    def test_path_ids_are_content_addressed(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=1)
        reasoning_problem = problem(kernel)
        budget = ReasoningBudget(
            maximum_candidates=1,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
        )
        payload = {
            "conclusion": "Bounded conclusion",
            "hypothesis_ids": ["h1"],
            "steps": [
                {
                    "claim": "One claim",
                    "premises": ["problem", "h1"],
                    "evidence_ids": ["e1"],
                    "inference": "deductive",
                    "confidence_bp": 9000,
                    "assumptions": [],
                    "falsifier": "counterexample",
                }
            ],
        }
        first = parse_reasoning_path(
            payload=payload,
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            perspective="direct",
            budget=budget,
        )
        second = parse_reasoning_path(
            payload={**payload, "provider_confidence_bp": 10000},
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            perspective="direct",
            budget=budget,
        )
        self.assertEqual(first.path_id, second.path_id)
        self.assertEqual(first.structure_signature, path_structure_signature(first))

    def test_problem_aliases_canonicalize_to_one_premise(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=1)
        reasoning_problem = problem(kernel)
        budget = ReasoningBudget(
            minimum_candidates=1,
            maximum_candidates=1,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
        )
        path = parse_reasoning_path(
            payload={
                "conclusion": "Bounded conclusion",
                "hypothesis_ids": ["h1"],
                "steps": [
                    {
                        "claim": "One claim",
                        "premises": [reasoning_problem.problem_id, "problem.statement", "h1"],
                        "evidence_ids": ["e1"],
                        "inference": "deductive",
                        "confidence_bp": 9000,
                        "assumptions": [],
                        "falsifier": "counterexample",
                    }
                ],
            },
            problem=reasoning_problem,
            hypotheses=hypotheses(),
            perspective="direct",
            budget=budget,
        )
        self.assertEqual(("problem", "h1"), path.steps[0].premises)

    def test_model_facing_problem_context_excludes_control_hashes(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=2)
        current_problem = problem(kernel)
        budget = ReasoningBudget(
            minimum_candidates=2,
            maximum_candidates=2,
            candidate_count=2,
            verifier_count=2,
            falsifier_count=1,
        )
        request = proposer_request(
            problem=current_problem,
            hypotheses=hypotheses(),
            perspective="direct",
            budget=budget,
        )
        content = json.loads(request["input_items"][0]["content"])
        self.assertNotIn("source_snapshot_hash", content["problem"])
        self.assertNotIn("boundary_signature", content["problem"])
        self.assertNotIn("dimension_signature", content["problem"])
        self.assertEqual("problem", content["problem"]["premise_id"])

    def test_perspective_contracts_are_unique(self) -> None:
        contracts = tuple(perspective_contract(name) for name in DEFAULT_PERSPECTIVES)
        self.assertEqual(len(DEFAULT_PERSPECTIVES), len(PERSPECTIVE_CONTRACTS))
        self.assertEqual(
            len(contracts),
            len({stable_hash(contract) for contract in contracts}),
        )
        self.assertEqual(
            len(contracts),
            len({contract["contract_id"] for contract in contracts}),
        )

    def test_perspective_requests_have_distinct_contract_payloads(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        current_problem = problem(kernel)
        budget = ReasoningBudget(
            minimum_candidates=4,
            maximum_candidates=4,
            candidate_count=4,
            verifier_count=4,
            falsifier_count=2,
        )
        payloads = []
        for perspective in DEFAULT_PERSPECTIVES[:4]:
            request = proposer_request(
                problem=current_problem,
                hypotheses=hypotheses(),
                perspective=perspective,
                budget=budget,
            )
            payloads.append(json.loads(request["input_items"][0]["content"]))
        self.assertEqual(
            4,
            len({stable_hash(payload["perspective_contract"]) for payload in payloads}),
        )
        self.assertEqual(
            tuple(DEFAULT_PERSPECTIVES[:4]),
            tuple(payload["perspective"] for payload in payloads),
        )

    def test_perspective_contract_adds_no_authority_or_evidence_identity(self) -> None:
        forbidden_keys = {
            "authority_hash",
            "boundary_signature",
            "dimension_signature",
            "evidence_ids",
            "source_snapshot_hash",
        }
        for name in DEFAULT_PERSPECTIVES:
            contract = perspective_contract(name)
            self.assertTrue(forbidden_keys.isdisjoint(contract))

    def test_unknown_perspective_uses_bounded_independent_probe_contract(self) -> None:
        first = perspective_contract("independent_probe_09")
        second = perspective_contract("independent_probe_09")
        self.assertEqual(first, second)
        self.assertEqual("independent_probe", first["contract_type"])
        self.assertIn(first["primary_inference_mode"], {
            "constraint",
            "defeasible",
            "probabilistic",
            "deductive",
            "inductive",
            "abductive",
            "causal",
            "computational",
        })
        self.assertLessEqual(len(first["required_path_shape"]), 2)

    def test_verifier_contract_marks_problem_as_validated_premise(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=2)
        request = verifier_request(
            problem=problem(kernel),
            path=make_path(path_id="p1"),
            hypotheses=hypotheses(),
        )
        content = json.loads(request["input_items"][0]["content"])
        self.assertEqual("object", content["verification_contract"]["top_level_type"])
        self.assertTrue(content["verification_contract"]["problem_is_validated_premise"])
        self.assertFalse(content["verification_contract"]["control_metadata_is_evidence"])

    def test_diversity_configuration_is_hashed(self) -> None:
        self.assertEqual(
            DEFAULT_DIVERSITY_CONFIGURATION.signature,
            replace(DEFAULT_DIVERSITY_CONFIGURATION).signature,
        )


class VerificationFalsificationTests(unittest.TestCase):
    def test_batch_tool_leaves_entry_semantics_to_role_validator(self) -> None:
        parameters = reasoning_batch_tool("reports")["parameters"]
        self.assertEqual([], parameters["required"])
        self.assertEqual({}, parameters["properties"]["reports"]["items"])
        self.assertFalse(parameters["additionalProperties"])

    def test_malformed_verifier_batch_repairs_with_individual_object_requests(self) -> None:
        class SplitRepairProvider:
            reasoning_role_batch_size = 2

            def __init__(self) -> None:
                self.requests = []
                self.repairs = []

            def record_reasoning_repair(self, *, role, reason, item_ids):
                self.repairs.append((role, reason, tuple(item_ids)))

            def create_responses(self, *, requests, max_responses):
                self.requests.extend(requests)
                values = []
                for request in requests:
                    supplied = json.loads(request["input_items"][0]["content"])
                    if "candidates" in supplied:
                        candidate = supplied["candidates"][0]
                        values.append(
                            response(
                                json.dumps(
                                    {
                                        "reports": [
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
                                        ]
                                    }
                                )
                            )
                        )
                        continue
                    candidate = supplied["candidate"]
                    values.append(
                        response(
                            json.dumps(
                                {
                                    "steps": [
                                        {
                                            "step_id": step["step_id"],
                                            "checks": {name: True for name in PROCESS_CHECKS},
                                            "failures": [],
                                        }
                                        for step in candidate["steps"]
                                    ],
                                    "contradictions": [],
                                    "missing_assumptions": [],
                                }
                            )
                        )
                    )
                return values

        provider = SplitRepairProvider()
        reports = verify_reasoning_paths(
            provider=provider,
            problem=problem(SuperReasoningKernel(max_candidates=2)),
            paths=(make_path(path_id="p1"), make_path(path_id="p2")),
            hypotheses=hypotheses(),
            declared_evidence_ids=("e1",),
            budget=ReasoningBudget(
                minimum_candidates=2,
                maximum_candidates=2,
                candidate_count=2,
                verifier_count=2,
                falsifier_count=0,
                max_provider_calls=3,
                max_verifier_passes=2,
            ),
            role_batch_size=2,
        )
        self.assertEqual(("ACCEPT", "ACCEPT"), tuple(item.verdict for item in reports))
        self.assertEqual(3, len(provider.requests))
        supplied = tuple(
            json.loads(item["input_items"][0]["content"])
            for item in provider.requests
        )
        self.assertEqual(2, len(supplied[0]["candidates"]))
        self.assertEqual(("p1", "p2"), tuple(item["candidate"]["path_id"] for item in supplied[1:]))
        self.assertEqual(
            ("submit_oiec_reasoning_batch", "submit_oiec_reasoning_object", "submit_oiec_reasoning_object"),
            tuple(item["tools"][0]["name"] for item in provider.requests),
        )
        self.assertEqual(
            [("verifier_batch", "reasoning batch response count does not match the request", ("p1", "p2"))],
            provider.repairs,
        )

    def test_singleton_verifier_batch_repairs_with_individual_object_request(self) -> None:
        class SingletonRepairProvider:
            reasoning_role_batch_size = 2

            def __init__(self) -> None:
                self.requests = []

            def create_responses(self, *, requests, max_responses):
                self.requests.extend(requests)
                values = []
                for request in requests:
                    supplied = json.loads(request["input_items"][0]["content"])
                    if "candidates" in supplied:
                        values.append(response(json.dumps({"reports": []})))
                        continue
                    candidate = supplied["candidate"]
                    values.append(
                        response(
                            json.dumps(
                                {
                                    "steps": [
                                        {
                                            "step_id": step["step_id"],
                                            "checks": {name: True for name in PROCESS_CHECKS},
                                            "failures": [],
                                        }
                                        for step in candidate["steps"]
                                    ],
                                    "contradictions": [],
                                    "missing_assumptions": [],
                                }
                            )
                        )
                    )
                return values

        provider = SingletonRepairProvider()
        reports = verify_reasoning_paths(
            provider=provider,
            problem=problem(SuperReasoningKernel(max_candidates=1)),
            paths=(make_path(path_id="p1"),),
            hypotheses=hypotheses(),
            declared_evidence_ids=("e1",),
            budget=ReasoningBudget(
                minimum_candidates=1,
                maximum_candidates=1,
                candidate_count=1,
                verifier_count=1,
                falsifier_count=0,
                max_provider_calls=2,
                max_verifier_passes=2,
            ),
            role_batch_size=2,
        )
        self.assertEqual("ACCEPT", reports[0].verdict)
        self.assertEqual(2, len(provider.requests))
        self.assertEqual(
            ("submit_oiec_reasoning_batch", "submit_oiec_reasoning_object"),
            tuple(item["tools"][0]["name"] for item in provider.requests),
        )

    def test_malformed_verifier_batch_fails_closed_without_repair_pass(self) -> None:
        class InvalidBatchProvider:
            reasoning_role_batch_size = 2

            def create_responses(self, *, requests, max_responses):
                return [response(json.dumps({"reports": []})) for _request in requests]

        with self.assertRaisesRegex(ProviderError, "response count"):
            verify_reasoning_paths(
                provider=InvalidBatchProvider(),
                problem=problem(SuperReasoningKernel(max_candidates=2)),
                paths=(make_path(path_id="p1"), make_path(path_id="p2")),
                hypotheses=hypotheses(),
                declared_evidence_ids=("e1",),
                budget=ReasoningBudget(
                    minimum_candidates=2,
                    maximum_candidates=2,
                    candidate_count=2,
                    verifier_count=2,
                    falsifier_count=0,
                    max_provider_calls=1,
                    max_verifier_passes=1,
                ),
                role_batch_size=2,
            )

    def test_verifier_schema_repair_is_bounded_and_error_informed(self) -> None:
        class RepairProvider:
            def __init__(self) -> None:
                self.requests = []

            def create_responses(self, *, requests, max_responses):
                self.requests.extend(requests)
                values = []
                for request in requests:
                    if "schema repairer" not in request["instructions"]:
                        values.append(
                            response(
                                json.dumps(
                                    {
                                        "steps": [
                                            {
                                                "step_id": "p1:step",
                                                "checks": {
                                                    name: True
                                                    for name in PROCESS_CHECKS
                                                    if name != "alternative_considered"
                                                },
                                                "failures": [],
                                            }
                                        ],
                                        "contradictions": [],
                                        "missing_assumptions": [],
                                    }
                                )
                            )
                        )
                        continue
                    repair_input = json.loads(request["input_items"][0]["content"])
                    if "every process check" not in repair_input["validation_error"]:
                        raise AssertionError("repair request omitted deterministic validation error")
                    values.append(
                        response(
                            json.dumps(
                                {
                                    "steps": [
                                        {
                                            "step_id": "p1:step",
                                            "checks": {name: True for name in PROCESS_CHECKS},
                                            "failures": [],
                                        }
                                    ],
                                    "contradictions": [],
                                    "missing_assumptions": [],
                                }
                            )
                        )
                    )
                return values

        provider = RepairProvider()
        kernel = SuperReasoningKernel(max_candidates=1)
        reports = verify_reasoning_paths(
            provider=provider,
            problem=problem(kernel),
            paths=(make_path(path_id="p1"),),
            hypotheses=hypotheses(),
            declared_evidence_ids=("e1",),
            budget=ReasoningBudget(
                minimum_candidates=1,
                maximum_candidates=1,
                candidate_count=1,
                verifier_count=1,
                falsifier_count=0,
                max_verifier_passes=2,
            ),
        )
        self.assertEqual("ACCEPT", reports[0].verdict)
        self.assertEqual(2, len(provider.requests))
        self.assertNotEqual(
            provider.requests[0]["instructions"],
            provider.requests[1]["instructions"],
        )

    def test_verifier_schema_repair_respects_single_pass_budget(self) -> None:
        class InvalidProvider:
            def create_responses(self, *, requests, max_responses):
                return [
                    response(
                        json.dumps(
                            {
                                "steps": [
                                    {
                                        "step_id": "p1:step",
                                        "checks": {},
                                        "failures": [],
                                    }
                                ],
                                "contradictions": [],
                                "missing_assumptions": [],
                            }
                        )
                    )
                    for _ in requests
                ]

        kernel = SuperReasoningKernel(max_candidates=1)
        with self.assertRaises(ProviderError):
            verify_reasoning_paths(
                provider=InvalidProvider(),
                problem=problem(kernel),
                paths=(make_path(path_id="p1"),),
                hypotheses=hypotheses(),
                declared_evidence_ids=("e1",),
                budget=ReasoningBudget(
                    minimum_candidates=1,
                    maximum_candidates=1,
                    candidate_count=1,
                    verifier_count=1,
                    falsifier_count=0,
                    max_verifier_passes=1,
                ),
            )

    def test_verifier_normalizes_only_the_declared_compatibility_alias(self) -> None:
        checks = {name: True for name in PROCESS_CHECKS}
        checks["alternative_consideered"] = checks.pop("alternative_considered")
        normalized = normalize_process_checks(checks)
        self.assertEqual(set(PROCESS_CHECKS), set(normalized))
        self.assertTrue(normalized["alternative_considered"])

    def test_verifier_rejects_unknown_or_ambiguous_check_keys(self) -> None:
        unknown = {name: True for name in PROCESS_CHECKS}
        unknown["grounding_traceble"] = unknown.pop("grounding_traceable")
        with self.assertRaises(ProviderError):
            normalize_process_checks(unknown)

        ambiguous = {name: True for name in PROCESS_CHECKS}
        ambiguous["alternative_consideered"] = True
        with self.assertRaises(ProviderError):
            normalize_process_checks(ambiguous)

    def test_verifier_rejects_non_boolean_check_values(self) -> None:
        checks = {name: True for name in PROCESS_CHECKS}
        checks["premises_available"] = "true"
        with self.assertRaises(ProviderError):
            normalize_process_checks(checks)

    def test_falsifier_contract_preserves_epistemic_distinction(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=2)
        request = falsifier_request(
            problem=problem(kernel),
            path=make_path(path_id="p1", conclusion="The claim is not proven."),
        )
        content = json.loads(request["input_items"][0]["content"])
        contract = content["falsification_contract"]
        self.assertTrue(contract["not_proven_is_not_proven_false"])
        self.assertTrue(contract["defeat_must_be_present_in_task"])
        self.assertFalse(contract["future_reversal_is_current_counterexample"])
        self.assertFalse(contract["alternate_definition_is_current_defeat"])
        self.assertNotIn("source_snapshot_hash", content["problem"])

    def test_alternative_explanation_reduces_survival(self) -> None:
        from ourd.reasoning.falsifier import falsify_reasoning_path

        report = falsify_reasoning_path(
            path=make_path(path_id="p1"),
            payload={
                "searched_falsifiers": ["alternative"],
                "alternative_explanations": ["A second mechanism fits."],
                "survival_bp": 9000,
            },
        )
        self.assertEqual("REVISE", report.verdict)
        self.assertLessEqual(report.survival_bp, 6000)

    def test_ungrounded_unresolved_defeat_becomes_reversal_condition(self) -> None:
        from ourd.reasoning.falsifier import falsify_reasoning_path

        report = falsify_reasoning_path(
            path=make_path(path_id="p1"),
            payload={
                "searched_falsifiers": ["possible future confound"],
                "unresolved_defeat_conditions": ["A future confound may be discovered."],
                "evidence_reversal_conditions": [],
                "survival_bp": 9000,
            },
            declared_evidence_ids=("e1",),
        )
        self.assertEqual("SURVIVES", report.verdict)
        self.assertEqual((), report.unresolved_defeat_conditions)
        self.assertIn(
            "A future confound may be discovered.",
            report.evidence_reversal_conditions,
        )

    def test_grounded_unresolved_defeat_remains_auditable_uncertainty(self) -> None:
        from ourd.reasoning.falsifier import falsify_reasoning_path

        report = falsify_reasoning_path(
            path=make_path(path_id="p1"),
            payload={
                "unresolved_defeat_conditions": ["The supplied trace contains a conflict."],
                "unresolved_defeat_evidence_ids": ["e1"],
                "survival_bp": 9000,
            },
            declared_evidence_ids=("e1",),
        )
        self.assertEqual("SURVIVES", report.verdict)
        self.assertEqual(("e1",), report.unresolved_defeat_evidence_ids)
        self.assertEqual(1000, report.residual_uncertainty_bp)

    def test_unresolved_defeat_rejects_unknown_grounding_evidence(self) -> None:
        from ourd.reasoning.falsifier import falsify_reasoning_path

        with self.assertRaises(ProviderError):
            falsify_reasoning_path(
                path=make_path(path_id="p1"),
                payload={
                    "unresolved_defeat_conditions": ["Current conflict."],
                    "unresolved_defeat_evidence_ids": ["unknown"],
                    "survival_bp": 9000,
                },
                declared_evidence_ids=("e1",),
            )

    def test_boundary_counterexample_is_recorded(self) -> None:
        from ourd.reasoning.falsifier import falsify_reasoning_path

        report = falsify_reasoning_path(
            path=make_path(path_id="p1"),
            payload={"boundary_cases": ["zero length input"], "survival_bp": 9000},
        )
        self.assertEqual(("zero length input",), report.boundary_cases)

    def test_critical_counterexample_prevents_selection(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        active, _budget, candidates, _topology, certificate = kernel.run(
            provider=FakeReasoningProvider(critical_falsifier=True),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        self.assertNotEqual("SOLUTION", certificate.terminal_state)
        self.assertEqual("FALSIFIED", active[0].status)
        self.assertTrue(candidates.hypothesis_updates)


class RankingAndSynthesisTests(unittest.TestCase):
    def test_synthesizer_contract_requires_disjoint_step_sets(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=2)
        winner = make_path(path_id="p1")
        request = synthesizer_request(
            problem=problem(kernel),
            winner=winner,
            survivors=(winner,),
        )
        content = json.loads(request["input_items"][0]["content"])
        self.assertNotIn("source_snapshot_hash", content["problem"])
        self.assertIn("Accepted and rejected", request["instructions"])

    def test_score_config_is_versioned_and_hashed(self) -> None:
        config = ScoreConfiguration()
        self.assertEqual("oiec-sr-score-v1", config.config_id)
        self.assertEqual(DEFAULT_SCORE_CONFIGURATION.signature, config.signature)

    def test_diversity_contributes_only_for_structural_difference(self) -> None:
        first, second = bind_diversity_scores(
            (
                make_path(path_id="p1", inference="deductive"),
                make_path(path_id="p2", inference="causal"),
            )
        )
        report = accepted_verifier(first)
        falsifier = surviving_falsifier(first)
        with_diversity = score_reasoning_path(
            path=first,
            verifier=report,
            falsifier=falsifier,
            declared_evidence_ids=("e1",),
        )
        without_diversity = score_reasoning_path(
            path=replace(first, diversity_bp=0),
            verifier=report,
            falsifier=falsifier,
            declared_evidence_ids=("e1",),
        )
        self.assertGreater(with_diversity.total_score_bp, without_diversity.total_score_bp)
        self.assertGreater(second.diversity_bp, 0)

    def _synthesize(
        self,
        payload: dict,
        *,
        survivors: tuple[ReasoningPath, ...] | None = None,
        reject_verifier: bool = False,
    ) -> SynthesisResult:
        paths = survivors or (make_path(path_id="p1"),)
        return synthesize_verified_result(
            provider=SynthesisProvider(payload, reject_verifier=reject_verifier),
            problem=problem(SuperReasoningKernel(max_candidates=1)),
            hypotheses=hypotheses(),
            winner=paths[0],
            survivors=paths,
            verifier_reports=tuple(accepted_verifier(path) for path in paths),
            declared_evidence_ids=("e1",),
            budget=ReasoningBudget(
                maximum_candidates=1,
                candidate_count=1,
                verifier_count=1,
                falsifier_count=0,
                max_provider_calls=4,
            ),
        )

    def test_synthesis_cannot_invent_source_path(self) -> None:
        result = self._synthesize(
            {"conclusion": "Invented", "source_path_ids": ["p1", "bogus"]}
        )
        self.assertTrue(result.fallback_used)

    def test_synthesis_cannot_accept_and_reject_same_step(self) -> None:
        result = self._synthesize(
            {
                "conclusion": "Merged",
                "source_path_ids": ["p1"],
                "accepted_step_ids": ["p1:step"],
                "rejected_step_ids": ["p1:step"],
            }
        )
        self.assertTrue(result.fallback_used)
        self.assertIn("both accept and reject", result.failure_reasons[0])

    def test_incompatible_components_are_not_merged(self) -> None:
        left = make_path(path_id="p1", hypothesis_ids=("h1",), conclusion="Left")
        right = make_path(path_id="p2", hypothesis_ids=("h2",), conclusion="Right")
        result = self._synthesize(
            {"conclusion": "Merged", "source_path_ids": ["p1", "p2"]},
            survivors=(left, right),
        )
        self.assertTrue(result.fallback_used)

    def test_unverified_synthesis_cannot_win(self) -> None:
        result = self._synthesize(
            {"conclusion": "Merged", "source_path_ids": ["p1"]},
            reject_verifier=True,
        )
        self.assertTrue(result.fallback_used)
        self.assertEqual("p1", result.synthesized_path_id)

    def test_failed_synthesis_falls_back_to_verified_winner(self) -> None:
        result = self._synthesize({"conclusion": "", "source_path_ids": []})
        self.assertTrue(result.verified)
        self.assertTrue(result.fallback_used)
        self.assertEqual("p1", result.winning_path_id)


class AdaptiveContextAndBudgetTests(unittest.TestCase):
    def test_model_cannot_raise_compute_budget(self) -> None:
        budget = SuperReasoningKernel(max_candidates=2).derive_budget(
            dimension_budget=dimension_budget(candidates=16),
            problem=problem(SuperReasoningKernel(max_candidates=2), uncertainty_bp=10000),
            provider_sample_cap=64,
        )
        self.assertLessEqual(budget.candidate_count, 2)

    def test_provider_call_budget_is_cumulative(self) -> None:
        provider = BoundedReasoningProvider(UsageProvider(), 1, 100, 1)
        provider.create_responses(requests=({},), max_responses=1)
        with self.assertRaises(PolicyError):
            provider.create_responses(requests=({},), max_responses=1)

    def test_token_and_tool_budgets_are_enforced(self) -> None:
        with self.assertRaises(PolicyError):
            BoundedReasoningProvider(
                UsageProvider(output_tokens=11), 1, 10, 1
            ).create_responses(
                requests=({},), max_responses=1
            )
        with self.assertRaises(PolicyError):
            BoundedReasoningProvider(UsageProvider(tool_calls=2), 1, 10, 1).create_responses(
                requests=({},), max_responses=1
            )

    def test_input_tokens_do_not_consume_generation_budget(self) -> None:
        provider = BoundedReasoningProvider(
            UsageProvider(input_tokens=20_000, output_tokens=10), 1, 10, 1
        )
        provider.create_responses(requests=({},), max_responses=1)
        self.assertEqual(10, provider.tokens_used)
        self.assertEqual(20_000, provider.input_tokens_observed)
        self.assertEqual(20_010, provider.total_tokens_observed)

    def test_context_projection_is_bounded(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        active, budget, candidates, topology, _certificate = kernel.run(
            provider=FakeReasoningProvider(),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        context = project_reasoning_context(
            problem=problem(kernel),
            hypotheses=active,
            topology=topology,
            candidates=candidates,
            budget=replace(budget, max_context_items=4),
        )
        self.assertLessEqual(len(context.candidate_summaries), 4)
        self.assertLessEqual(len(context.topology_node_ids), 4)

    def test_context_excludes_raw_conversation_history(self) -> None:
        context = project_reasoning_context(
            problem=problem(SuperReasoningKernel(max_candidates=1)),
            hypotheses=hypotheses(),
            budget=ReasoningBudget(
                maximum_candidates=1,
                candidate_count=1,
                verifier_count=1,
                falsifier_count=0,
            ),
        )
        self.assertNotIn("conversation", asdict(context))
        self.assertNotIn("history", asdict(context))

    def test_no_positive_voi_stops_reasoning(self) -> None:
        choice = choose_reasoning_operation(
            budget=ReasoningBudget(
                maximum_candidates=1,
                candidate_count=1,
                verifier_count=1,
                falsifier_count=0,
                minimum_voi_bp=100,
            ),
            expected_gains_bp={},
        )
        self.assertEqual("STOP", choice.operation)

    def test_voi_operation_cannot_bypass_iurm_or_eon(self) -> None:
        budget = ReasoningBudget(
            maximum_candidates=1,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
            operation_costs_bp=(("REFINE_DIMENSION", 0),),
        )
        choice = choose_reasoning_operation(
            budget=budget,
            expected_gains_bp={"REFINE_DIMENSION": 1000},
        )
        self.assertTrue(choice.requires_iurm)
        self.assertTrue(choice.read_only)

    def test_identical_state_selects_identical_next_operation(self) -> None:
        budget = ReasoningBudget(
            maximum_candidates=1,
            candidate_count=1,
            verifier_count=1,
            falsifier_count=0,
            operation_costs_bp=(("VERIFY_AGAIN", 100),),
        )
        first = choose_reasoning_operation(
            budget=budget,
            expected_gains_bp={"VERIFY_AGAIN": 1000},
        )
        second = choose_reasoning_operation(
            budget=budget,
            expected_gains_bp={"VERIFY_AGAIN": 1000},
        )
        self.assertEqual(first.signature, second.signature)


class CertificateContradictionAndExportTests(unittest.TestCase):
    def test_unresolved_critical_contradiction_blocks_solution(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        certificate = kernel.run(
            provider=ContradictionProvider(),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )[-1]
        self.assertNotEqual("SOLUTION", certificate.terminal_state)
        self.assertIn("critical_contradiction_unresolved", certificate.reasons)

    def test_contradiction_resolution_preserves_identity(self) -> None:
        path = make_path(path_id="p1")
        candidate = RuntimeState().reasoning_candidates
        del candidate
        from ourd.reasoning.models import CandidateSet

        candidates = CandidateSet(
            paths=(path,),
            verifier_reports=(
                replace(accepted_verifier(path), contradictions=("conflict",)),
            ),
            falsifier_reports=(surviving_falsifier(path),),
            metrics=(ReasoningMetrics(path_id=path.path_id),),
            selected_path_id=path.path_id,
        )
        record = build_contradiction_records(candidates)[0]
        resolved = resolve_contradiction(record, resolution_evidence_ids=("e2",))
        self.assertEqual(record.contradiction_id, resolved.contradiction_id)
        self.assertFalse(unresolved_critical_contradictions((resolved,)))

    def test_certificate_binds_hypothesis_and_score_config(self) -> None:
        kernel = SuperReasoningKernel(max_candidates=4)
        active, _budget, candidates, _topology, certificate = kernel.run(
            provider=FakeReasoningProvider(),
            problem=problem(kernel),
            hypotheses=hypotheses(),
            dimension_budget=dimension_budget(),
            declared_evidence_ids=("e1",),
        )
        self.assertEqual(
            kernel.hypothesis_collection_signature(active),
            certificate.hypothesis_signature,
        )
        self.assertEqual(candidates.score_config_hash, certificate.score_config_hash)

    def test_gui_reasoning_projection_is_read_only(self) -> None:
        state = RuntimeState()
        before = state.to_dict()
        payload = reasoning_projection(state)
        self.assertEqual(before, state.to_dict())
        self.assertFalse(payload["authoritative"])

    def test_exports_preserve_ids_hashes_and_limits(self) -> None:
        state = RuntimeState()
        payload = reasoning_projection(state)
        self.assertIn("limits", payload)
        self.assertIn('"authoritative": false', reasoning_json(payload))
        self.assertIn("non-authoritative", reasoning_markdown(payload))

    def test_exports_do_not_create_approval_or_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = reasoning_projection(RuntimeState())
            json_path = write_reasoning_export(root, payload, "json")
            markdown_path = write_reasoning_export(root, payload, "markdown")
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertFalse((root / ".ourd-agent" / "approvals.jsonl").exists())
            self.assertFalse((root / ".ourd-agent" / "evidence.jsonl").exists())


class MathematicalAndCausalAdapterTests(unittest.TestCase):
    def test_python_decimal_arithmetic_is_deterministic(self) -> None:
        first = evaluate_decimal_expression("(1 + 2) * 3")
        second = evaluate_decimal_expression("(1 + 2) * 3")
        self.assertEqual("9", first.result)
        self.assertEqual(first.signature, second.signature)

    def test_symbolic_equivalence_uses_adapter_result(self) -> None:
        result = symbolic_equivalence("(x + 1)^2", "x^2 + 2*x + 1")
        self.assertEqual("PASS", result.status)

    def test_numerical_residual_has_declared_tolerance(self) -> None:
        result = numerical_residual_check(
            "x * x",
            "x ** 2",
            points=({"x": -2}, {"x": 0}, {"x": 3}),
            tolerance="1e-20",
        )
        self.assertEqual("PASS", result.status)
        self.assertEqual("1E-20", result.tolerance)

    def test_dimensional_mismatch_rejects_equation(self) -> None:
        result = dimensional_equivalence(
            {"length": 1},
            {"time": 1},
            equation="distance = duration",
        )
        self.assertEqual("FAIL", result.status)

    def test_finite_domain_counterexample_is_recorded(self) -> None:
        result = finite_domain_check("x < 2", domains={"x": (0, 1, 2)})
        self.assertEqual("FAIL", result.status)
        self.assertEqual((("x", "2"),), result.counterexample)

    def test_correlation_does_not_imply_intervention(self) -> None:
        assessment = assess_causal_claim(
            claim="X changes Y",
            source_id="x",
            target_id="y",
            edges=(CausalEdge("e", "x", "y", "correlates", ("obs",), True),),
            intervention=Intervention("do-x", "x", "1"),
        )
        self.assertFalse(assessment.intervention_supported)
        self.assertLessEqual(assessment.confidence_bp, 3000)

    def test_confounder_blocks_high_confidence_causal_claim(self) -> None:
        assessment = assess_causal_claim(
            claim="X causes Y",
            source_id="x",
            target_id="y",
            edges=(CausalEdge("e", "x", "y", "causes", ("trial",), True),),
            intervention=Intervention("do-x", "x", "1"),
            declared_confounders=("z",),
        )
        self.assertLess(assessment.confidence_bp, 5000)
        self.assertFalse(assessment.intervention_supported)

    def test_adapter_failure_remains_explicit_uncertainty(self) -> None:
        result = evaluate_decimal_expression("unknown + 1")
        self.assertEqual("INCONCLUSIVE", result.status)
        self.assertIn("unknown variable", result.result)


if __name__ == "__main__":
    unittest.main()
