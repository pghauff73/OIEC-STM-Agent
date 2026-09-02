from __future__ import annotations

import re
import shlex
from typing import Iterable

from ..workspace import Workspace
from .models import ContextReference, ResolvedContext


BRACKET_REFERENCE_PATTERN = re.compile(
    r"(?P<prefix>@sourcefolder|@source|@rubric|@output|@draft|@style|@file|@folder|@path|#evidence|!constraint)\[(?P<value>[^\]]+)\]"
)
ROOT_SHORTHAND_PATTERN = re.compile(
    r"(?<![\w@])/(?P<path>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)/"
)
BARE_WORKSPACE_PATH_PATTERN = re.compile(
    r"^(?:\./)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/?$|^[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+$"
)
BARE_WORKSPACE_GLOB_PATTERN = re.compile(
    r"^(?:\./)?[A-Za-z0-9_./*?\[\]-]+$"
)


def _bare_workspace_path(token: str) -> str:
    candidate = token.strip().strip("`")
    while candidate and candidate[-1] in ".,;:":
        candidate = candidate[:-1]
    if (
        not candidate
        or candidate.startswith(("/", "~"))
        or ".." in candidate.split("/")
        or not BARE_WORKSPACE_PATH_PATTERN.match(candidate)
    ):
        return ""
    return candidate


def _bare_workspace_glob(token: str) -> str:
    candidate = token.strip().strip("`")
    while candidate and candidate[-1] in ".,;:":
        candidate = candidate[:-1]
    if (
        not candidate
        or not any(marker in candidate for marker in ("*", "?", "["))
        or candidate.startswith(("/", "~"))
        or ".." in candidate.split("/")
        or not BARE_WORKSPACE_GLOB_PATTERN.match(candidate)
    ):
        return ""
    return candidate


def _missing_bare_path_kind(candidate: str, canonical: str) -> str:
    if candidate.endswith("/"):
        return "folder"
    if "/" not in candidate and "." not in canonical.rsplit("/", 1)[-1]:
        return ""
    if "." in canonical.rsplit("/", 1)[-1]:
        return "file"
    return "path"


def _reference_kind(prefix: str) -> str:
    return {
        "@file": "file",
        "@folder": "folder",
        "@path": "path",
        "@source": "source",
        "@sourcefolder": "sourcefolder",
        "@rubric": "rubric",
        "@output": "output",
        "@draft": "draft",
        "@style": "style",
        "#evidence": "evidence",
        "!constraint": "constraint",
    }[prefix]


def _path_reference(workspace: Workspace, kind: str, value: str) -> ContextReference:
    if kind == "style":
        return ContextReference(kind=kind, value=value, status="resolved")
    canonical = workspace.canonical(value)
    resolved = workspace.resolve(canonical)
    if kind in {"file", "source", "rubric", "draft"}:
        status = "resolved" if resolved.is_file() else "unresolved"
    elif kind in {"folder", "sourcefolder"}:
        status = "resolved" if resolved.is_dir() else "unresolved"
    else:
        status = "resolved" if resolved.exists() else "prospective"
    return ContextReference(kind=kind, value=canonical, status=status)


def _evidence_reference(value: str, known_evidence_ids: set[str]) -> ContextReference:
    evidence_id = value.strip()
    if not evidence_id:
        raise ValueError("evidence reference must be non-empty")
    if evidence_id in known_evidence_ids:
        status = "resolved"
    elif known_evidence_ids:
        status = "unresolved"
    else:
        status = "unverified"
    return ContextReference(kind="evidence", value=evidence_id, status=status)


def _make_reference(
    workspace: Workspace,
    kind: str,
    value: str,
    known_evidence_ids: set[str],
) -> ContextReference:
    if kind in {
        "file",
        "folder",
        "path",
        "source",
        "sourcefolder",
        "rubric",
        "output",
        "draft",
        "style",
    }:
        return _path_reference(workspace, kind, value)
    if kind == "evidence":
        return _evidence_reference(value, known_evidence_ids)
    return ContextReference(kind="constraint", value=value, status="resolved")


