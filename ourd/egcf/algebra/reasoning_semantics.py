from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from .reasoning import CanonicalReasoningAlgorithm


REASONING_SEMANTIC_VERSION = "saa-reasoning-semantics-v1"
REASONING_STATE_KINDS = {"ATOMIC", "COMPOSITE"}
REASONING_GOVERNANCE_SUBSYSTEMS = (
    "EON",
    "OURD",
    "IURM",
    "CFEL",
    "BD_DL",
    "HYPOTHESIS_STATE",
    "ALGORITHM_STORE",
)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _texts(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


@dataclass(frozen=True)
class ReasoningStateDimension:
    dimension_id: str
    label: str
    meaning: str
    representation_kind: str = "ATOMIC"
    epistemic_status: str = "UNVERIFIED_CONCEPT"
    evidence_ids: Tuple[str, ...] = ()
    declared_independent: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "label": self.label,
            "meaning": self.meaning,
            "representation_kind": self.representation_kind,
            "epistemic_status": self.epistemic_status,
            "evidence_ids": list(self.evidence_ids),
            "declared_independent": self.declared_independent,
        }


@dataclass(frozen=True)
class ReasoningStateDependency:
    source_dimension_id: str
    target_dimension_id: str
    relation: str = "CONTRIBUTES_TO"
    evidence_ids: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dimension_id": self.source_dimension_id,
            "target_dimension_id": self.target_dimension_id,
            "relation": self.relation,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class ReasoningStateModel:
    dimensions: Tuple[ReasoningStateDimension, ...]
    dependencies: Tuple[ReasoningStateDependency, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [item.to_dict() for item in self.dimensions],
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


@dataclass(frozen=True)
class ReasoningSemanticIssue:
    issue_id: str
    issue_kind: str
    dimension_ids: Tuple[str, ...]
    label: str
    meanings: Tuple[str, ...]
    blocking: bool
    status: str
    questions: Tuple[str, ...]
    issue_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_kind": self.issue_kind,
            "dimension_ids": list(self.dimension_ids),
            "label": self.label,
            "meanings": list(self.meanings),
            "blocking": self.blocking,
            "status": self.status,
            "questions": list(self.questions),
            "issue_signature": self.issue_signature,
        }


@dataclass(frozen=True)
class ReasoningSemanticAssessment:
    schema_version: int
    semantic_version: str
    status: str
    issues: Tuple[ReasoningSemanticIssue, ...]
    state_signature: str
    canonical_reasoning_state_eligible: bool
    public_artifact_only: bool
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "semantic_version": self.semantic_version,
            "status": self.status,
            "issues": [item.to_dict() for item in self.issues],
            "state_signature": self.state_signature,
            "canonical_reasoning_state_eligible": self.canonical_reasoning_state_eligible,
            "public_artifact_only": self.public_artifact_only,
            "assessment_signature": self.assessment_signature,
        }


@dataclass(frozen=True)
class ReasoningSemanticDirective:
    issue_id: str
    subsystem: str
    action: str
    blocking: bool
    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "subsystem": self.subsystem,
            "action": self.action,
            "blocking": self.blocking,
            "payload": dict(self.payload),
        }


def _issue(
    *,
    issue_kind: str,
    dimension_ids: Sequence[str],
    label: str,
    meanings: Sequence[str],
    blocking: bool,
    questions: Sequence[str],
) -> ReasoningSemanticIssue:
    canonical_ids = tuple(sorted(str(value).strip() for value in dimension_ids))
    canonical_meanings = tuple(sorted({_text(value) for value in meanings if _text(value)}))
    canonical_label = _text(label)
    material = {
        "version": REASONING_SEMANTIC_VERSION,
        "issue_kind": issue_kind,
        "dimension_ids": canonical_ids,
        "label": canonical_label,
        "meanings": canonical_meanings,
        "blocking": blocking,
    }
    signature = sha256_json(material)
    return ReasoningSemanticIssue(
        issue_id=f"reasoning-semantic:{signature[:24]}",
        issue_kind=issue_kind,
        dimension_ids=canonical_ids,
        label=canonical_label,
        meanings=canonical_meanings,
        blocking=blocking,
        status="SEMANTIC_MISREPRESENTATION" if blocking else "SEMANTIC_REVIEW_REQUIRED",
        questions=tuple(str(value).strip() for value in questions if str(value).strip()),
        issue_signature=signature,
    )


