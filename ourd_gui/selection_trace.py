from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ourd.egcf.ids import sha256_json
from ourd.egcf.models import (
    AlgorithmDefinition,
    CommandDefinition,
    CommandInvocation,
    CompiledWorkflow,
    EvidenceArtifact,
    QualificationRecord,
    SelectionDecision,
)

from .read_models import ObjectDiagnostic, ReadOnlyEGCFRepository


@dataclass(frozen=True)
class SelectionCandidateView:
    algorithm_id: str
    algorithm_digest: str
    definition_id: str
    status: str
    selected: bool
    qualified: bool
    qualification_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    score_components: Mapping[str, float | int]
    rejection_reasons: tuple[str, ...]
    capability_level: str
    capability_requirements: tuple[str, ...]
    invariants: tuple[str, ...]
    rollback_class: str
    risk_floor: str
    known_failures: tuple[str, ...]
    implementation_kind: str
    implementation_digest: str
    implementation_ref: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    diagnostics: tuple[ObjectDiagnostic, ...] = ()


@dataclass(frozen=True)
class SelectionTrace:
    selection_id: str
    command_id: str
    command_definition_id: str
    intent_id: str
    invocation_id: str
    compiled_workflow_id: str
    context_hash: str
    required_capability_level: str
    required_capabilities: tuple[str, ...]
    candidates: tuple[SelectionCandidateView, ...]
    ranking: tuple[str, ...]
    selected_algorithm_id: str
    selected_algorithm_digest: str
    tie_break: str
    evidence_ids: tuple[str, ...]
    source_snapshot_hash: str
    diagnostics: tuple[ObjectDiagnostic, ...] = ()

    @property
    def digest(self) -> str:
        return sha256_json(asdict(self))


