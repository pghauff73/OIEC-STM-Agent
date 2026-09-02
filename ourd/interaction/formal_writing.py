from __future__ import annotations

import re

from ..writing_engine.compiler import infer_formal_operation
from .models import FormalWritingIntent, ResolvedContext


FORMAL_NOUN_PATTERN = re.compile(
    r"\b(essay|paper|report|literature review|argument|thesis|paragraph|citation|bibliography|quotation|paraphrase|source|reference)\b",
    flags=re.IGNORECASE,
)


def _paths(context: ResolvedContext, kind: str) -> tuple[str, ...]:
    return tuple(item.value for item in context.references if item.kind == kind)


def _fallback_paths(context: ResolvedContext, kinds: set[str]) -> tuple[str, ...]:
    return tuple(item.value for item in context.references if item.kind in kinds)


def interpret_formal_writing(text: str, context: ResolvedContext) -> FormalWritingIntent | None:
    operation = infer_formal_operation(text)
    role_reference_present = any(
        item.kind in {"source", "sourcefolder", "rubric", "output", "draft", "style", "file", "folder", "path"}
        for item in context.references
    )
    explicit_formal_action = bool(
        re.search(
            r"\b(locate|extract|reference|cite|quote|quotation|paraphrase|outline|draft|revise|bibliography|citation|claim|premise|warrant|counterclaim|thesis|page[- ]accurate)\b",
            text,
            re.IGNORECASE,
        )
    )
    strong_formal_noun = bool(
        re.search(r"\b(essay|paper|literature review|bibliography|citation|quotation|paraphrase|reference|thesis)\b", text, re.IGNORECASE)
        or re.search(
            r"(?:\bformal\s+report\b|\breport\s+(?:from|using|on|about|based on)\b)",
            text,
            re.IGNORECASE,
        )
        or (role_reference_present and re.search(r"\breport\b", text, re.IGNORECASE))
    )
    if operation is None or not (explicit_formal_action or strong_formal_noun):
        return None
    style_values = _paths(context, "style")
    word_match = re.search(r"\b(\d{2,6})[- ]word\b", text, flags=re.IGNORECASE)
    if re.search(r"\b(full text|retrieve remote)\b", text, re.IGNORECASE):
        network_policy = "explicit-retrieval"
    elif re.search(r"\b(crossref|doi metadata|remote metadata)\b", text, re.IGNORECASE):
        network_policy = "metadata-only"
    else:
        network_policy = "offline"
    return FormalWritingIntent(
        operation=operation,
        profile=(
            "scientific-essay"
            if re.search(r"\bscientific essay\b", text, re.IGNORECASE)
            else "argumentative-essay"
            if re.search(r"\bargumentative essay\b", text, re.IGNORECASE)
            else "general"
        ),
        source_paths=_paths(context, "source") or _fallback_paths(context, {"file", "path"}),
        source_folder_paths=_paths(context, "sourcefolder") or _fallback_paths(context, {"folder"}),
        rubric_paths=_paths(context, "rubric"),
        output_paths=_paths(context, "output"),
        draft_paths=_paths(context, "draft"),
        citation_style=(
            style_values[0]
            if style_values
            else "apa-7"
            if re.search(r"\bAPA\s*7\b", text, re.IGNORECASE)
            else "author-date"
        ),
        word_target=int(word_match.group(1)) if word_match else 0,
        require_page_accuracy=bool(
            re.search(r"\b(page[- ]accurate|exact page|page accuracy)\b", text, re.IGNORECASE)
        ),
        allow_ocr=bool(re.search(r"\ballow OCR\b", text, re.IGNORECASE)),
        network_policy=network_policy,
    )


__all__ = ["FORMAL_NOUN_PATTERN", "interpret_formal_writing"]
