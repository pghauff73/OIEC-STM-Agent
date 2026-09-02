from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Tuple

from ..errors import PolicyError
from ..reasoning.models import stable_hash
from ..workspace import Workspace
from .context import resolve_context
from .envelope import (
    ContextProjectionBudget,
    InteractionContextEnvelope,
    build_context_envelope,
)
from .models import canonical_strings
from .routing import route_interaction


MAX_PINNED_CONTEXT_PATHS = 32


def format_path_references(paths: Iterable[str]) -> str:
    references = []
    for path in paths:
        value = str(path).strip()
        if not value:
            raise ValueError("pinned context path must be non-empty")
        if any(character in value for character in ("]", "\n", "\r")):
            raise ValueError("pinned context paths cannot contain ']', newlines, or returns")
        references.append(f"@path[{value}]")
    if not references:
        raise ValueError("at least one pinned context path is required")
    return " ".join(references)


@dataclass(frozen=True)
class PinnedContextSet:
    schema_version: int = 1
    paths: Tuple[str, ...] = ()
    context_id: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("pinned context schema_version must be 1")
        paths = canonical_strings(self.paths)
        if len(paths) > MAX_PINNED_CONTEXT_PATHS:
            raise ValueError(
                f"pinned context exceeds {MAX_PINNED_CONTEXT_PATHS} paths"
            )
        for path in paths:
            format_path_references((path,))
            if path.startswith("/") or path == ".." or path.startswith("../"):
                raise ValueError(f"pinned context path is not canonical: {path}")
        material = {
            "schema_version": self.schema_version,
            "paths": paths,
            "authoritative": False,
        }
        expected_id = f"pinned-context:{stable_hash(material)}"
        if self.context_id and self.context_id != expected_id:
            raise ValueError("pinned context ID mismatch")
        signature_material = {**material, "context_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("pinned context signature mismatch")
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "context_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PinnedContextSet":
        return cls(**dict(payload))

    def add(self, workspace: Workspace, paths: Iterable[str]) -> "PinnedContextSet":
        canonical = [workspace.canonical(str(path)) for path in paths]
        combined = canonical_strings((*self.paths, *canonical))
        if len(combined) > MAX_PINNED_CONTEXT_PATHS:
            raise PolicyError(
                f"pinned context exceeds {MAX_PINNED_CONTEXT_PATHS} paths"
            )
        return PinnedContextSet(paths=combined)

    def remove(
        self,
        workspace: Workspace,
        paths: Iterable[str],
    ) -> "PinnedContextSet":
        removed = {workspace.canonical(str(path)) for path in paths}
        return PinnedContextSet(
            paths=tuple(path for path in self.paths if path not in removed)
        )

    def clear(self) -> "PinnedContextSet":
        return PinnedContextSet()

    def apply_to(self, text: str, workspace: Workspace) -> str:
        source = text.strip()
        if not source or source.startswith("/") or not self.paths:
            return source
        resolved = resolve_context(source, workspace)
        existing = set(resolved.target_paths)
        missing = tuple(path for path in self.paths if path not in existing)
        if not missing:
            return source
        return f"{source} {format_path_references(missing)}"


def build_pinned_context_envelope(
    pinned_context: PinnedContextSet,
    workspace: Workspace,
    *,
    source_snapshot_hash: str,
    known_evidence_ids: Iterable[str] = (),
    budget: ContextProjectionBudget | None = None,
) -> InteractionContextEnvelope | None:
    if not pinned_context.paths:
        return None
    references = format_path_references(pinned_context.paths)
    route = route_interaction(
        f"inspect {references}",
        workspace,
        known_evidence_ids=known_evidence_ids,
    )
    return build_context_envelope(
        route,
        workspace,
        source_snapshot_hash=source_snapshot_hash,
        known_evidence_ids=known_evidence_ids,
        budget=budget,
    )


__all__ = [
    "MAX_PINNED_CONTEXT_PATHS",
    "PinnedContextSet",
    "build_pinned_context_envelope",
    "format_path_references",
]
