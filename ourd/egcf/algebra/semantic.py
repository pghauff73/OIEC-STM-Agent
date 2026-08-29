from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .mimo import CanonicalMIMOCoupling
from .representative import (
    RepresentationAssessment,
    RepresentativeInputCandidate,
    RepresentativeInputSearch,
    assess_mimo_representation,
)


SEMANTIC_VERSION = "saa-semantic-representation-v1"
SEMANTIC_ISSUE_STATUSES = {
    "SEMANTIC_MISREPRESENTATION",
    "UNRESOLVED_SEMANTICS",
    "DECLARED_SEMANTICS",
    "CANDIDATE_REPRESENTATIVE_SEMANTICS",
    "EVIDENCE_SUPPORTED_SEMANTICS",
    "SEMANTICALLY_RESOLVED",
    "SEMANTICALLY_CONTRADICTED",
}
FALSIFIER_OUTCOMES = {"SURVIVED", "TRIGGERED", "UNTESTED"}
PROPAGATION_SUBSYSTEMS = (
    "EON",
    "OURD",
    "IURM",
    "CFEL",
    "BD_DL",
    "HYPOTHESIS_STATE",
    "ALGORITHM_STORE",
)


def _fraction_payload(value: Fraction) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _semantic_map(values: Mapping[int, str] | None) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw_index, raw_text in (values or {}).items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise EGCFError(f"invalid semantic position: {raw_index!r}") from exc
        if index < 0:
            raise EGCFError("semantic positions cannot be negative")
        text = _normalize_text(raw_text)
        if not text:
            raise EGCFError("semantic descriptions must be non-empty")
        result[index] = text
    return result


def _affected_outputs_from_mimo(
    mimo: CanonicalMIMOCoupling,
    input_index: int,
) -> Tuple[int, ...]:
    return tuple(
        output_index
        for output_index in range(mimo.output_count)
        if mimo.nonzero_pattern[output_index][input_index]
    )


def _affected_outputs_from_candidate(
    candidate: RepresentativeInputCandidate,
    input_index: int,
) -> Tuple[int, ...]:
    return tuple(
        output_index
        for output_index, row in enumerate(candidate.representative_channels)
        if not row[input_index].zero
    )


def _question_set(
    *,
    coordinate_label: str,
    affected_outputs: Sequence[int],
    declared_meaning: str | None,
    issue_kind: str,
) -> Tuple[str, ...]:
    outputs = ", ".join(f"y{index}" for index in affected_outputs) or "no observed outputs"
    questions = [
        f"What independent quantity does {coordinate_label} actually represent?",
        f"Why does {coordinate_label} affect {outputs}, and is that output footprint intended?",
        f"Which outputs should change when only the meaning of {coordinate_label} changes?",
        f"Which outputs must remain invariant if {coordinate_label} is semantically independent?",
        f"What observation would falsify the proposed meaning of {coordinate_label}?",
    ]
    if declared_meaning:
        questions.insert(
            1,
            f"Does the declared meaning '{declared_meaning}' fully explain the observed effects of {coordinate_label}?",
        )
    if issue_kind == "COUPLED_INPUT":
        questions.append(
            f"Is {coordinate_label} a mixture of multiple latent inputs that should be separated?"
        )
    elif issue_kind == "REDUNDANT_INPUT":
        questions.append(
            f"Is {coordinate_label} merely a duplicate or linear combination of other inputs?"
        )
    elif issue_kind == "REPRESENTATIVE_COORDINATE":
        questions.append(
            f"What domain concept names the newly discovered representative coordinate {coordinate_label}?"
        )
    return tuple(questions)


