from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Tuple

from ..errors import PolicyError
from ..reasoning.models import stable_hash
from ..workspace import Workspace
from .context import resolve_context
from .models import ContextReference, InteractionRoute, canonical_strings


MEDIA_TYPES = {
    ".c": "text/x-c",
    ".cc": "text/x-c++",
    ".cpp": "text/x-c++",
    ".css": "text/css",
    ".csv": "text/csv",
    ".h": "text/x-c",
    ".hpp": "text/x-c++",
    ".html": "text/html",
    ".ini": "text/plain",
    ".js": "text/javascript",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".rst": "text/x-rst",
    ".svg": "image/svg+xml",
    ".toml": "application/toml",
    ".ts": "text/typescript",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


@dataclass(frozen=True)
class ContextProjectionBudget:
    schema_version: int = 1
    max_references: int = 32
    max_files: int = 128
    max_files_per_folder: int = 64
    max_directory_entries: int = 512
    max_folder_entries_scanned: int = 4_096
    max_folder_depth: int = 8
    max_preview_bytes_per_file: int = 8_192
    max_total_preview_bytes: int = 65_536
    max_hash_file_bytes: int = 16 * 1024 * 1024
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context projection budget schema_version must be 1")
        for name in (
            "max_references",
            "max_files",
            "max_files_per_folder",
            "max_directory_entries",
            "max_folder_entries_scanned",
            "max_folder_depth",
            "max_preview_bytes_per_file",
            "max_total_preview_bytes",
            "max_hash_file_bytes",
        ):
            value = int(getattr(self, name))
            if value < 1:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        material = {
            "schema_version": self.schema_version,
            "max_references": self.max_references,
            "max_files": self.max_files,
            "max_files_per_folder": self.max_files_per_folder,
            "max_directory_entries": self.max_directory_entries,
            "max_folder_entries_scanned": self.max_folder_entries_scanned,
            "max_folder_depth": self.max_folder_depth,
            "max_preview_bytes_per_file": self.max_preview_bytes_per_file,
            "max_total_preview_bytes": self.max_total_preview_bytes,
            "max_hash_file_bytes": self.max_hash_file_bytes,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context projection budget signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextProjectionBudget":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ContextFileProjection:
    schema_version: int = 1
    path: str = ""
    size_bytes: int = 0
    media_type: str = "application/octet-stream"
    content_sha256: str = ""
    hash_status: str = "omitted"
    preview_kind: str = "omitted"
    preview_text: str = ""
    preview_bytes: int = 0
    preview_truncated: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context file projection schema_version must be 1")
        path = self.path.strip()
        if not path:
            raise ValueError("context file projection path must be non-empty")
        size = int(self.size_bytes)
        preview_bytes = int(self.preview_bytes)
        if size < 0 or preview_bytes < 0:
            raise ValueError("context file projection sizes cannot be negative")
        if self.hash_status not in {"exact", "omitted_size_limit"}:
            raise ValueError(f"invalid context file hash status: {self.hash_status}")
        if self.hash_status == "exact" and len(self.content_sha256) != 64:
            raise ValueError("exact context file hashes must be SHA-256 digests")
        if self.preview_kind not in {"text", "binary", "omitted_budget"}:
            raise ValueError(f"invalid context file preview kind: {self.preview_kind}")
        if self.preview_kind != "text" and self.preview_text:
            raise ValueError("only text context previews may contain preview text")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "size_bytes", size)
        object.__setattr__(self, "preview_bytes", preview_bytes)
        material = {
            "schema_version": self.schema_version,
            "path": path,
            "size_bytes": size,
            "media_type": self.media_type,
            "content_sha256": self.content_sha256,
            "hash_status": self.hash_status,
            "preview_kind": self.preview_kind,
            "preview_text": self.preview_text,
            "preview_bytes": preview_bytes,
            "preview_truncated": bool(self.preview_truncated),
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context file projection signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextFileProjection":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ContextAttachmentProjection:
    schema_version: int = 1
    reference_id: str = ""
    kind: str = "path"
    value: str = ""
    status: str = "unresolved"
    file_paths: Tuple[str, ...] = ()
    truncated: bool = False
    note: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context attachment projection schema_version must be 1")
        if not self.reference_id:
            raise ValueError("context attachment projection requires a reference ID")
        kind = self.kind.strip().casefold()
        value = self.value.strip()
        status = self.status.strip().casefold()
        if not kind or not value or not status:
            raise ValueError("context attachment projection fields must be non-empty")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "file_paths", canonical_strings(self.file_paths))
        object.__setattr__(self, "note", self.note.strip())
        material = {
            "schema_version": self.schema_version,
            "reference_id": self.reference_id,
            "kind": kind,
            "value": value,
            "status": status,
            "file_paths": self.file_paths,
            "truncated": bool(self.truncated),
            "note": self.note,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context attachment projection signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextAttachmentProjection":
        return cls(**dict(payload))


@dataclass(frozen=True)
class InteractionContextEnvelope:
    schema_version: int = 1
    envelope_id: str = ""
    route_id: str = ""
    route_signature: str = ""
    source_snapshot_hash: str = ""
    objective: str = ""
    mode: str = "REASON"
    original_request: str = ""
    budget: ContextProjectionBudget = ContextProjectionBudget()
    attachments: Tuple[ContextAttachmentProjection, ...] = ()
    files: Tuple[ContextFileProjection, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()
    unresolved_reference_ids: Tuple[str, ...] = ()
    total_preview_bytes: int = 0
    model_input: str = ""
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("interaction context envelope schema_version must be 1")
        if self.authoritative:
            raise ValueError("interaction context envelope cannot be authoritative")
        if not self.route_id or not self.route_signature:
            raise ValueError("interaction context envelope requires route identity")
        if len(self.source_snapshot_hash) != 64:
            raise ValueError("interaction context envelope requires a SHA-256 source snapshot")
        if not self.objective.strip() or not self.original_request.strip():
            raise ValueError("interaction context envelope requires an objective and original request")
        if not self.model_input.strip():
            raise ValueError("interaction context envelope model input must be non-empty")
        attachments = tuple(sorted(self.attachments, key=lambda item: item.reference_id))
        files = tuple(sorted(self.files, key=lambda item: item.path))
        if len({item.reference_id for item in attachments}) != len(attachments):
            raise ValueError("interaction context attachment IDs must be unique")
        if len({item.path for item in files}) != len(files):
            raise ValueError("interaction context file paths must be unique")
        total_preview_bytes = int(self.total_preview_bytes)
        if total_preview_bytes != sum(item.preview_bytes for item in files):
            raise ValueError("interaction context total preview bytes mismatch")
        if len(attachments) > self.budget.max_references:
            raise ValueError("interaction context exceeds its reference budget")
        if len(files) > self.budget.max_files:
            raise ValueError("interaction context exceeds its file budget")
        if total_preview_bytes > self.budget.max_total_preview_bytes:
            raise ValueError("interaction context exceeds its preview budget")
        object.__setattr__(self, "objective", self.objective.strip())
        object.__setattr__(self, "mode", self.mode.strip().upper())
        object.__setattr__(self, "original_request", self.original_request.strip())
        object.__setattr__(self, "attachments", attachments)
        object.__setattr__(self, "files", files)
        object.__setattr__(self, "evidence_ids", canonical_strings(self.evidence_ids))
        object.__setattr__(self, "constraints", canonical_strings(self.constraints))
        object.__setattr__(
            self,
            "unresolved_reference_ids",
            canonical_strings(self.unresolved_reference_ids),
        )
        object.__setattr__(self, "total_preview_bytes", total_preview_bytes)
        object.__setattr__(self, "model_input", self.model_input.strip())
        material = {
            "schema_version": self.schema_version,
            "route_id": self.route_id,
            "route_signature": self.route_signature,
            "source_snapshot_hash": self.source_snapshot_hash,
            "objective": self.objective,
            "mode": self.mode,
            "original_request": self.original_request,
            "budget": asdict(self.budget),
            "attachments": tuple(asdict(item) for item in attachments),
            "files": tuple(asdict(item) for item in files),
            "evidence_ids": self.evidence_ids,
            "constraints": self.constraints,
            "unresolved_reference_ids": self.unresolved_reference_ids,
            "total_preview_bytes": total_preview_bytes,
            "model_input": self.model_input,
            "authoritative": False,
        }
        expected_id = f"context-envelope:{stable_hash(material)}"
        if self.envelope_id and self.envelope_id != expected_id:
            raise ValueError("interaction context envelope ID mismatch")
        signature_material = {**material, "envelope_id": expected_id}
        expected_signature = stable_hash(signature_material)
        if self.signature and self.signature != expected_signature:
            raise ValueError("interaction context envelope signature mismatch")
        object.__setattr__(self, "envelope_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InteractionContextEnvelope":
        values = dict(payload)
        values["budget"] = ContextProjectionBudget.from_dict(values.get("budget", {}))
        values["attachments"] = tuple(
            ContextAttachmentProjection.from_dict(item)
            for item in values.get("attachments", ())
        )
        values["files"] = tuple(
            ContextFileProjection.from_dict(item) for item in values.get("files", ())
        )
        return cls(**values)


def _project_file(
    workspace: Workspace,
    path: str,
    budget: ContextProjectionBudget,
    remaining_preview_bytes: int,
) -> ContextFileProjection:
    resolved = workspace.resolve(path)
    if not resolved.is_file():
        raise PolicyError(f"context file is not a regular file: {path}")
    size = resolved.stat().st_size
    if size <= budget.max_hash_file_bytes:
        content_sha256 = workspace.file_sha256(resolved)
        hash_status = "exact"
    else:
        content_sha256 = ""
        hash_status = "omitted_size_limit"
    preview_limit = min(budget.max_preview_bytes_per_file, remaining_preview_bytes)
    media_type = MEDIA_TYPES.get(Path(path).suffix.casefold(), "application/octet-stream")
    if preview_limit <= 0:
        return ContextFileProjection(
            path=path,
            size_bytes=size,
            media_type=media_type,
            content_sha256=content_sha256,
            hash_status=hash_status,
            preview_kind="omitted_budget",
            preview_truncated=size > 0,
        )
    with resolved.open("rb") as handle:
        raw = handle.read(preview_limit + 1)
    preview_truncated = len(raw) > preview_limit or size > preview_limit
    raw = raw[:preview_limit]
    if b"\x00" in raw:
        preview_kind = "binary"
        preview_text = ""
    else:
        try:
            preview_text = raw.decode("utf-8")
            preview_kind = "text"
            if media_type == "application/octet-stream":
                media_type = "text/plain"
        except UnicodeDecodeError:
            preview_text = ""
            preview_kind = "binary"
    return ContextFileProjection(
        path=path,
        size_bytes=size,
        media_type=media_type,
        content_sha256=content_sha256,
        hash_status=hash_status,
        preview_kind=preview_kind,
        preview_text=preview_text,
        preview_bytes=len(raw),
        preview_truncated=preview_truncated,
    )


def _reference_paths(
    workspace: Workspace,
    reference: ContextReference,
    budget: ContextProjectionBudget,
) -> tuple[Tuple[str, ...], bool, str]:
    if reference.kind == "style":
        return (), False, "formal-writing style reference"
    if reference.kind not in {
        "file",
        "folder",
        "path",
        "source",
        "sourcefolder",
        "rubric",
        "output",
        "draft",
    }:
        return (), False, "non-filesystem reference"
    if reference.status == "unresolved":
        return (), False, "reference is unresolved"
    resolved = workspace.resolve(reference.value)
    if not resolved.exists():
        return (), False, "prospective path; no current file content"
    if resolved.is_file():
        return (reference.value,), False, "single file"
    if not resolved.is_dir():
        return (), False, "unsupported filesystem object"
    selected, truncated, scanned_entries = _bounded_folder_paths(
        workspace,
        resolved,
        budget,
    )
    note = (
        f"folder projection limited to {len(selected)} files after scanning {scanned_entries} entries"
        if truncated
        else f"folder projection contains {len(selected)} files after scanning {scanned_entries} entries"
    )
    return selected, truncated, note


def _bounded_folder_paths(
    workspace: Workspace,
    root: Path,
    budget: ContextProjectionBudget,
) -> tuple[Tuple[str, ...], bool, int]:
    selected: list[str] = []
    scanned_entries = 0
    truncated = False

    def visit(directory: Path, depth: int) -> bool:
        nonlocal scanned_entries, truncated
        entries: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if len(entries) >= budget.max_directory_entries:
                    raise PolicyError(
                        f"context directory entry budget exceeded: {workspace.rel(directory)}"
                    )
                entries.append(entry)
        for entry in sorted(entries, key=lambda item: item.name):
            scanned_entries += 1
            if scanned_entries > budget.max_folder_entries_scanned:
                raise PolicyError("context folder scan entry budget exceeded")
            if Workspace.ignored_parts((entry.name,)):
                continue
            entry_path = Path(entry.path)
            if entry.is_file(follow_symlinks=False):
                try:
                    relative = workspace.rel(entry_path)
                except (PolicyError, ValueError):
                    continue
                selected.append(relative)
                if len(selected) > budget.max_files_per_folder:
                    selected.pop()
                    truncated = True
                    return False
            elif entry.is_dir(follow_symlinks=False):
                if depth >= budget.max_folder_depth:
                    truncated = True
                    continue
                if not visit(entry_path, depth + 1):
                    return False
        return True

    visit(root, 0)
    return tuple(selected), truncated, scanned_entries


def _render_model_input(
    route: InteractionRoute,
    source_snapshot_hash: str,
    attachments: Tuple[ContextAttachmentProjection, ...],
    files: Tuple[ContextFileProjection, ...],
    evidence_ids: Tuple[str, ...],
    constraints: Tuple[str, ...],
) -> str:
    assert route.intent is not None
    intent = route.intent
    lines = [
        "[OIEC-STM-SR-AgentICPI STRUCTURED REQUEST]",
        f"Route-ID: {route.route_id}",
        f"Source-Snapshot: {source_snapshot_hash}",
        f"Mode: {intent.mode}",
        f"Objective: {intent.objective}",
        f"Proposed-Risk: {intent.proposed_risk}",
        f"Original-Request: {intent.source_text}",
        f"Targets: {', '.join(intent.target_paths) if intent.target_paths else 'none'}",
        f"Evidence-References: {', '.join(evidence_ids) if evidence_ids else 'none'}",
        f"Constraints: {', '.join(constraints) if constraints else 'none'}",
        f"Requested-Outputs: {', '.join(intent.requested_outputs)}",
        "",
        "[BOUNDED CONTEXT ATTACHMENTS]",
    ]
    if not attachments:
        lines.append("No explicit context references were supplied.")
    for attachment in attachments:
        lines.append(
            f"REFERENCE {attachment.kind} {attachment.value} status={attachment.status} "
            f"files={len(attachment.file_paths)} truncated={str(attachment.truncated).lower()} "
            f"note={attachment.note or 'none'}"
        )
    for file in files:
        digest = file.content_sha256 if file.hash_status == "exact" else file.hash_status
        lines.extend(
            [
                "",
                f"FILE {file.path}",
                f"size={file.size_bytes} media_type={file.media_type} sha256={digest}",
                f"preview={file.preview_kind} bytes={file.preview_bytes} "
                f"truncated={str(file.preview_truncated).lower()}",
            ]
        )
        if file.preview_kind == "text":
            lines.extend(("--- bounded preview ---", file.preview_text, "--- end preview ---"))
    lines.extend(
        [
            "",
            "[CONTROL BOUNDARY]",
            "This context envelope is a non-authoritative projection.",
            "It does not grant authority, lower policy risk, approve evidence, approve an EON action, or permit mutation.",
            "Use repository tools and canonical evidence to verify any claim before relying on it.",
        ]
    )
    return "\n".join(lines).strip()


def build_context_envelope(
    route: InteractionRoute,
    workspace: Workspace,
    *,
    source_snapshot_hash: str,
    known_evidence_ids: Iterable[str] = (),
    budget: ContextProjectionBudget | None = None,
) -> InteractionContextEnvelope:
    if route.kind != "INTENT" or route.intent is None:
        raise ValueError("context envelopes require a natural-language intent route")
    projection_budget = budget or ContextProjectionBudget()
    if workspace.snapshot_hash() != source_snapshot_hash:
        raise PolicyError("context envelope source snapshot mismatch before projection")
    context = resolve_context(
        route.intent.source_text,
        workspace,
        known_evidence_ids=known_evidence_ids,
    )
    if context.target_paths != route.intent.target_paths:
        raise PolicyError("context target projection does not match interpreted intent")
    if context.evidence_ids != route.intent.referenced_evidence_ids:
        raise PolicyError("context evidence projection does not match interpreted intent")
    if context.constraints != route.intent.constraints:
        raise PolicyError("context constraint projection does not match interpreted intent")
    if len(context.references) > projection_budget.max_references:
        raise PolicyError(
            f"context reference budget exceeded: {len(context.references)} > "
            f"{projection_budget.max_references}"
        )

    file_projections: dict[str, ContextFileProjection] = {}
    attachment_projections: list[ContextAttachmentProjection] = []
    remaining_preview_bytes = projection_budget.max_total_preview_bytes
    for reference in context.references:
        candidate_paths, folder_truncated, note = _reference_paths(
            workspace,
            reference,
            projection_budget,
        )
        remaining_file_slots = projection_budget.max_files - len(file_projections)
        selected_paths = tuple(
            path for path in candidate_paths if path not in file_projections
        )[: max(0, remaining_file_slots)]
        global_truncated = len(
            tuple(path for path in candidate_paths if path not in file_projections)
        ) > len(selected_paths)
        for path in selected_paths:
            projection = _project_file(
                workspace,
                path,
                projection_budget,
                remaining_preview_bytes,
            )
            file_projections[path] = projection
            remaining_preview_bytes = max(
                0,
                remaining_preview_bytes - projection.preview_bytes,
            )
        referenced_paths = tuple(
            path for path in candidate_paths if path in file_projections
        )
        if global_truncated:
            note = f"{note}; global file budget reached"
        attachment_projections.append(
            ContextAttachmentProjection(
                reference_id=reference.reference_id,
                kind=reference.kind,
                value=reference.value,
                status=reference.status,
                file_paths=referenced_paths,
                truncated=folder_truncated or global_truncated,
                note=note,
            )
        )

    attachments = tuple(attachment_projections)
    files = tuple(file_projections.values())
    evidence_ids = context.evidence_ids
    constraints = context.constraints
    model_input = _render_model_input(
        route,
        source_snapshot_hash,
        attachments,
        files,
        evidence_ids,
        constraints,
    )
    if workspace.snapshot_hash() != source_snapshot_hash:
        raise PolicyError("context envelope source changed during projection")
    return InteractionContextEnvelope(
        route_id=route.route_id,
        route_signature=route.signature,
        source_snapshot_hash=source_snapshot_hash,
        objective=route.intent.objective,
        mode=route.intent.mode,
        original_request=route.intent.source_text,
        budget=projection_budget,
        attachments=attachments,
        files=files,
        evidence_ids=evidence_ids,
        constraints=constraints,
        unresolved_reference_ids=context.unresolved_references,
        total_preview_bytes=sum(item.preview_bytes for item in files),
        model_input=model_input,
    )


__all__ = [
    "ContextAttachmentProjection",
    "ContextFileProjection",
    "ContextProjectionBudget",
    "InteractionContextEnvelope",
    "build_context_envelope",
]