def resolve_context(
    text: str,
    workspace: Workspace,
    *,
    known_evidence_ids: Iterable[str] = (),
) -> ResolvedContext:
    source_text = text.strip()
    if not source_text:
        raise ValueError("interaction text must be non-empty")
    known_ids = {str(value).strip() for value in known_evidence_ids if str(value).strip()}
    references: list[ContextReference] = []
    spans: list[tuple[int, int]] = []
    for match in BRACKET_REFERENCE_PATTERN.finditer(source_text):
        kind = _reference_kind(match.group("prefix"))
        references.append(
            _make_reference(workspace, kind, match.group("value"), known_ids)
        )
        spans.append(match.span())
    for match in ROOT_SHORTHAND_PATTERN.finditer(source_text):
        candidate = match.group("path")
        try:
            canonical = workspace.canonical(candidate)
            resolved = workspace.resolve(canonical)
        except Exception:
            continue
        if not resolved.exists():
            continue
        kind = "folder" if resolved.is_dir() else "file"
        references.append(_path_reference(workspace, kind, canonical))
        spans.append(match.span())

    residual_characters = list(source_text)
    for start, end in spans:
        residual_characters[start:end] = " " * (end - start)
    residual = "".join(residual_characters)
    try:
        tokens = shlex.split(residual)
    except ValueError as exc:
        raise ValueError(f"invalid interaction quoting: {exc}") from exc
    objective_tokens: list[str] = []
    for token in tokens:
        if token.startswith("#evidence:"):
            references.append(_evidence_reference(token.split(":", 1)[1], known_ids))
        elif token.startswith("!constraint:"):
            references.append(
                ContextReference(
                    kind="constraint",
                    value=token.split(":", 1)[1],
                    status="resolved",
                )
            )
        elif token.startswith("@") and len(token) > 1:
            references.append(_path_reference(workspace, "path", token[1:]))
        elif glob_candidate := _bare_workspace_glob(token):
            try:
                canonical = workspace.canonical(glob_candidate)
            except Exception:
                objective_tokens.append(token)
                continue
            references.append(_path_reference(workspace, "path", canonical))
        elif candidate := _bare_workspace_path(token):
            try:
                canonical = workspace.canonical(candidate)
                resolved = workspace.resolve(canonical)
            except Exception:
                objective_tokens.append(token)
                continue
            if resolved.exists():
                kind = "folder" if resolved.is_dir() else "file"
                references.append(_path_reference(workspace, kind, canonical))
            else:
                kind = _missing_bare_path_kind(candidate, canonical)
                if kind:
                    references.append(_path_reference(workspace, kind, canonical))
                else:
                    objective_tokens.append(token)
        else:
            objective_tokens.append(token)

    unique_references = {
        (item.kind, item.value, item.status): item for item in references
    }
    ordered_references = tuple(
        unique_references[key] for key in sorted(unique_references)
    )
    target_paths = tuple(
        item.value
        for item in ordered_references
        if item.kind
        in {
            "file",
            "folder",
            "path",
            "source",
            "sourcefolder",
            "rubric",
            "output",
            "draft",
        }
    )
    evidence_ids = tuple(
        item.value for item in ordered_references if item.kind == "evidence"
    )
    constraints = tuple(
        item.value for item in ordered_references if item.kind == "constraint"
    )
    unresolved = tuple(
        item.reference_id for item in ordered_references if item.status == "unresolved"
    )
    return ResolvedContext(
        source_text=source_text,
        objective_text=" ".join(objective_tokens).strip(),
        references=ordered_references,
        target_paths=target_paths,
        evidence_ids=evidence_ids,
        constraints=constraints,
        unresolved_references=unresolved,
    )


__all__ = [
    "BARE_WORKSPACE_GLOB_PATTERN",
    "BARE_WORKSPACE_PATH_PATTERN",
    "BRACKET_REFERENCE_PATTERN",
    "ROOT_SHORTHAND_PATTERN",
    "resolve_context",
]
