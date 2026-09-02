from __future__ import annotations

import fnmatch
import json
import mimetypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .persistence import atomic_write_text
from .reasoning.models import stable_hash
from .workspace import Workspace


LineRange = Tuple[int, int]


def _canonical_ranges(ranges: Iterable[LineRange], line_count: int) -> Tuple[LineRange, ...]:
    bounded = sorted(
        (max(1, int(start)), min(line_count, int(end)))
        for start, end in ranges
        if line_count > 0 and int(end) >= 1 and int(start) <= line_count
    )
    merged: list[LineRange] = []
    for start, end in bounded:
        if start > end:
            continue
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return tuple(merged)


def _uncovered_ranges(covered: Sequence[LineRange], line_count: int) -> Tuple[LineRange, ...]:
    if line_count <= 0:
        return ()
    uncovered: list[LineRange] = []
    cursor = 1
    for start, end in covered:
        if cursor < start:
            uncovered.append((cursor, start - 1))
        cursor = end + 1
    if cursor <= line_count:
        uncovered.append((cursor, line_count))
    return tuple(uncovered)


@dataclass(frozen=True)
class CorpusFileRecord:
    path: str
    media_type: str
    byte_size: int
    line_count: int
    content_sha256: str


@dataclass(frozen=True)
class CorpusManifest:
    schema_version: int = 1
    manifest_id: str = ""
    root_path: str = "."
    include_patterns: Tuple[str, ...] = ("**/*.md", "*.md")
    exclude_patterns: Tuple[str, ...] = ()
    source_snapshot_hash: str = ""
    files: Tuple[CorpusFileRecord, ...] = ()
    manifest_signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("corpus manifest schema_version must be 1")
        files = tuple(sorted(self.files, key=lambda item: item.path))
        if len({item.path for item in files}) != len(files):
            raise ValueError("corpus manifest paths must be unique")
        object.__setattr__(self, "files", files)
        object.__setattr__(self, "include_patterns", tuple(sorted(set(self.include_patterns))))
        object.__setattr__(self, "exclude_patterns", tuple(sorted(set(self.exclude_patterns))))
        material = {
            "schema_version": self.schema_version,
            "root_path": self.root_path,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
            "source_snapshot_hash": self.source_snapshot_hash,
            "files": tuple(asdict(item) for item in files),
        }
        expected_id = f"corpus:{stable_hash(material)}"
        if self.manifest_id and self.manifest_id != expected_id:
            raise ValueError("corpus manifest ID mismatch")
        expected_signature = stable_hash({**material, "manifest_id": expected_id})
        if self.manifest_signature and self.manifest_signature != expected_signature:
            raise ValueError("corpus manifest signature mismatch")
        object.__setattr__(self, "manifest_id", expected_id)
        object.__setattr__(self, "manifest_signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CorpusManifest":
        values = dict(payload)
        values["files"] = tuple(CorpusFileRecord(**item) for item in values.get("files", ()))
        values["include_patterns"] = tuple(values.get("include_patterns", ()))
        values["exclude_patterns"] = tuple(values.get("exclude_patterns", ()))
        return cls(**values)


@dataclass(frozen=True)
class DocumentReadCoverage:
    path: str
    content_sha256: str
    line_count: int
    covered_line_ranges: Tuple[LineRange, ...] = ()
    uncovered_line_ranges: Tuple[LineRange, ...] = ()
    read_evidence_ids: Tuple[str, ...] = ()
    coverage_complete: bool = False
    coverage_signature: str = ""

    def __post_init__(self) -> None:
        covered = _canonical_ranges(self.covered_line_ranges, int(self.line_count))
        uncovered = _uncovered_ranges(covered, int(self.line_count))
        complete = not uncovered
        object.__setattr__(self, "covered_line_ranges", covered)
        object.__setattr__(self, "uncovered_line_ranges", uncovered)
        object.__setattr__(self, "read_evidence_ids", tuple(sorted(set(self.read_evidence_ids))))
        object.__setattr__(self, "coverage_complete", complete)
        material = {
            "path": self.path,
            "content_sha256": self.content_sha256,
            "line_count": int(self.line_count),
            "covered_line_ranges": covered,
            "uncovered_line_ranges": uncovered,
            "read_evidence_ids": self.read_evidence_ids,
            "coverage_complete": complete,
        }
        expected = stable_hash(material)
        if self.coverage_signature and self.coverage_signature != expected:
            raise ValueError("document read coverage signature mismatch")
        object.__setattr__(self, "coverage_signature", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DocumentReadCoverage":
        values = dict(payload)
        values["covered_line_ranges"] = tuple(tuple(item) for item in values.get("covered_line_ranges", ()))
        values["uncovered_line_ranges"] = tuple(tuple(item) for item in values.get("uncovered_line_ranges", ()))
        values["read_evidence_ids"] = tuple(values.get("read_evidence_ids", ()))
        return cls(**values)


@dataclass(frozen=True)
class DocumentSummaryArtifact:
    schema_version: int = 1
    summary_id: str = ""
    manifest_id: str = ""
    path: str = ""
    content_sha256: str = ""
    source_snapshot_hash: str = ""
    summary_text: str = ""
    summary_sha256: str = ""
    source_read_evidence_ids: Tuple[str, ...] = ()
    coverage_signature: str = ""
    coverage_complete: bool = False
    model_identity: str = ""
    prompt_signature: str = ""
    epistemic_status: str = "MODEL_SUMMARY_BOUND_TO_VERIFIED_SOURCE"
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("document summary schema_version must be 1")
        if not self.coverage_complete:
            raise ValueError("document summaries require complete source coverage")
        text = self.summary_text.strip()
        if not text:
            raise ValueError("document summary text must be non-empty")
        calculated_summary_hash = stable_hash(text)
        if self.summary_sha256 and self.summary_sha256 != calculated_summary_hash:
            raise ValueError("document summary hash mismatch")
        object.__setattr__(self, "summary_text", text)
        object.__setattr__(self, "summary_sha256", calculated_summary_hash)
        object.__setattr__(self, "source_read_evidence_ids", tuple(sorted(set(self.source_read_evidence_ids))))
        material = {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "path": self.path,
            "content_sha256": self.content_sha256,
            "source_snapshot_hash": self.source_snapshot_hash,
            "summary_sha256": calculated_summary_hash,
            "source_read_evidence_ids": self.source_read_evidence_ids,
            "coverage_signature": self.coverage_signature,
            "coverage_complete": True,
            "model_identity": self.model_identity,
            "prompt_signature": self.prompt_signature,
            "epistemic_status": self.epistemic_status,
        }
        expected_id = f"summary:{stable_hash(material)}"
        if self.summary_id and self.summary_id != expected_id:
            raise ValueError("document summary ID mismatch")
        expected_signature = stable_hash({**material, "summary_id": expected_id})
        if self.signature and self.signature != expected_signature:
            raise ValueError("document summary signature mismatch")
        object.__setattr__(self, "summary_id", expected_id)
        object.__setattr__(self, "signature", expected_signature)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DocumentSummaryArtifact":
        values = dict(payload)
        values["source_read_evidence_ids"] = tuple(values.get("source_read_evidence_ids", ()))
        return cls(**values)


@dataclass(frozen=True)
class CorpusSummaryReport:
    manifest_id: str
    expected_paths: Tuple[str, ...]
    summarized_paths: Tuple[str, ...]
    missing_paths: Tuple[str, ...]
    partial_paths: Tuple[str, ...]
    stale_paths: Tuple[str, ...]
    summary_ids: Tuple[str, ...]
    coverage_status: str
    source_snapshot_hash: str
    signature: str = ""

    def __post_init__(self) -> None:
        if self.coverage_status not in {"COMPLETE", "PARTIAL", "STALE"}:
            raise ValueError("invalid corpus coverage status")
        for name in (
            "expected_paths",
            "summarized_paths",
            "missing_paths",
            "partial_paths",
            "stale_paths",
            "summary_ids",
        ):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))
        material = {key: value for key, value in asdict(self).items() if key != "signature"}
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("corpus summary report signature mismatch")
        object.__setattr__(self, "signature", expected)


