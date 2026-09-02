from __future__ import annotations

from typing import Sequence

from .models import (
    ConceptAnnotation,
    FormalWritingPlan,
    FormalWritingRequest,
    ReasoningAnnotation,
    ReferenceSpan,
)
from .topology import build_argument_topology


def build_writing_plan(
    request: FormalWritingRequest,
    references: Sequence[ReferenceSpan],
    concepts: Sequence[ConceptAnnotation],
    reasoning: Sequence[ReasoningAnnotation],
) -> FormalWritingPlan:
    if request.profile == "scientific-essay":
        sections = ("Introduction", "Evidence and Methods", "Analysis", "Limitations", "Conclusion")
    elif request.profile == "argumentative-essay":
        sections = ("Introduction", "Supporting Case", "Counterarguments", "Rebuttal", "Conclusion")
    else:
        sections = ("Introduction", "Analysis", "Conclusion")
    topology, topology_signature = build_argument_topology(request.objective, reasoning)
    claims = tuple(
        dict.fromkeys(
            annotation.source_claim
            for annotation in reasoning
            if annotation.source_claim and annotation.component_role in {"claim", "evidence", "warrant", "counterclaim", "limitation"}
        )
    )
    allocations = tuple(
        (claim, tuple(reference.reference_span_id for reference in references))
        for claim in claims
    )
    gaps = []
    if not references:
        gaps.append("No source passage has been allocated to the plan.")
    if not claims:
        gaps.append("No source-grounded claim inventory could be derived.")
    if request.word_target and request.word_target < len(sections) * 80:
        gaps.append("Word target is too small for the requested structure.")
    return FormalWritingPlan(
        request_id=request.request_id,
        task_interpretation=request.objective,
        thesis_or_purpose=request.objective,
        section_structure=sections,
        claim_inventory=claims,
        source_allocations=allocations,
        concept_coverage=tuple(item.preferred_label for item in concepts),
        argument_topology_signature=topology_signature,
        counterargument_plan=tuple(
            item.source_claim for item in reasoning if item.component_role == "counterclaim"
        ),
        citation_style=request.citation_style,
        quotation_policy=request.quotation_policy,
        paraphrase_policy=request.paraphrase_policy,
        unresolved_evidence_gaps=tuple(gaps),
        planned_output_paths=request.output_paths,
        validation_requirements=(
            "exact source hashes remain current",
            "all quotations round-trip to source anchors",
            "all citations have locators when the source has stable pages",
            "unsupported claims remain explicit",
        ),
    )


__all__ = ["build_writing_plan"]
