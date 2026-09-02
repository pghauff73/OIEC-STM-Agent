from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

from .models import FormalWritingRequest


WRITING_PROFILES = (
    "general",
    "scientific-essay",
    "argumentative-essay",
    "engineering-report",
    "literature-review",
    "business-analysis",
    "research-proposal",
    "lab-report",
)


COMMAND_OPERATIONS = {
    "plan": "OUTLINE",
    "research": "BUILD_SOURCE_MAP",
    "argue": "BUILD_ARGUMENT_MAP",
    "audit": "VALIDATE",
    "explain": "EXPLAIN_REFERENCE",
    "export": "EXPORT_REFERENCES",
    "inspect": "INSPECT_SOURCES",
    "locate": "LOCATE_REFERENCE",
    "explain-reference": "EXPLAIN_REFERENCE",
    "source-map": "BUILD_SOURCE_MAP",
    "argument-map": "BUILD_ARGUMENT_MAP",
    "outline": "OUTLINE",
    "draft": "DRAFT",
    "revise": "REVISE",
    "validate": "VALIDATE",
    "write": "WRITE",
    "references": "EXPORT_REFERENCES",
}


def compile_formal_writing_request(
    *,
    operation: str,
    objective: str,
    profile: str = "general",
    genre: str = "essay",
    audience: str = "general",
    discipline: str = "general",
    word_target: int = 0,
    source_document_ids: Sequence[str] = (),
    source_paths: Sequence[str] = (),
    rubric_paths: Sequence[str] = (),
    draft_paths: Sequence[str] = (),
    output_paths: Sequence[str] = (),
    citation_style: str = "author-date",
    locale: str = "en",
    network_policy: str = "offline",
    constraints: Sequence[str] = (),
    requested_outputs: Sequence[str] = (),
    authority_binding: str = "",
    context_envelope_signature: str = "",
) -> FormalWritingRequest:
    if profile not in WRITING_PROFILES:
        raise ValueError(f"unsupported writing profile: {profile}")
    normalized_operation = COMMAND_OPERATIONS.get(operation.casefold(), operation.upper())
    return FormalWritingRequest(
        operation=normalized_operation,
        objective=objective,
        profile=profile,
        genre=genre,
        audience=audience,
        discipline=discipline,
        word_target=word_target,
        source_document_ids=tuple(source_document_ids),
        source_paths=tuple(source_paths),
        rubric_paths=tuple(rubric_paths),
        draft_paths=tuple(draft_paths),
        output_paths=tuple(output_paths),
        citation_style=citation_style,
        locale=locale,
        network_policy=network_policy,
        constraints=tuple(constraints),
        requested_outputs=tuple(requested_outputs),
        authority_binding=authority_binding,
        context_envelope_signature=context_envelope_signature,
    )


def infer_formal_operation(text: str) -> str | None:
    lowered = text.casefold()
    patterns = (
        ("WRITE", (r"\bwrite\b", r"\bcreate\b")),
        ("REVISE", (r"\brevise\b", r"\bedit\b")),
        ("VALIDATE", (r"\bvalidate\b", r"\bverify\b", r"\bcheck\b")),
        ("DRAFT", (r"\bdraft\b",)),
        ("OUTLINE", (r"\boutline\b", r"\bplan\b")),
        ("BUILD_ARGUMENT_MAP", (r"argument map", r"reasoning map", r"claim-evidence")),
        ("BUILD_SOURCE_MAP", (r"source map", r"literature map")),
        ("EXPLAIN_REFERENCE", (r"explain (?:the )?(?:reference|passage)", r"reasoning role", r"concept")),
        (
            "LOCATE_REFERENCE",
            (
                r"\blocate\b",
                r"\bfind the page\b",
                r"\bpoint to\b",
                r"\bquote\b",
                r"\bquotation\b",
                r"\bextract\b.*\breference\b",
                r"\bpage[- ]accurate reference\b",
            ),
        ),
        ("EXPORT_REFERENCES", (r"\bbibliography\b", r"\breferences\b")),
        ("INSPECT_SOURCES", (r"\binspect\b", r"\bread sources\b")),
    )
    for operation, candidates in patterns:
        if any(re.search(pattern, lowered) for pattern in candidates):
            return operation
    formal_nouns = (
        "essay",
        "paper",
        "report",
        "literature review",
        "citation",
        "source",
        "reference",
        "thesis",
    )
    return "OUTLINE" if any(noun in lowered for noun in formal_nouns) else None


__all__ = [
    "COMMAND_OPERATIONS",
    "WRITING_PROFILES",
    "compile_formal_writing_request",
    "infer_formal_operation",
]