def build_corpus_manifest(
    workspace: Workspace,
    root_path: str,
    *,
    include_patterns: Sequence[str] = ("**/*.md", "*.md"),
    exclude_patterns: Sequence[str] = (),
    allowed_paths: Sequence[str] = ("**",),
    forbidden_paths: Sequence[str] = (),
) -> CorpusManifest:
    canonical_root = workspace.canonical(root_path)
    root = workspace.resolve(canonical_root)
    if not root.exists():
        raise FileNotFoundError(canonical_root)
    records: list[CorpusFileRecord] = []
    candidates = [root] if root.is_file() else workspace.iter_files(canonical_root)
    for path in candidates:
        canonical = workspace.rel(path)
        relative_to_root = path.name if root.is_file() else path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatchcase(relative_to_root, pattern) for pattern in include_patterns):
            continue
        if any(fnmatch.fnmatchcase(canonical, pattern) or fnmatch.fnmatchcase(relative_to_root, pattern) for pattern in exclude_patterns):
            continue
        if not workspace.matches(canonical, list(allowed_paths)):
            continue
        if forbidden_paths and workspace.matches(canonical, list(forbidden_paths)):
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        line_count = len(text.splitlines())
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        records.append(
            CorpusFileRecord(
                path=canonical,
                media_type=media_type,
                byte_size=len(raw),
                line_count=line_count,
                content_sha256=workspace.file_sha256(path),
            )
        )
    return CorpusManifest(
        root_path=canonical_root,
        include_patterns=tuple(include_patterns),
        exclude_patterns=tuple(exclude_patterns),
        source_snapshot_hash=workspace.snapshot_hash(),
        files=tuple(records),
    )


