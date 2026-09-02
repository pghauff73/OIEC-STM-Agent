from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ourd.interaction import ContextDelta, InteractionContextEnvelope
from ourd.reasoning.models import stable_hash


CONTEXT_INSPECTOR_SCHEMA_VERSION = 1
MAX_CONTEXT_INSPECTOR_ATTACHMENTS = 32
MAX_CONTEXT_INSPECTOR_FILES = 128
MAX_CONTEXT_INSPECTOR_PATHS_PER_ATTACHMENT = 64


def _bounded_limit(value: int, hard_limit: int) -> int:
    return max(1, min(int(value), hard_limit))


def context_envelope_audit_metadata(
    envelope: InteractionContextEnvelope,
) -> dict[str, Any]:
    """Return journal-safe envelope identity without prompt or preview bodies."""

    return {
        "context_envelope_id": envelope.envelope_id,
        "context_envelope_signature": envelope.signature,
        "context_source_snapshot": envelope.source_snapshot_hash,
        "context_route_id": envelope.route_id,
        "context_route_signature": envelope.route_signature,
        "context_budget_signature": envelope.budget.signature,
        "context_reference_count": len(envelope.attachments),
        "context_file_count": len(envelope.files),
        "context_evidence_count": len(envelope.evidence_ids),
        "context_constraint_count": len(envelope.constraints),
        "context_unresolved_reference_count": len(envelope.unresolved_reference_ids),
        "context_total_preview_bytes": envelope.total_preview_bytes,
        "context_preview_bodies_persisted": False,
    }


def context_delta_audit_metadata(delta: ContextDelta) -> dict[str, Any]:
    """Return journal-safe delta identity and counts without file contents."""

    return {
        "context_delta_signature": delta.signature,
        "context_freshness": delta.freshness,
        "context_refresh_applied": delta.refresh_applied,
        "context_workspace_snapshot_changed": delta.workspace_snapshot_changed,
        "context_baseline_snapshot": delta.baseline_source_snapshot_hash,
        "context_observed_snapshot": delta.observed_source_snapshot_hash,
        "context_delta_file_count": len(delta.files),
        "context_unchanged_file_count": delta.unchanged_count,
        "context_changed_file_count": delta.changed_count,
        "context_missing_file_count": delta.missing_count,
        "context_new_file_count": delta.new_count,
        "context_indeterminate_file_count": delta.indeterminate_count,
        "context_preview_bodies_persisted": False,
    }


def context_delta_projection(delta: ContextDelta) -> dict[str, Any]:
    """Build a bounded read-only projection of an exact context comparison."""

    return {
        "schema_version": delta.schema_version,
        "authoritative": False,
        "export_kind": "oiec-icpi-read-only-context-delta",
        "notice": (
            "This delta is observational. Applying a refresh updates only the "
            "in-memory pinned draft envelope and grants no mutation authority."
        ),
        "signature": delta.signature,
        "freshness": delta.freshness,
        "refresh_applied": delta.refresh_applied,
        "workspace_snapshot_changed": delta.workspace_snapshot_changed,
        "baseline_envelope_id": delta.baseline_envelope_id,
        "baseline_envelope_signature": delta.baseline_envelope_signature,
        "baseline_source_snapshot_hash": delta.baseline_source_snapshot_hash,
        "observed_envelope_id": delta.observed_envelope_id,
        "observed_envelope_signature": delta.observed_envelope_signature,
        "observed_source_snapshot_hash": delta.observed_source_snapshot_hash,
        "counts": {
            "unchanged": delta.unchanged_count,
            "changed": delta.changed_count,
            "missing": delta.missing_count,
            "new": delta.new_count,
            "indeterminate": delta.indeterminate_count,
        },
        "files": [
            {
                "path": item.path,
                "status": item.status,
                "previous_size_bytes": item.previous_size_bytes,
                "current_size_bytes": item.current_size_bytes,
                "previous_content_sha256": item.previous_content_sha256,
                "current_content_sha256": item.current_content_sha256,
                "previous_hash_status": item.previous_hash_status,
                "current_hash_status": item.current_hash_status,
                "signature": item.signature,
            }
            for item in delta.files
        ],
        "preview_bodies_persisted": False,
    }


