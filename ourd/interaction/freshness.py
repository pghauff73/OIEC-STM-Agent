from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from ..errors import PolicyError
from ..reasoning.models import stable_hash
from .envelope import ContextFileProjection, InteractionContextEnvelope
from .pinned import PinnedContextSet


CONTEXT_FILE_DELTA_STATUSES = {
    "unchanged",
    "changed",
    "missing",
    "new",
    "indeterminate",
}
MAX_CONTEXT_DELTA_FILES = 256


@dataclass(frozen=True)
class ContextFileDelta:
    schema_version: int = 1
    path: str = ""
    status: str = "indeterminate"
    previous_size_bytes: int = -1
    current_size_bytes: int = -1
    previous_content_sha256: str = ""
    current_content_sha256: str = ""
    previous_hash_status: str = "absent"
    current_hash_status: str = "absent"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context file delta schema_version must be 1")
        path = self.path.strip()
        status = self.status.strip().casefold()
        if not path:
            raise ValueError("context file delta path must be non-empty")
        if status not in CONTEXT_FILE_DELTA_STATUSES:
            raise ValueError(f"invalid context file delta status: {self.status}")
        previous_size = int(self.previous_size_bytes)
        current_size = int(self.current_size_bytes)
        if previous_size < -1 or current_size < -1:
            raise ValueError("context file delta sizes must be -1 or greater")
        material = {
            "schema_version": self.schema_version,
            "path": path,
            "status": status,
            "previous_size_bytes": previous_size,
            "current_size_bytes": current_size,
            "previous_content_sha256": self.previous_content_sha256,
            "current_content_sha256": self.current_content_sha256,
            "previous_hash_status": self.previous_hash_status,
            "current_hash_status": self.current_hash_status,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context file delta signature mismatch")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "previous_size_bytes", previous_size)
        object.__setattr__(self, "current_size_bytes", current_size)
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextFileDelta":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ContextDelta:
    schema_version: int = 1
    baseline_envelope_id: str = ""
    baseline_envelope_signature: str = ""
    baseline_source_snapshot_hash: str = ""
    observed_envelope_id: str = ""
    observed_envelope_signature: str = ""
    observed_source_snapshot_hash: str = ""
    freshness: str = "STALE"
    refresh_applied: bool = False
    workspace_snapshot_changed: bool = False
    files: Tuple[ContextFileDelta, ...] = ()
    unchanged_count: int = 0
    changed_count: int = 0
    missing_count: int = 0
    new_count: int = 0
    indeterminate_count: int = 0
    authoritative: bool = False
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("context delta schema_version must be 1")
        if self.authoritative:
            raise ValueError("context delta cannot be authoritative")
        freshness = self.freshness.strip().upper()
        if freshness not in {"FRESH", "STALE"}:
            raise ValueError(f"invalid context freshness: {self.freshness}")
        for name in (
            "baseline_envelope_id",
            "baseline_envelope_signature",
            "observed_envelope_id",
            "observed_envelope_signature",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"context delta requires {name}")
        for name in (
            "baseline_source_snapshot_hash",
            "observed_source_snapshot_hash",
        ):
            if len(str(getattr(self, name))) != 64:
                raise ValueError(f"context delta requires a SHA-256 {name}")
        files = tuple(sorted(self.files, key=lambda item: item.path))
        if len(files) > MAX_CONTEXT_DELTA_FILES:
            raise ValueError(
                f"context delta exceeds {MAX_CONTEXT_DELTA_FILES} files"
            )
        if len({item.path for item in files}) != len(files):
            raise ValueError("context delta file paths must be unique")
        counts = {
            status: sum(item.status == status for item in files)
            for status in CONTEXT_FILE_DELTA_STATUSES
        }
        expected_counts = {
            "unchanged_count": counts["unchanged"],
            "changed_count": counts["changed"],
            "missing_count": counts["missing"],
            "new_count": counts["new"],
            "indeterminate_count": counts["indeterminate"],
        }
        for name, value in expected_counts.items():
            supplied = int(getattr(self, name))
            if supplied != value:
                raise ValueError(f"context delta {name} mismatch")
        snapshot_changed = (
            self.baseline_source_snapshot_hash != self.observed_source_snapshot_hash
        )
        if bool(self.workspace_snapshot_changed) != snapshot_changed:
            raise ValueError("context delta workspace snapshot change mismatch")
        exact_match = (
            not snapshot_changed
            and self.baseline_envelope_signature == self.observed_envelope_signature
        )
        if bool(self.refresh_applied) and freshness != "FRESH":
            raise ValueError("applied context refresh must produce FRESH state")
        if not self.refresh_applied and (freshness == "FRESH") != exact_match:
            raise ValueError("context delta freshness does not match envelope identity")
        object.__setattr__(self, "freshness", freshness)
        object.__setattr__(self, "files", files)
        material = {
            "schema_version": self.schema_version,
            "baseline_envelope_id": self.baseline_envelope_id,
            "baseline_envelope_signature": self.baseline_envelope_signature,
            "baseline_source_snapshot_hash": self.baseline_source_snapshot_hash,
            "observed_envelope_id": self.observed_envelope_id,
            "observed_envelope_signature": self.observed_envelope_signature,
            "observed_source_snapshot_hash": self.observed_source_snapshot_hash,
            "freshness": freshness,
            "refresh_applied": bool(self.refresh_applied),
            "workspace_snapshot_changed": bool(self.workspace_snapshot_changed),
            "files": tuple(item.__dict__ for item in files),
            **expected_counts,
            "authoritative": False,
        }
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("context delta signature mismatch")
        object.__setattr__(self, "signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextDelta":
        values = dict(payload)
        values["files"] = tuple(
            item if isinstance(item, ContextFileDelta) else ContextFileDelta.from_dict(item)
            for item in values.get("files", ())
        )
        return cls(**values)


def _classify_file_delta(
    previous: ContextFileProjection | None,
    current: ContextFileProjection | None,
) -> str:
    if previous is None:
        return "new"
    if current is None:
        return "missing"
    if previous.signature == current.signature:
        return "unchanged"
    if previous.size_bytes != current.size_bytes or previous.media_type != current.media_type:
        return "changed"
    if previous.hash_status == current.hash_status == "exact":
        return (
            "unchanged"
            if previous.content_sha256 == current.content_sha256
            else "changed"
        )
    return "indeterminate"


def compare_context_envelopes(
    baseline: InteractionContextEnvelope,
    observed: InteractionContextEnvelope,
    *,
    refresh_applied: bool = False,
) -> ContextDelta:
    baseline_files = {item.path: item for item in baseline.files}
    observed_files = {item.path: item for item in observed.files}
    file_deltas = []
    for path in sorted(set(baseline_files) | set(observed_files)):
        previous = baseline_files.get(path)
        current = observed_files.get(path)
        file_deltas.append(
            ContextFileDelta(
                path=path,
                status=_classify_file_delta(previous, current),
                previous_size_bytes=previous.size_bytes if previous is not None else -1,
                current_size_bytes=current.size_bytes if current is not None else -1,
                previous_content_sha256=(
                    previous.content_sha256 if previous is not None else ""
                ),
                current_content_sha256=(
                    current.content_sha256 if current is not None else ""
                ),
                previous_hash_status=(
                    previous.hash_status if previous is not None else "absent"
                ),
                current_hash_status=(
                    current.hash_status if current is not None else "absent"
                ),
            )
        )
    exact_match = (
        baseline.source_snapshot_hash == observed.source_snapshot_hash
        and baseline.signature == observed.signature
    )
    file_delta_tuple = tuple(file_deltas)
    counts = {
        status: sum(item.status == status for item in file_delta_tuple)
        for status in CONTEXT_FILE_DELTA_STATUSES
    }
    return ContextDelta(
        baseline_envelope_id=baseline.envelope_id,
        baseline_envelope_signature=baseline.signature,
        baseline_source_snapshot_hash=baseline.source_snapshot_hash,
        observed_envelope_id=observed.envelope_id,
        observed_envelope_signature=observed.signature,
        observed_source_snapshot_hash=observed.source_snapshot_hash,
        freshness="FRESH" if refresh_applied or exact_match else "STALE",
        refresh_applied=refresh_applied,
        workspace_snapshot_changed=(
            baseline.source_snapshot_hash != observed.source_snapshot_hash
        ),
        files=file_delta_tuple,
        unchanged_count=counts["unchanged"],
        changed_count=counts["changed"],
        missing_count=counts["missing"],
        new_count=counts["new"],
        indeterminate_count=counts["indeterminate"],
    )


def require_fresh_pinned_context(
    pinned_context: PinnedContextSet,
    envelope: InteractionContextEnvelope | None,
    *,
    current_source_snapshot_hash: str,
) -> None:
    freshness = pinned_context_freshness(
        pinned_context,
        envelope,
        current_source_snapshot_hash=current_source_snapshot_hash,
    )
    if freshness == "EMPTY":
        return
    if freshness == "UNBOUND":
        raise PolicyError(
            "pinned context has no bound draft envelope; use /context --refresh"
        )
    if freshness == "STALE":
        raise PolicyError(
            "pinned context is stale for the current workspace snapshot; "
            "use /context to inspect the delta and /context --refresh to accept it"
        )
    assert envelope is not None
    projected_paths = {
        item.value
        for item in envelope.attachments
        if item.kind in {"file", "folder", "path"}
    }
    missing_paths = set(pinned_context.paths) - projected_paths
    if missing_paths:
        raise PolicyError(
            f"pinned draft envelope omits paths: {sorted(missing_paths)!r}"
        )


def pinned_context_freshness(
    pinned_context: PinnedContextSet,
    envelope: InteractionContextEnvelope | None,
    *,
    current_source_snapshot_hash: str,
) -> str:
    if not pinned_context.paths:
        return "EMPTY"
    if envelope is None:
        return "UNBOUND"
    if envelope.source_snapshot_hash == current_source_snapshot_hash:
        return "FRESH"
    return "STALE"


def render_context_delta(delta: ContextDelta) -> str:
    changed = delta.changed_count + delta.missing_count + delta.new_count
    return (
        f"Context freshness: {delta.freshness}\n"
        f"Baseline snapshot: {delta.baseline_source_snapshot_hash}\n"
        f"Observed snapshot: {delta.observed_source_snapshot_hash}\n"
        f"Files: {len(delta.files)} total, {delta.unchanged_count} unchanged, "
        f"{delta.changed_count} changed, {delta.missing_count} missing, "
        f"{delta.new_count} new, {delta.indeterminate_count} indeterminate\n"
        f"Refresh applied: {'yes' if delta.refresh_applied else 'no'}\n"
        f"Material file deltas: {changed}"
    )


__all__ = [
    "CONTEXT_FILE_DELTA_STATUSES",
    "ContextDelta",
    "ContextFileDelta",
    "MAX_CONTEXT_DELTA_FILES",
    "compare_context_envelopes",
    "pinned_context_freshness",
    "render_context_delta",
    "require_fresh_pinned_context",
]