class SummaryArtifactStore:
    def __init__(self, state_dir: Path):
        self.root = state_dir / "summaries"
        self.manifest_dir = self.root / "manifests"
        self.coverage_dir = self.root / "coverage"
        self.artifact_dir = self.root / "artifacts"
        for directory in (self.manifest_dir, self.coverage_dir, self.artifact_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(value: str) -> str:
        return value.replace(":", "-")

    def _write(self, path: Path, payload: Mapping[str, Any]) -> None:
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def save_manifest(self, manifest: CorpusManifest) -> None:
        self._write(self.manifest_dir / f"{self._safe_id(manifest.manifest_id)}.json", asdict(manifest))

    def load_manifest(self, manifest_id: str) -> CorpusManifest:
        path = self.manifest_dir / f"{self._safe_id(manifest_id)}.json"
        return CorpusManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_coverage(self, manifest_id: str, coverage: DocumentReadCoverage) -> None:
        key = stable_hash({"manifest_id": manifest_id, "path": coverage.path})
        self._write(self.coverage_dir / f"{key}.json", {"manifest_id": manifest_id, **asdict(coverage)})

    def load_coverage(self, manifest_id: str, path: str) -> DocumentReadCoverage | None:
        key = stable_hash({"manifest_id": manifest_id, "path": path})
        target = self.coverage_dir / f"{key}.json"
        if not target.exists():
            return None
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload.pop("manifest_id", None)
        return DocumentReadCoverage.from_dict(payload)

    def save_summary(self, artifact: DocumentSummaryArtifact) -> None:
        self._write(self.artifact_dir / f"{self._safe_id(artifact.summary_id)}.json", asdict(artifact))

    def summaries_for_manifest(self, manifest_id: str) -> Tuple[DocumentSummaryArtifact, ...]:
        artifacts: list[DocumentSummaryArtifact] = []
        for path in sorted(self.artifact_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("manifest_id") == manifest_id:
                artifacts.append(DocumentSummaryArtifact.from_dict(payload))
        return tuple(artifacts)


def merge_coverage(
    prior: DocumentReadCoverage | None,
    *,
    path: str,
    content_sha256: str,
    line_count: int,
    covered_range: LineRange,
    evidence_id: str,
) -> DocumentReadCoverage:
    ranges = tuple(prior.covered_line_ranges if prior else ()) + (covered_range,)
    evidence_ids = tuple(prior.read_evidence_ids if prior else ()) + (evidence_id,)
    return DocumentReadCoverage(
        path=path,
        content_sha256=content_sha256,
        line_count=line_count,
        covered_line_ranges=ranges,
        read_evidence_ids=evidence_ids,
    )


def build_corpus_summary_report(
    manifest: CorpusManifest,
    summaries: Sequence[DocumentSummaryArtifact],
    coverages: Mapping[str, DocumentReadCoverage | None],
    *,
    current_snapshot_hash: str,
) -> CorpusSummaryReport:
    expected = {item.path for item in manifest.files}
    valid_summaries = {
        item.path: item
        for item in summaries
        if item.content_sha256 == next((record.content_sha256 for record in manifest.files if record.path == item.path), "")
    }
    summarized = set(valid_summaries)
    missing = expected - summarized
    partial = {
        path
        for path in expected
        if coverages.get(path) is not None and not coverages[path].coverage_complete
    }
    stale = set()
    if manifest.source_snapshot_hash != current_snapshot_hash:
        stale = set(expected)
    if stale:
        status = "STALE"
    elif summarized == expected and not partial:
        status = "COMPLETE"
    else:
        status = "PARTIAL"
    return CorpusSummaryReport(
        manifest_id=manifest.manifest_id,
        expected_paths=tuple(expected),
        summarized_paths=tuple(summarized),
        missing_paths=tuple(missing),
        partial_paths=tuple(partial),
        stale_paths=tuple(stale),
        summary_ids=tuple(item.summary_id for item in valid_summaries.values()),
        coverage_status=status,
        source_snapshot_hash=manifest.source_snapshot_hash,
    )


__all__ = [
    "CorpusFileRecord",
    "CorpusManifest",
    "CorpusSummaryReport",
    "DocumentReadCoverage",
    "DocumentSummaryArtifact",
    "SummaryArtifactStore",
    "build_corpus_manifest",
    "build_corpus_summary_report",
    "merge_coverage",
]
