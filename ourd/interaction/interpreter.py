from __future__ import annotations

import re
from typing import Iterable

from ..constants import SCORE_SCALE
from ..workspace import Workspace
from .context import resolve_context
from .formal_writing import interpret_formal_writing
from .models import InterpretedIntent, MUTATING_INTENT_MODES


AMBIGUITY_CONFIRMATION_BP = 5_000

MODE_PATTERNS = {
    "EXECUTE": (
        r"\bcommit\b",
        r"\bpush\b",
        r"\bmerge\b",
        r"\bapply\b",
        r"\bexecute\b",
        r"\brun the action\b",
    ),
    "RECOVER": (r"\brollback\b", r"\brecover\b", r"\brevert\b", r"\bundo\b"),
    "WRITE": (
        r"\bedit\b",
        r"\bmodify\b",
        r"\bchange\b",
        r"\bfix\b",
        r"\bcreate\b",
        r"\bwrite\b",
        r"\bimplement\b",
        r"\brename\b",
        r"\bdelete\b",
        r"\bremove\b",
        r"\bimprove\b",
        r"\bmake\b.+\bbetter\b",
    ),
    "TEST": (
        r"\btest\b",
        r"\bvalidate\b",
        r"\bverify\b",
        r"\bbuild\b",
        r"\blint\b",
        r"\bbenchmark\b",
    ),
    "EXPORT": (r"\bexport\b", r"\bsave (?:a )?report\b"),
    "PROPOSE": (r"\bpropose\b", r"\bdraft\b", r"\bcandidate\b"),
    "PLAN": (r"\bplan\b", r"\bstrategy\b", r"\broadmap\b", r"\bdesign\b"),
    "COMPARE": (r"\bcompare\b", r"\bcontrast\b", r"\bversus\b", r"\bvs\.?\b"),
    "SUMMARIZE": (
        r"\bsummari[sz](?:e|ed|ing)\b",
        r"\bsummary of\b",
        r"\bgive (?:me )?an overview of\b",
        r"\bdigest\b",
        r"\babstract each\b",
    ),
    "EXPLAIN": (r"\bexplain\b", r"\bdescribe\b", r"\bteach\b", r"\bwhat is\b"),
    "INSPECT": (r"\binspect\b", r"\bread\b", r"\blist\b", r"\bshow\b", r"\blook at\b"),
}

NON_EXECUTION_PATTERNS = (
    r"\bdo not execute\b",
    r"\bdon't execute\b",
    r"\bdo not run\b",
    r"\bread[- ]only\b",
    r"\bproposal only\b",
    r"\bwithout (?:editing|writing|executing|changing)\b",
)

VAGUE_PATTERNS = (
    r"\bsomething\b",
    r"\bsomehow\b",
    r"\bwhatever\b",
    r"\betc\.?\b",
    r"\bmaybe\b",
    r"\bthis\b",
    r"\bit\b",
)

MODE_OUTPUTS = {
    "INSPECT": ("inspection", "evidence"),
    "SUMMARIZE": ("summary", "evidence", "corpus_coverage"),
    "EXPLAIN": ("explanation",),
    "REASON": ("reasoned_answer", "reasoning_certificate"),
    "COMPARE": ("comparison", "reasoning_certificate"),
    "PLAN": ("plan", "reasoning_certificate"),
    "PROPOSE": ("candidate", "reasoning_certificate"),
    "WRITE": ("candidate", "diff", "evidence"),
    "TEST": ("test_results", "evidence"),
    "EXECUTE": ("execution_result", "evidence"),
    "RECOVER": ("recovery_result", "evidence"),
    "EXPORT": ("export",),
}


def _matching_modes(text: str) -> tuple[str, ...]:
    return tuple(
        mode
        for mode, patterns in MODE_PATTERNS.items()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    )


def _classify_mode(text: str) -> tuple[str, tuple[str, ...]]:
    matching = _matching_modes(text)
    matching_set = set(matching)
    if "SUMMARIZE" in matching_set and "WRITE" in matching_set:
        mode = "WRITE"
    elif "SUMMARIZE" in matching_set and "EXPORT" in matching_set:
        mode = "EXPORT"
    else:
        mode = matching[0] if matching else "REASON"
    if mode in MUTATING_INTENT_MODES and any(
        re.search(pattern, text, flags=re.IGNORECASE) for pattern in NON_EXECUTION_PATTERNS
    ):
        mode = "PROPOSE"
    return mode, matching


def _ambiguity_bp(
    objective: str,
    mode: str,
    target_paths: tuple[str, ...],
    unresolved_count: int,
    matching_modes: tuple[str, ...],
) -> int:
    score = 0
    words = re.findall(r"[A-Za-z0-9_'-]+", objective)
    if len(words) < 3:
        score += 2_500
    if mode in MUTATING_INTENT_MODES and not target_paths:
        score += 3_500
    if any(re.search(pattern, objective, flags=re.IGNORECASE) for pattern in VAGUE_PATTERNS):
        score += 1_500
    if unresolved_count:
        score += 4_000
    if len(matching_modes) > 1:
        score += min(2_000, (len(matching_modes) - 1) * 500)
    return min(SCORE_SCALE, score)


def interpret_natural_language(
    text: str,
    workspace: Workspace,
    *,
    known_evidence_ids: Iterable[str] = (),
) -> InterpretedIntent:
    context = resolve_context(text, workspace, known_evidence_ids=known_evidence_ids)
    if not context.objective_text:
        raise ValueError("natural-language interaction must include an objective")
    mode, matching_modes = _classify_mode(context.objective_text)
    formal_writing = interpret_formal_writing(context.source_text, context)
    if formal_writing is not None:
        if formal_writing.operation in {"WRITE", "REVISE"}:
            mode = "WRITE"
        elif formal_writing.operation == "DRAFT":
            mode = "PROPOSE"
        elif formal_writing.operation in {"OUTLINE", "BUILD_SOURCE_MAP", "BUILD_ARGUMENT_MAP"}:
            mode = "PLAN"
        else:
            mode = "INSPECT"
    ambiguity = _ambiguity_bp(
        context.objective_text,
        mode,
        context.target_paths,
        len(context.unresolved_references),
        matching_modes,
    )
    proposed_risk = "L2" if mode in {"EXECUTE", "RECOVER"} else "L1" if mode in {"WRITE", "TEST"} else "L0"
    requires_confirmation = bool(
        mode in MUTATING_INTENT_MODES
        or context.has_unresolved_references
        or ambiguity >= AMBIGUITY_CONFIRMATION_BP
    )
    if formal_writing is not None and mode not in MUTATING_INTENT_MODES:
        requires_confirmation = bool(
            context.has_unresolved_references
            or ambiguity >= AMBIGUITY_CONFIRMATION_BP
        )
    return InterpretedIntent(
        source_text=context.source_text,
        objective=context.objective_text,
        mode=mode,
        target_paths=context.target_paths,
        referenced_evidence_ids=context.evidence_ids,
        constraints=context.constraints,
        requested_outputs=MODE_OUTPUTS[mode],
        ambiguity_bp=ambiguity,
        proposed_risk=proposed_risk,
        requires_confirmation=requires_confirmation,
        formal_writing=formal_writing,
    )


__all__ = [
    "AMBIGUITY_CONFIRMATION_BP",
    "MODE_OUTPUTS",
    "MODE_PATTERNS",
    "NON_EXECUTION_PATTERNS",
    "interpret_natural_language",
]