@dataclass(frozen=True)
class SemanticRepresentationIssue:
    issue_id: str
    issue_kind: str
    coordinate_kind: str
    coordinate_index: int
    coordinate_label: str
    source_input_indices: Tuple[int, ...]
    source_coefficients: Tuple[Fraction, ...]
    declared_meaning: str | None
    affected_output_indices: Tuple[int, ...]
    affected_output_meanings: Tuple[str, ...]
    status: str
    resolution_required: bool
    questions: Tuple[str, ...]
    source_representation_signature: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_kind": self.issue_kind,
            "coordinate_kind": self.coordinate_kind,
            "coordinate_index": self.coordinate_index,
            "coordinate_label": self.coordinate_label,
            "source_input_indices": list(self.source_input_indices),
            "source_coefficients": [_fraction_payload(value) for value in self.source_coefficients],
            "declared_meaning": self.declared_meaning,
            "affected_output_indices": list(self.affected_output_indices),
            "affected_output_meanings": list(self.affected_output_meanings),
            "status": self.status,
            "resolution_required": self.resolution_required,
            "questions": list(self.questions),
            "source_representation_signature": self.source_representation_signature,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class SemanticRepresentationAssessment:
    schema_version: int
    semantic_version: str
    mathematical_assessment: RepresentationAssessment
    semantic_status: str
    issues: Tuple[SemanticRepresentationIssue, ...]
    mathematical_admission_eligible: bool
    canonical_admission_eligible: bool
    assessment_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "semantic_version": self.semantic_version,
            "mathematical_assessment": self.mathematical_assessment.to_dict(),
            "semantic_status": self.semantic_status,
            "issues": [issue.to_dict() for issue in self.issues],
            "mathematical_admission_eligible": self.mathematical_admission_eligible,
            "canonical_admission_eligible": self.canonical_admission_eligible,
            "assessment_signature": self.assessment_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SemanticCandidateMeaning:
    candidate_id: str
    issue_id: str
    meaning: str
    expected_output_indices: Tuple[int, ...]
    excluded_output_indices: Tuple[int, ...]
    assumptions: Tuple[str, ...]
    falsifiers: Tuple[str, ...]
    epistemic_status: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "issue_id": self.issue_id,
            "meaning": self.meaning,
            "expected_output_indices": list(self.expected_output_indices),
            "excluded_output_indices": list(self.excluded_output_indices),
            "assumptions": list(self.assumptions),
            "falsifiers": list(self.falsifiers),
            "epistemic_status": self.epistemic_status,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class SemanticFalsifierResult:
    falsifier: str
    outcome: str
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        outcome = str(self.outcome).strip().upper()
        if outcome not in FALSIFIER_OUTCOMES:
            raise EGCFError(f"unsupported semantic falsifier outcome: {self.outcome!r}")
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "falsifier", _normalize_text(self.falsifier))
        if self.evidence_id is not None:
            object.__setattr__(self, "evidence_id", _normalize_text(self.evidence_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "falsifier": self.falsifier,
            "outcome": self.outcome,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class SemanticResolution:
    issue_id: str
    candidate_id: str
    status: str
    semantic_fit_bp: int
    evidence_ids: Tuple[str, ...]
    falsifier_results: Tuple[SemanticFalsifierResult, ...]
    independent_review: bool
    canonical_semantic_eligible: bool
    resolution_signature: str
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "semantic_fit_bp": self.semantic_fit_bp,
            "evidence_ids": list(self.evidence_ids),
            "falsifier_results": [item.to_dict() for item in self.falsifier_results],
            "independent_review": self.independent_review,
            "canonical_semantic_eligible": self.canonical_semantic_eligible,
            "resolution_signature": self.resolution_signature,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SemanticPropagationDirective:
    issue_id: str
    subsystem: str
    action: str
    blocking: bool
    question_required: bool
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "subsystem": self.subsystem,
            "action": self.action,
            "blocking": self.blocking,
            "question_required": self.question_required,
            "payload": dict(self.payload),
        }


def _make_issue(
    *,
    issue_kind: str,
    coordinate_kind: str,
    coordinate_index: int,
    coordinate_label: str,
    source_input_indices: Sequence[int],
    source_coefficients: Sequence[Fraction],
    declared_meaning: str | None,
    affected_output_indices: Sequence[int],
    output_semantics: Mapping[int, str],
    status: str,
    source_representation_signature: str,
) -> SemanticRepresentationIssue:
    if status not in SEMANTIC_ISSUE_STATUSES:
        raise EGCFError(f"unsupported semantic issue status: {status!r}")
    affected = tuple(sorted(set(int(value) for value in affected_output_indices)))
    output_meanings = tuple(output_semantics.get(index, f"y{index}") for index in affected)
    questions = _question_set(
        coordinate_label=coordinate_label,
        affected_outputs=affected,
        declared_meaning=declared_meaning,
        issue_kind=issue_kind,
    )
    material = {
        "schema_version": 1,
        "semantic_version": SEMANTIC_VERSION,
        "issue_kind": issue_kind,
        "coordinate_kind": coordinate_kind,
        "coordinate_index": int(coordinate_index),
        "source_input_indices": list(source_input_indices),
        "source_coefficients": [_fraction_payload(value) for value in source_coefficients],
        "declared_meaning": declared_meaning,
        "affected_output_indices": list(affected),
        "source_representation_signature": source_representation_signature,
    }
    signature = sha256_json(material)
    return SemanticRepresentationIssue(
        issue_id=f"semantic:{signature[:24]}",
        issue_kind=issue_kind,
        coordinate_kind=coordinate_kind,
        coordinate_index=int(coordinate_index),
        coordinate_label=coordinate_label,
        source_input_indices=tuple(int(value) for value in source_input_indices),
        source_coefficients=tuple(Fraction(value) for value in source_coefficients),
        declared_meaning=declared_meaning,
        affected_output_indices=affected,
        affected_output_meanings=output_meanings,
        status=status,
        resolution_required=status != "SEMANTICALLY_RESOLVED",
        questions=questions,
        source_representation_signature=source_representation_signature,
        signature=signature,
    )


def assess_mimo_semantics(
    mimo: CanonicalMIMOCoupling,
    *,
    mathematical_assessment: RepresentationAssessment | None = None,
    input_semantics: Mapping[int, str] | None = None,
    output_semantics: Mapping[int, str] | None = None,
) -> SemanticRepresentationAssessment:
    if not isinstance(mimo, CanonicalMIMOCoupling):
        raise EGCFError("SAA-5.3 semantic assessment requires CanonicalMIMOCoupling")
    math = mathematical_assessment or assess_mimo_representation(mimo)
    inputs = _semantic_map(input_semantics)
    outputs = _semantic_map(output_semantics)
    issues: list[SemanticRepresentationIssue] = []
    warnings: list[str] = []

    if math.status == "NON_REPRESENTATIVE_COUPLED":
        for input_index in range(mimo.input_count):
            affected = _affected_outputs_from_mimo(mimo, input_index)
            if len(affected) <= 1:
                continue
            issues.append(
                _make_issue(
                    issue_kind="COUPLED_INPUT",
                    coordinate_kind="SOURCE_INPUT",
                    coordinate_index=input_index,
                    coordinate_label=f"u{input_index}",
                    source_input_indices=(input_index,),
                    source_coefficients=(Fraction(1),),
                    declared_meaning=inputs.get(input_index),
                    affected_output_indices=affected,
                    output_semantics=outputs,
                    status="SEMANTIC_MISREPRESENTATION",
                    source_representation_signature=mimo.ordered_signature,
                )
            )
        if not issues:
            for input_index in range(mimo.input_count):
                issues.append(
                    _make_issue(
                        issue_kind="COUPLED_INPUT",
                        coordinate_kind="SOURCE_INPUT",
                        coordinate_index=input_index,
                        coordinate_label=f"u{input_index}",
                        source_input_indices=(input_index,),
                        source_coefficients=(Fraction(1),),
                        declared_meaning=inputs.get(input_index),
                        affected_output_indices=_affected_outputs_from_mimo(mimo, input_index),
                        output_semantics=outputs,
                        status="SEMANTIC_MISREPRESENTATION",
                        source_representation_signature=mimo.ordered_signature,
                    )
                )
    elif math.status == "NON_REPRESENTATIVE_REDUNDANT_INPUTS":
        nonpivots = math.minimality.nonpivot_input_positions if math.minimality else ()
        for input_index in nonpivots:
            issues.append(
                _make_issue(
                    issue_kind="REDUNDANT_INPUT",
                    coordinate_kind="SOURCE_INPUT",
                    coordinate_index=input_index,
                    coordinate_label=f"u{input_index}",
                    source_input_indices=(input_index,),
                    source_coefficients=(Fraction(1),),
                    declared_meaning=inputs.get(input_index),
                    affected_output_indices=_affected_outputs_from_mimo(mimo, input_index),
                    output_semantics=outputs,
                    status="SEMANTIC_MISREPRESENTATION",
                    source_representation_signature=mimo.ordered_signature,
                )
            )
    elif math.status == "REPRESENTATIVE_EXACT":
        for input_index in range(mimo.input_count):
            declared = inputs.get(input_index)
            issues.append(
                _make_issue(
                    issue_kind="SOURCE_INPUT_SEMANTICS",
                    coordinate_kind="SOURCE_INPUT",
                    coordinate_index=input_index,
                    coordinate_label=f"u{input_index}",
                    source_input_indices=(input_index,),
                    source_coefficients=(Fraction(1),),
                    declared_meaning=declared,
                    affected_output_indices=_affected_outputs_from_mimo(mimo, input_index),
                    output_semantics=outputs,
                    status="DECLARED_SEMANTICS" if declared else "UNRESOLVED_SEMANTICS",
                    source_representation_signature=mimo.ordered_signature,
                )
            )
    else:
        warnings.append(
            "semantic resolution cannot establish canonical admission while mathematical representation is unresolved"
        )

    if any(issue.status == "SEMANTIC_MISREPRESENTATION" for issue in issues):
        semantic_status = "SEMANTIC_MISREPRESENTATION"
    elif any(issue.status == "UNRESOLVED_SEMANTICS" for issue in issues):
        semantic_status = "UNRESOLVED_SEMANTICS"
    elif issues:
        semantic_status = "DECLARED_SEMANTICS"
    else:
        semantic_status = "UNRESOLVED_SEMANTICS"

    mathematical_eligible = bool(math.canonical_admission_eligible)
    canonical_eligible = False
    payload = {
        "schema_version": 1,
        "semantic_version": SEMANTIC_VERSION,
        "mathematical_assessment_signature": math.assessment_signature,
        "semantic_status": semantic_status,
        "issue_signatures": [issue.signature for issue in issues],
        "mathematical_admission_eligible": mathematical_eligible,
        "canonical_admission_eligible": canonical_eligible,
    }
    return SemanticRepresentationAssessment(
        schema_version=1,
        semantic_version=SEMANTIC_VERSION,
        mathematical_assessment=math,
        semantic_status=semantic_status,
        issues=tuple(issues),
        mathematical_admission_eligible=mathematical_eligible,
        canonical_admission_eligible=canonical_eligible,
        assessment_signature=sha256_json(payload),
        warnings=tuple(warnings),
    )


def assess_representative_candidate_semantics(
    mimo: CanonicalMIMOCoupling,
    search: RepresentativeInputSearch,
    *,
    input_semantics: Mapping[int, str] | None = None,
    output_semantics: Mapping[int, str] | None = None,
) -> Tuple[SemanticRepresentationIssue, ...]:
    if search.best_candidate is None:
        return ()
    candidate = search.best_candidate
    inputs = _semantic_map(input_semantics)
    outputs = _semantic_map(output_semantics)
    source_signature = mimo.ordered_signature
    issues: list[SemanticRepresentationIssue] = []
    for representative_index in range(candidate.representative_input_count):
        coefficients = tuple(
            candidate.source_to_representative_projection[representative_index][source_index]
            for source_index in range(candidate.source_input_count)
        )
        sources = tuple(index for index, value in enumerate(coefficients) if value != 0)
        nonzero_coefficients = tuple(coefficients[index] for index in sources)
        inherited = None
        if len(sources) == 1 and nonzero_coefficients == (Fraction(1),):
            inherited = inputs.get(sources[0])
        affected = _affected_outputs_from_candidate(candidate, representative_index)
        issues.append(
            _make_issue(
                issue_kind="REPRESENTATIVE_COORDINATE",
                coordinate_kind="REPRESENTATIVE_INPUT",
                coordinate_index=representative_index,
                coordinate_label=f"v{representative_index}",
                source_input_indices=sources,
                source_coefficients=nonzero_coefficients,
                declared_meaning=inherited,
                affected_output_indices=affected,
                output_semantics=outputs,
                status="DECLARED_SEMANTICS" if inherited else "UNRESOLVED_SEMANTICS",
                source_representation_signature=source_signature,
            )
        )
    return tuple(issues)


def make_semantic_candidate(
    issue: SemanticRepresentationIssue,
    *,
    meaning: str,
    expected_output_indices: Sequence[int],
    excluded_output_indices: Sequence[int] = (),
    assumptions: Sequence[str] = (),
    falsifiers: Sequence[str] = (),
) -> SemanticCandidateMeaning:
    meaning_text = _normalize_text(meaning)
    if not meaning_text:
        raise EGCFError("semantic candidate meaning must be non-empty")
    expected = tuple(sorted(set(int(value) for value in expected_output_indices)))
    excluded = tuple(sorted(set(int(value) for value in excluded_output_indices)))
    if any(value < 0 for value in expected + excluded):
        raise EGCFError("semantic output positions cannot be negative")
    if set(expected) & set(excluded):
        raise EGCFError("semantic expected and excluded outputs must be disjoint")
    normalized_assumptions = tuple(_normalize_text(value) for value in assumptions if _normalize_text(value))
    normalized_falsifiers = tuple(_normalize_text(value) for value in falsifiers if _normalize_text(value))
    material = {
        "schema_version": 1,
        "semantic_version": SEMANTIC_VERSION,
        "issue_id": issue.issue_id,
        "meaning": meaning_text,
        "expected_output_indices": list(expected),
        "excluded_output_indices": list(excluded),
        "assumptions": list(normalized_assumptions),
        "falsifiers": list(normalized_falsifiers),
    }
    signature = sha256_json(material)
    return SemanticCandidateMeaning(
        candidate_id=f"semantic-candidate:{signature[:24]}",
        issue_id=issue.issue_id,
        meaning=meaning_text,
        expected_output_indices=expected,
        excluded_output_indices=excluded,
        assumptions=normalized_assumptions,
        falsifiers=normalized_falsifiers,
        epistemic_status="MODEL_PROPOSED_SEMANTICS",
        signature=signature,
    )


def evaluate_semantic_candidate(
    issue: SemanticRepresentationIssue,
    candidate: SemanticCandidateMeaning,
    *,
    evidence_ids: Sequence[str] = (),
    falsifier_results: Sequence[SemanticFalsifierResult] = (),
    independent_review: bool = False,
) -> SemanticResolution:
    if candidate.issue_id != issue.issue_id:
        raise EGCFError("semantic candidate does not belong to issue")
    evidence = tuple(sorted({_normalize_text(value) for value in evidence_ids if _normalize_text(value)}))
    results = tuple(falsifier_results)
    affected = set(issue.affected_output_indices)
    expected = set(candidate.expected_output_indices)
    excluded = set(candidate.excluded_output_indices)
    expected_match = expected == affected
    excluded_clear = not (affected & excluded)
    semantic_fit_bp = 10000 if expected_match and excluded_clear else 0
    triggered = any(item.outcome == "TRIGGERED" for item in results)
    all_declared_falsifiers_tested = True
    if candidate.falsifiers:
        by_text = {item.falsifier: item for item in results}
        all_declared_falsifiers_tested = all(
            falsifier in by_text and by_text[falsifier].outcome == "SURVIVED"
            for falsifier in candidate.falsifiers
        )

    warnings: list[str] = []
    if triggered or semantic_fit_bp < 10000:
        status = "SEMANTICALLY_CONTRADICTED"
        eligible = False
    elif not evidence:
        status = "CANDIDATE_REPRESENTATIVE_SEMANTICS"
        eligible = False
        warnings.append("semantic meaning cannot be resolved without grounded evidence")
    elif not all_declared_falsifiers_tested:
        status = "EVIDENCE_SUPPORTED_SEMANTICS"
        eligible = False
        warnings.append("semantic falsifiers remain untested or unsatisfied")
    elif not independent_review:
        status = "EVIDENCE_SUPPORTED_SEMANTICS"
        eligible = False
        warnings.append("independent semantic review is required before canonical admission")
    else:
        status = "SEMANTICALLY_RESOLVED"
        eligible = True

    material = {
        "schema_version": 1,
        "semantic_version": SEMANTIC_VERSION,
        "issue_id": issue.issue_id,
        "candidate_signature": candidate.signature,
        "status": status,
        "semantic_fit_bp": semantic_fit_bp,
        "evidence_ids": list(evidence),
        "falsifier_results": [item.to_dict() for item in results],
        "independent_review": bool(independent_review),
    }
    return SemanticResolution(
        issue_id=issue.issue_id,
        candidate_id=candidate.candidate_id,
        status=status,
        semantic_fit_bp=semantic_fit_bp,
        evidence_ids=evidence,
        falsifier_results=results,
        independent_review=bool(independent_review),
        canonical_semantic_eligible=eligible,
        resolution_signature=sha256_json(material),
        warnings=tuple(warnings),
    )


def canonical_semantic_admission(
    *,
    mathematical_eligible: bool,
    issues: Sequence[SemanticRepresentationIssue],
    resolutions: Sequence[SemanticResolution],
) -> bool:
    if not mathematical_eligible:
        return False
    resolution_by_issue = {item.issue_id: item for item in resolutions}
    if len(resolution_by_issue) != len(resolutions):
        raise EGCFError("duplicate semantic resolutions for one issue are not allowed")
    return all(
        issue.issue_id in resolution_by_issue
        and resolution_by_issue[issue.issue_id].status == "SEMANTICALLY_RESOLVED"
        and resolution_by_issue[issue.issue_id].canonical_semantic_eligible
        for issue in issues
    )


def propagate_semantic_issues(
    issues: Sequence[SemanticRepresentationIssue],
) -> Tuple[SemanticPropagationDirective, ...]:
    directives: list[SemanticPropagationDirective] = []
    for issue in issues:
        common_payload = {
            "coordinate_kind": issue.coordinate_kind,
            "coordinate_index": issue.coordinate_index,
            "coordinate_label": issue.coordinate_label,
            "status": issue.status,
            "affected_output_indices": list(issue.affected_output_indices),
            "questions": list(issue.questions),
        }
        actions = {
            "EON": ("SURFACE_UNRESOLVED_SEMANTIC_REPRESENTATION", False),
            "OURD": ("CREATE_SEMANTIC_RESOLUTION_OBJECTIVE", False),
            "IURM": ("BLOCK_AS_INDEPENDENT_DIMENSION", True),
            "CFEL": ("REGISTER_SEMANTIC_COLLISION_ON_CONTRADICTORY_EFFECT", False),
            "BD_DL": ("DETERMINE_SEMANTIC_DOMAIN_AND_BOUNDS", False),
            "HYPOTHESIS_STATE": ("RECORD_CANDIDATE_MEANINGS_AS_UNVERIFIED", False),
            "ALGORITHM_STORE": ("BLOCK_CANONICAL_ADMISSION", True),
        }
        for subsystem in PROPAGATION_SUBSYSTEMS:
            action, blocking = actions[subsystem]
            directives.append(
                SemanticPropagationDirective(
                    issue_id=issue.issue_id,
                    subsystem=subsystem,
                    action=action,
                    blocking=blocking,
                    question_required=True,
                    payload=common_payload,
                )
            )
    return tuple(directives)


def semantic_followup_questions(
    issues: Sequence[SemanticRepresentationIssue],
) -> Tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for issue in issues:
        for question in issue.questions:
            if question not in seen:
                seen.add(question)
                ordered.append(question)
    return tuple(ordered)