def context_envelope_projection(
    envelope: InteractionContextEnvelope,
    *,
    include_preview_text: bool = False,
    max_attachments: int = MAX_CONTEXT_INSPECTOR_ATTACHMENTS,
    max_files: int = MAX_CONTEXT_INSPECTOR_FILES,
) -> dict[str, Any]:
    """Build a bounded, non-authoritative GUI projection of one exact envelope."""

    attachment_limit = _bounded_limit(
        max_attachments,
        MAX_CONTEXT_INSPECTOR_ATTACHMENTS,
    )
    file_limit = _bounded_limit(max_files, MAX_CONTEXT_INSPECTOR_FILES)

    attachments = []
    for item in envelope.attachments[:attachment_limit]:
        paths = item.file_paths[:MAX_CONTEXT_INSPECTOR_PATHS_PER_ATTACHMENT]
        attachments.append(
            {
                "reference_id": item.reference_id,
                "kind": item.kind,
                "value": item.value,
                "status": item.status,
                "file_paths": list(paths),
                "omitted_file_path_count": max(0, len(item.file_paths) - len(paths)),
                "truncated": item.truncated,
                "note": item.note,
                "signature": item.signature,
            }
        )

    files = []
    for item in envelope.files[:file_limit]:
        preview_text = item.preview_text if include_preview_text else ""
        files.append(
            {
                "path": item.path,
                "size_bytes": item.size_bytes,
                "media_type": item.media_type,
                "content_sha256": item.content_sha256,
                "hash_status": item.hash_status,
                "preview_kind": item.preview_kind,
                "preview_text": preview_text,
                "preview_redacted": bool(item.preview_text) and not include_preview_text,
                "preview_bytes": item.preview_bytes,
                "preview_truncated": item.preview_truncated,
                "signature": item.signature,
            }
        )

    identity_material = {
        "schema_version": CONTEXT_INSPECTOR_SCHEMA_VERSION,
        "envelope_id": envelope.envelope_id,
        "envelope_signature": envelope.signature,
        "source_snapshot_hash": envelope.source_snapshot_hash,
        "route_id": envelope.route_id,
        "route_signature": envelope.route_signature,
        "budget_signature": envelope.budget.signature,
        "attachment_signatures": tuple(item.signature for item in envelope.attachments),
        "file_signatures": tuple(item.signature for item in envelope.files),
        "evidence_ids": envelope.evidence_ids,
        "constraints": envelope.constraints,
        "unresolved_reference_ids": envelope.unresolved_reference_ids,
        "total_preview_bytes": envelope.total_preview_bytes,
    }
    return {
        "schema_version": CONTEXT_INSPECTOR_SCHEMA_VERSION,
        "authoritative": False,
        "export_kind": "oiec-icpi-read-only-context-envelope",
        "notice": (
            "This inspector displays a bounded context projection. It cannot grant "
            "authority, approve evidence, lower risk, approve EON, or mutate files."
        ),
        "preview_notice": (
            "Preview bodies are redacted by default and exist only in the active "
            "in-memory envelope; GUI journal events retain identity metadata only."
        ),
        "inspector_signature": stable_hash(identity_material),
        "envelope_id": envelope.envelope_id,
        "envelope_signature": envelope.signature,
        "source_snapshot_hash": envelope.source_snapshot_hash,
        "route_id": envelope.route_id,
        "route_signature": envelope.route_signature,
        "objective": envelope.objective,
        "mode": envelope.mode,
        "original_request": envelope.original_request,
        "budget": asdict(envelope.budget),
        "attachments": attachments,
        "omitted_attachment_count": max(
            0,
            len(envelope.attachments) - len(attachments),
        ),
        "files": files,
        "omitted_file_count": max(0, len(envelope.files) - len(files)),
        "evidence_ids": list(envelope.evidence_ids),
        "constraints": list(envelope.constraints),
        "unresolved_reference_ids": list(envelope.unresolved_reference_ids),
        "total_preview_bytes": envelope.total_preview_bytes,
        "model_input_included": False,
        "preview_text_included": bool(include_preview_text),
    }


__all__ = [
    "CONTEXT_INSPECTOR_SCHEMA_VERSION",
    "MAX_CONTEXT_INSPECTOR_ATTACHMENTS",
    "MAX_CONTEXT_INSPECTOR_FILES",
    "MAX_CONTEXT_INSPECTOR_PATHS_PER_ATTACHMENT",
    "context_delta_audit_metadata",
    "context_delta_projection",
    "context_envelope_audit_metadata",
    "context_envelope_projection",
]