class SelectionTraceAssembler:
    def __init__(self, repository: ReadOnlyEGCFRepository) -> None:
        self.repository = repository

    def _algorithm_definition(
        self,
        algorithm_id: str,
        algorithm_digest: str,
    ) -> tuple[AlgorithmDefinition | None, list[ObjectDiagnostic]]:
        matches = [
            item
            for item in self.repository.find(
                "algorithm-definition",
                lambda record: isinstance(record, AlgorithmDefinition)
                and record.algorithm_id == algorithm_id
                and record.implementation_digest == algorithm_digest,
            )
            if isinstance(item, AlgorithmDefinition)
        ]
        if not matches:
            return None, [
                ObjectDiagnostic(
                    code="algorithm_missing",
                    message=f"No exact algorithm definition for {algorithm_id} digest {algorithm_digest}",
                    blocking=True,
                )
            ]
        matches.sort(key=lambda item: item.object_id)
        diagnostics: list[ObjectDiagnostic] = []
        if len(matches) > 1:
            diagnostics.append(
                ObjectDiagnostic(
                    code="algorithm_duplicate",
                    message=f"Multiple identical exact definitions found for {algorithm_id}",
                )
            )
        return matches[0], diagnostics

    def _qualification_evidence(
        self,
        qualification_ids: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[ObjectDiagnostic, ...], bool]:
        evidence_ids: list[str] = []
        diagnostics: list[ObjectDiagnostic] = []
        qualified = False
        for qualification_id in qualification_ids:
            try:
                record = self.repository.get(qualification_id)
            except (OSError, ValueError, KeyError) as exc:
                diagnostics.append(
                    ObjectDiagnostic(
                        code="qualification_missing",
                        message=str(exc),
                        object_id=qualification_id,
                        blocking=True,
                    )
                )
                continue
            if not isinstance(record, QualificationRecord):
                diagnostics.append(
                    ObjectDiagnostic(
                        code="qualification_type_mismatch",
                        message=f"{qualification_id} is not a qualification record",
                        object_id=qualification_id,
                        blocking=True,
                    )
                )
                continue
            qualified = qualified or record.status == "QUALIFIED"
            evidence_ids.extend(record.evidence_ids)
        return tuple(dict.fromkeys(evidence_ids)), tuple(diagnostics), qualified

    def _find_compiled_workflow(self, selection_id: str) -> CompiledWorkflow | None:
        matches = [
            item
            for item in self.repository.find(
                "compiled-workflow",
                lambda record: isinstance(record, CompiledWorkflow)
                and any(node.get("selection_id") == selection_id for node in record.nodes),
            )
            if isinstance(item, CompiledWorkflow)
        ]
        matches.sort(key=lambda item: (item.created_at, item.object_id))
        return matches[-1] if matches else None

    def _find_invocation(
        self,
        compiled: CompiledWorkflow | None,
        invocation_id: str,
    ) -> tuple[CommandInvocation | None, list[ObjectDiagnostic]]:
        diagnostics: list[ObjectDiagnostic] = []
        if invocation_id:
            try:
                record = self.repository.get(invocation_id)
            except (OSError, ValueError, KeyError) as exc:
                return None, [
                    ObjectDiagnostic(
                        code="invocation_missing",
                        message=str(exc),
                        object_id=invocation_id,
                        blocking=True,
                    )
                ]
            if not isinstance(record, CommandInvocation):
                return None, [
                    ObjectDiagnostic(
                        code="invocation_type_mismatch",
                        message=f"{invocation_id} is not a command invocation",
                        object_id=invocation_id,
                        blocking=True,
                    )
                ]
            return record, diagnostics
        if compiled is None:
            return None, diagnostics
        workflow_name = compiled.workflow_id.rsplit("@", 1)[0]
        prefix = "invocation-"
        if not workflow_name.startswith(prefix):
            return None, diagnostics
        digest_prefix = workflow_name[len(prefix) :]
        matches = [
            item
            for item in self.repository.list("command-invocation")
            if isinstance(item, CommandInvocation)
            and item.object_id.partition(":sha256:")[2].startswith(digest_prefix)
        ]
        if len(matches) == 1:
            return matches[0], diagnostics
        diagnostics.append(
            ObjectDiagnostic(
                code="invocation_unresolved",
                message=(
                    "Could not resolve an exact invocation from the compiled workflow; "
                    "provide the task-bound invocation ID"
                ),
                blocking=False,
            )
        )
        return None, diagnostics

    def assemble(
        self,
        selection_id: str,
        *,
        invocation_id: str = "",
        compiled_workflow_id: str = "",
    ) -> SelectionTrace:
        selection = self.repository.get(selection_id)
        if not isinstance(selection, SelectionDecision):
            raise TypeError(f"not a selection decision: {selection_id}")
        diagnostics: list[ObjectDiagnostic] = []
        compiled: CompiledWorkflow | None = None
        if compiled_workflow_id:
            candidate = self.repository.get(compiled_workflow_id)
            if not isinstance(candidate, CompiledWorkflow):
                raise TypeError(f"not a compiled workflow: {compiled_workflow_id}")
            compiled = candidate
        else:
            compiled = self._find_compiled_workflow(selection_id)
        if compiled is None:
            diagnostics.append(
                ObjectDiagnostic(
                    code="compiled_workflow_missing",
                    message="No compiled workflow references this selection decision",
                )
            )
        invocation, invocation_diagnostics = self._find_invocation(compiled, invocation_id)
        diagnostics.extend(invocation_diagnostics)
        command_definition_id = invocation.command_definition_id if invocation else ""
        if command_definition_id:
            try:
                command_definition = self.repository.get(command_definition_id)
                if not isinstance(command_definition, CommandDefinition):
                    diagnostics.append(
                        ObjectDiagnostic(
                            code="command_definition_type_mismatch",
                            message=f"{command_definition_id} is not a command definition",
                            object_id=command_definition_id,
                            blocking=True,
                        )
                    )
            except (OSError, ValueError, KeyError) as exc:
                diagnostics.append(
                    ObjectDiagnostic(
                        code="command_definition_missing",
                        message=str(exc),
                        object_id=command_definition_id,
                        blocking=True,
                    )
                )

        ordered_items: list[tuple[dict[str, Any], tuple[str, ...]]] = []
        for item in selection.candidates:
            ordered_items.append((dict(item), ()))
        for item in selection.excluded:
            reasons = tuple(str(reason) for reason in item.get("reasons", []))
            ordered_items.append((dict(item), reasons))

        candidate_views: list[SelectionCandidateView] = []
        all_evidence_ids = list(selection.evidence_ids)
        for item, rejection_reasons in ordered_items:
            algorithm_id = str(item.get("algorithm_id", ""))
            algorithm_digest = str(item.get("algorithm_digest", ""))
            definition, algorithm_diagnostics = self._algorithm_definition(
                algorithm_id,
                algorithm_digest,
            )
            qualification_ids = tuple(str(value) for value in item.get("qualification_ids", []))
            qualification_evidence, qualification_diagnostics, qualified = (
                self._qualification_evidence(qualification_ids)
            )
            all_evidence_ids.extend(qualification_evidence)
            if definition is None:
                candidate_views.append(
                    SelectionCandidateView(
                        algorithm_id=algorithm_id,
                        algorithm_digest=algorithm_digest,
                        definition_id="",
                        status=str(item.get("status", "MISSING")),
                        selected=algorithm_id == selection.selected_algorithm_id
                        and algorithm_digest == selection.selected_algorithm_digest,
                        qualified=qualified,
                        qualification_ids=qualification_ids,
                        evidence_ids=qualification_evidence,
                        score_components=dict(item.get("score_components", {})),
                        rejection_reasons=rejection_reasons,
                        capability_level="",
                        capability_requirements=(),
                        invariants=(),
                        rollback_class=str(item.get("rollback_class", "")),
                        risk_floor="",
                        known_failures=tuple(str(value) for value in item.get("known_failures", [])),
                        implementation_kind="",
                        implementation_digest=algorithm_digest,
                        implementation_ref="",
                        input_schema={},
                        output_schema={},
                        diagnostics=tuple([*algorithm_diagnostics, *qualification_diagnostics]),
                    )
                )
                continue
            candidate_views.append(
                SelectionCandidateView(
                    algorithm_id=algorithm_id,
                    algorithm_digest=algorithm_digest,
                    definition_id=definition.object_id,
                    status=str(item.get("status", definition.status)),
                    selected=algorithm_id == selection.selected_algorithm_id
                    and algorithm_digest == selection.selected_algorithm_digest,
                    qualified=qualified,
                    qualification_ids=qualification_ids,
                    evidence_ids=qualification_evidence,
                    score_components=dict(item.get("score_components", {})),
                    rejection_reasons=rejection_reasons,
                    capability_level=definition.capability_level,
                    capability_requirements=tuple(definition.capability_requirements),
                    invariants=tuple(definition.invariants),
                    rollback_class=definition.rollback_class,
                    risk_floor=definition.risk_floor,
                    known_failures=tuple(definition.known_failures),
                    implementation_kind=definition.implementation_kind,
                    implementation_digest=definition.implementation_digest,
                    implementation_ref=definition.implementation_ref,
                    input_schema=dict(definition.input_schema),
                    output_schema=dict(definition.output_schema),
                    diagnostics=tuple([*algorithm_diagnostics, *qualification_diagnostics]),
                )
            )

        selected_view = next((item for item in candidate_views if item.selected), None)
        required_level = selected_view.capability_level if selected_view else ""
        required_capabilities = selected_view.capability_requirements if selected_view else ()
        source_snapshot = compiled.source_snapshot_hash if compiled else ""
        current_source_snapshot = self.repository.source_snapshot()
        if source_snapshot and source_snapshot != current_source_snapshot:
            diagnostics.append(
                ObjectDiagnostic(
                    code="source_snapshot_stale",
                    message=(
                        f"Trace snapshot {source_snapshot} differs from current "
                        f"{current_source_snapshot}"
                    ),
                )
            )
        for evidence_id in tuple(dict.fromkeys(all_evidence_ids)):
            try:
                evidence = self.repository.get(evidence_id)
                if not isinstance(evidence, (EvidenceArtifact, QualificationRecord, SelectionDecision)):
                    diagnostics.append(
                        ObjectDiagnostic(
                            code="evidence_type_unexpected",
                            message=f"Referenced support object has type {evidence.object_type}",
                            object_id=evidence_id,
                        )
                    )
            except (OSError, ValueError, KeyError) as exc:
                diagnostics.append(
                    ObjectDiagnostic(
                        code="evidence_missing",
                        message=str(exc),
                        object_id=evidence_id,
                    )
                )
        return SelectionTrace(
            selection_id=selection.object_id,
            command_id=selection.command_id,
            command_definition_id=command_definition_id,
            intent_id=invocation.intent_id if invocation else "",
            invocation_id=invocation.object_id if invocation else "",
            compiled_workflow_id=compiled.object_id if compiled else "",
            context_hash=selection.context_hash,
            required_capability_level=required_level,
            required_capabilities=required_capabilities,
            candidates=tuple(candidate_views),
            ranking=tuple(selection.ranking),
            selected_algorithm_id=selection.selected_algorithm_id,
            selected_algorithm_digest=selection.selected_algorithm_digest,
            tie_break=selection.tie_break,
            evidence_ids=tuple(dict.fromkeys(all_evidence_ids)),
            source_snapshot_hash=source_snapshot,
            diagnostics=tuple(diagnostics),
        )