def _validate_state(state: ReasoningStateModel) -> tuple[dict[str, ReasoningStateDimension], Tuple[ReasoningStateDependency, ...]]:
    if not isinstance(state, ReasoningStateModel):
        raise EGCFError("SAA-8.2 requires ReasoningStateModel")
    if not state.dimensions:
        raise EGCFError("SAA-8.2 reasoning state must contain at least one dimension")
    by_id: dict[str, ReasoningStateDimension] = {}
    for dimension in state.dimensions:
        identifier = str(dimension.dimension_id).strip()
        if not identifier or identifier in by_id:
            raise EGCFError("SAA-8.2 reasoning state dimension IDs must be unique")
        kind = str(dimension.representation_kind).strip().upper()
        if kind not in REASONING_STATE_KINDS:
            raise EGCFError(f"unsupported SAA-8.2 reasoning representation kind: {kind}")
        if not _text(dimension.label) or not _text(dimension.meaning):
            raise EGCFError("SAA-8.2 reasoning dimensions require explicit label and meaning")
        by_id[identifier] = dimension
    seen: set[tuple[str, str, str]] = set()
    dependencies: list[ReasoningStateDependency] = []
    for dependency in state.dependencies:
        source = str(dependency.source_dimension_id).strip()
        target = str(dependency.target_dimension_id).strip()
        relation = str(dependency.relation).strip().upper()
        if source not in by_id or target not in by_id:
            raise EGCFError("SAA-8.2 dependency references unknown reasoning dimension")
        if source == target:
            raise EGCFError("SAA-8.2 reasoning dimension cannot depend on itself directly")
        key = (source, target, relation)
        if key in seen:
            raise EGCFError("duplicate SAA-8.2 reasoning dependency")
        seen.add(key)
        dependencies.append(dependency)
    return by_id, tuple(dependencies)


def assess_reasoning_state_semantics(
    state: ReasoningStateModel,
    *,
    algorithm: CanonicalReasoningAlgorithm | None = None,
) -> ReasoningSemanticAssessment:
    by_id, dependencies = _validate_state(state)
    issues: list[ReasoningSemanticIssue] = []

    labels: dict[str, list[ReasoningStateDimension]] = {}
    for dimension in by_id.values():
        labels.setdefault(_text(dimension.label), []).append(dimension)
    for label, dimensions in labels.items():
        meanings = {_text(item.meaning) for item in dimensions}
        if len(meanings) > 1:
            issues.append(
                _issue(
                    issue_kind="SEMANTIC_LABEL_COLLISION",
                    dimension_ids=[item.dimension_id for item in dimensions],
                    label=label,
                    meanings=meanings,
                    blocking=True,
                    questions=(
                        f"Why is the label '{label}' being used for multiple distinct meanings?",
                        "Should these state dimensions be renamed or resolved to one evidence-backed concept?",
                    ),
                )
            )

    incoming: dict[str, list[ReasoningStateDependency]] = {identifier: [] for identifier in by_id}
    for dependency in dependencies:
        incoming[dependency.target_dimension_id].append(dependency)

    for identifier, dimension in by_id.items():
        parents = incoming[identifier]
        parent_meanings = tuple(_text(by_id[item.source_dimension_id].meaning) for item in parents)
        distinct_parent_meanings = tuple(sorted(set(parent_meanings)))
        kind = str(dimension.representation_kind).strip().upper()
        status = str(dimension.epistemic_status).strip().upper()
        evidence = _texts(dimension.evidence_ids)
        if kind == "ATOMIC" and len(distinct_parent_meanings) > 1:
            issues.append(
                _issue(
                    issue_kind="ATOMIC_DIMENSION_COUPLES_MULTIPLE_MEANINGS",
                    dimension_ids=(identifier, *(item.source_dimension_id for item in parents)),
                    label=dimension.label,
                    meanings=(dimension.meaning, *distinct_parent_meanings),
                    blocking=True,
                    questions=(
                        f"Does '{dimension.label}' really denote one independent quantity, or is it a mixture of {', '.join(distinct_parent_meanings)}?",
                        "Can the mixed state be decomposed into representative independent reasoning dimensions?",
                    ),
                )
            )
        if dimension.declared_independent and parents:
            issues.append(
                _issue(
                    issue_kind="DECLARED_INDEPENDENCE_CONTRADICTED_BY_DEPENDENCY",
                    dimension_ids=(identifier, *(item.source_dimension_id for item in parents)),
                    label=dimension.label,
                    meanings=(dimension.meaning, *distinct_parent_meanings),
                    blocking=True,
                    questions=(
                        f"Why is independently declared '{dimension.label}' derived from other reasoning-state dimensions?",
                        "Should the dimension be reclassified as derived/composite, or should the dependency be removed?",
                    ),
                )
            )
        if kind == "COMPOSITE" and parents and status != "SEMANTICALLY_RESOLVED":
            issues.append(
                _issue(
                    issue_kind="UNRESOLVED_COMPOSITE_REASONING_SEMANTICS",
                    dimension_ids=(identifier, *(item.source_dimension_id for item in parents)),
                    label=dimension.label,
                    meanings=(dimension.meaning, *distinct_parent_meanings),
                    blocking=True,
                    questions=(
                        f"What exact meaning does composite reasoning dimension '{dimension.label}' have?",
                        "What evidence and falsifier distinguish this composite from its component concepts?",
                    ),
                )
            )
        if status in {"FACT", "VERIFIED_FACT", "SEMANTICALLY_RESOLVED"} and not evidence:
            issues.append(
                _issue(
                    issue_kind="UNGROUNDED_REASONING_STATE",
                    dimension_ids=(identifier,),
                    label=dimension.label,
                    meanings=(dimension.meaning,),
                    blocking=True,
                    questions=(
                        f"What evidence grounds the asserted status of '{dimension.label}'?",
                        "Until evidence is attached, should this state be downgraded to an unverified concept or hypothesis?",
                    ),
                )
            )

    if algorithm is not None:
        if not isinstance(algorithm, CanonicalReasoningAlgorithm):
            raise EGCFError("SAA-8.2 algorithm context must be CanonicalReasoningAlgorithm")
        algorithm_semantics = set(algorithm.input_semantics) | set(algorithm.output_semantics)
        for node in algorithm.canonical_nodes:
            algorithm_semantics.update(str(value) for value in node.get("semantic_inputs", []))
            algorithm_semantics.update(str(value) for value in node.get("semantic_outputs", []))
        for dimension in by_id.values():
            if _text(dimension.meaning) not in algorithm_semantics:
                issues.append(
                    _issue(
                        issue_kind="UNBOUND_REASONING_STATE_MEANING",
                        dimension_ids=(dimension.dimension_id,),
                        label=dimension.label,
                        meanings=(dimension.meaning,),
                        blocking=False,
                        questions=(
                            f"Where does reasoning-state meaning '{dimension.meaning}' participate in the canonical reasoning algorithm?",
                        ),
                    )
                )

    dimensions_payload = sorted(
        (
            {
                "dimension_id": identifier,
                "label": _text(dimension.label),
                "meaning": _text(dimension.meaning),
                "representation_kind": str(dimension.representation_kind).strip().upper(),
                "epistemic_status": str(dimension.epistemic_status).strip().upper(),
                "evidence_ids": list(_texts(dimension.evidence_ids)),
                "declared_independent": bool(dimension.declared_independent),
            }
            for identifier, dimension in by_id.items()
        ),
        key=lambda item: item["dimension_id"],
    )
    dependencies_payload = sorted(
        (
            {
                "source": item.source_dimension_id,
                "target": item.target_dimension_id,
                "relation": str(item.relation).strip().upper(),
                "evidence_ids": list(_texts(item.evidence_ids)),
            }
            for item in dependencies
        ),
        key=lambda item: (item["source"], item["target"], item["relation"]),
    )
    state_signature = sha256_json(
        {
            "version": REASONING_SEMANTIC_VERSION,
            "dimensions": dimensions_payload,
            "dependencies": dependencies_payload,
        }
    )
    blocking = any(issue.blocking for issue in issues)
    status = "REASONING_STATE_SEMANTIC_MISREPRESENTATION" if blocking else (
        "REASONING_STATE_SEMANTIC_REVIEW" if issues else "REASONING_STATE_SEMANTICALLY_COHERENT"
    )
    material = {
        "version": REASONING_SEMANTIC_VERSION,
        "state_signature": state_signature,
        "algorithm_signature": algorithm.canonical_reasoning_signature if algorithm is not None else "",
        "issues": [item.issue_signature for item in issues],
        "status": status,
    }
    return ReasoningSemanticAssessment(
        schema_version=1,
        semantic_version=REASONING_SEMANTIC_VERSION,
        status=status,
        issues=tuple(issues),
        state_signature=state_signature,
        canonical_reasoning_state_eligible=not blocking,
        public_artifact_only=True,
        assessment_signature=sha256_json(material),
    )


def propagate_reasoning_semantic_issues(
    issues: Sequence[ReasoningSemanticIssue],
) -> Tuple[ReasoningSemanticDirective, ...]:
    actions = {
        "EON": "SURFACE_REASONING_SEMANTIC_ISSUE",
        "OURD": "CREATE_REASONING_SEMANTIC_RESOLUTION_OBJECTIVE",
        "IURM": "BLOCK_MISREPRESENTED_REASONING_DIMENSION",
        "CFEL": "REGISTER_REASONING_SEMANTIC_COLLISION",
        "BD_DL": "DETERMINE_REASONING_SEMANTIC_BOUNDARY",
        "HYPOTHESIS_STATE": "STORE_REASONING_MEANING_AS_UNVERIFIED",
        "ALGORITHM_STORE": "BLOCK_REASONING_CANONICAL_ADMISSION",
    }
    directives: list[ReasoningSemanticDirective] = []
    for issue in issues:
        payload = {
            "issue_kind": issue.issue_kind,
            "dimension_ids": list(issue.dimension_ids),
            "label": issue.label,
            "meanings": list(issue.meanings),
            "questions": list(issue.questions),
        }
        for subsystem in REASONING_GOVERNANCE_SUBSYSTEMS:
            directives.append(
                ReasoningSemanticDirective(
                    issue_id=issue.issue_id,
                    subsystem=subsystem,
                    action=actions[subsystem],
                    blocking=issue.blocking and subsystem in {"IURM", "ALGORITHM_STORE"},
                    payload=payload,
                )
            )
    return tuple(directives)
