from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Dict, Optional

from .authority import canonical_json
from .errors import PolicyError
from .models import RuntimeState, TransactionRecord
from .persistence import atomic_write_text
from .workspace import Workspace


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class TransactionManager:
    def __init__(self, workspace: Workspace, state_dir: Path, state: RuntimeState):
        self.workspace = workspace
        self.state_dir = state_dir
        self.state = state
        self.root = state_dir / "transactions"
        self.root.mkdir(parents=True, exist_ok=True)

    def prepare_write(self, path: str, content: str) -> TransactionRecord:
        canonical = self.workspace.canonical(path)
        target = self.workspace.resolve(canonical)
        original = target.read_bytes() if target.exists() else None
        candidate = content.encode("utf-8")
        return self._prepare(
            operation="write_file",
            candidates={canonical: candidate},
            originals={canonical: original},
        )

    def prepare_changes(self, changes: list[dict[str, object]]) -> TransactionRecord:
        if not changes:
            raise PolicyError("multi-file transaction requires at least one change")
        candidates: Dict[str, bytes] = {}
        originals: Dict[str, Optional[bytes]] = {}
        operations = []
        for change in changes:
            change_type = str(change.get("type", ""))
            canonical = self.workspace.canonical(str(change.get("path", "")))
            if canonical in candidates:
                raise PolicyError(f"duplicate transaction target: {canonical}")
            target = self.workspace.resolve(canonical)
            original_bytes = target.read_bytes() if target.exists() else None
            if change_type == "write":
                candidate = str(change.get("content", "")).encode("utf-8")
            elif change_type == "replace":
                if original_bytes is None:
                    raise PolicyError(f"replace target does not exist: {canonical}")
                original_text = original_bytes.decode("utf-8", errors="replace")
                old = str(change.get("old", ""))
                new = str(change.get("new", ""))
                count = int(change.get("count", 1))
                if not old or old not in original_text:
                    raise PolicyError(f"old text not found in {canonical}")
                candidate_text = (
                    original_text.replace(old, new)
                    if count < 0
                    else original_text.replace(old, new, count)
                )
                candidate = candidate_text.encode("utf-8")
            else:
                raise PolicyError(f"unsupported transaction change type: {change_type!r}")
            candidates[canonical] = candidate
            originals[canonical] = original_bytes
            operations.append(change_type)
        operation = operations[0] if len(set(operations)) == 1 else "multi_file"
        if len(candidates) > 1:
            operation = "multi_file"
        return self._prepare(operation=operation, candidates=candidates, originals=originals)

    def prepare_replace(
        self,
        path: str,
        old: str,
        new: str,
        count: int = 1,
    ) -> TransactionRecord:
        canonical = self.workspace.canonical(path)
        target = self.workspace.resolve(canonical)
        if not target.exists() or not target.is_file():
            raise PolicyError(f"replace target does not exist: {canonical}")
        original = target.read_text(encoding="utf-8", errors="replace")
        occurrences = original.count(old)
        if occurrences == 0:
            raise PolicyError("old text not found")
        candidate_text = original.replace(old, new) if count < 0 else original.replace(old, new, count)
        return self._prepare(
            operation="replace_text",
            candidates={canonical: candidate_text.encode("utf-8")},
            originals={canonical: target.read_bytes()},
        )

    def _prepare(
        self,
        *,
        operation: str,
        candidates: Dict[str, bytes],
        originals: Dict[str, Optional[bytes]],
    ) -> TransactionRecord:
        source_snapshot_hash = self.workspace.snapshot_hash()
        candidate_hashes = {path: sha256_bytes(content) for path, content in candidates.items()}
        candidate_hash = hashlib.sha256(
            canonical_json(candidate_hashes).encode("utf-8")
        ).hexdigest()
        transaction_material = {
            "operation": operation,
            "targets": sorted(candidates),
            "source_snapshot_hash": source_snapshot_hash,
            "candidate_hash": candidate_hash,
        }
        transaction_id = hashlib.sha256(
            canonical_json(transaction_material).encode("utf-8")
        ).hexdigest()
        transaction_dir = self.root / transaction_id
        candidate_dir = transaction_dir / "candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_files: Dict[str, str] = {}
        diff_parts = []
        for target, content in candidates.items():
            storage_name = hashlib.sha256(target.encode("utf-8")).hexdigest()
            stored = candidate_dir / storage_name
            stored.write_bytes(content)
            candidate_files[target] = stored.relative_to(self.state_dir).as_posix()
            before = (originals[target] or b"").decode("utf-8", errors="replace").splitlines(True)
            after = content.decode("utf-8", errors="replace").splitlines(True)
            diff_parts.extend(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{target}",
                    tofile=f"b/{target}",
                )
            )
        record = TransactionRecord(
            transaction_id=transaction_id,
            operation=operation,
            targets=sorted(candidates),
            source_snapshot_hash=source_snapshot_hash,
            candidate_hash=candidate_hash,
            candidate_files=candidate_files,
            original_hashes={
                path: sha256_bytes(content) if content is not None else None
                for path, content in originals.items()
            },
            diff="".join(diff_parts),
            authority_hash=self.state.authority.authority_hash,
        )
        self.state.transactions[transaction_id] = record
        atomic_write_text(
            transaction_dir / "transaction.json",
            json.dumps(record.__dict__, indent=2) + "\n",
        )
        return record

    def verify_candidate(self, record: TransactionRecord) -> None:
        observed = {}
        for target, stored_relative in record.candidate_files.items():
            stored = self.state_dir / stored_relative
            if not stored.exists():
                raise PolicyError(f"candidate artifact missing for {target}")
            observed[target] = sha256_bytes(stored.read_bytes())
        observed_hash = hashlib.sha256(canonical_json(observed).encode("utf-8")).hexdigest()
        if observed_hash != record.candidate_hash:
            raise PolicyError("candidate hash mismatch")

    def apply(self, record: TransactionRecord) -> TransactionRecord:
        if record.status != "PREPARED":
            raise PolicyError(f"transaction is not prepared: {record.status}")
        current_snapshot = self.workspace.snapshot_hash()
        if current_snapshot != record.source_snapshot_hash:
            raise PolicyError(
                "source drift blocks transaction apply: "
                f"expected {record.source_snapshot_hash}, observed {current_snapshot}"
            )
        self.verify_candidate(record)
        transaction_dir = self.root / record.transaction_id
        backup_dir = transaction_dir / "original"
        backup_dir.mkdir(parents=True, exist_ok=True)
        applied = []
        try:
            for target_name in record.targets:
                target = self.workspace.resolve(target_name)
                candidate = self.state_dir / record.candidate_files[target_name]
                metadata = {
                    "existed": target.exists(),
                    "mode": (target.stat().st_mode & 0o777) if target.exists() else None,
                    "sha256": self.workspace.file_hash_or_none(target_name),
                    "backup": "",
                }
                if target.exists():
                    backup_name = hashlib.sha256(target_name.encode("utf-8")).hexdigest()
                    backup_path = backup_dir / backup_name
                    shutil.copy2(target, backup_path)
                    metadata["backup"] = backup_path.relative_to(self.state_dir).as_posix()
                record.backup_manifest[target_name] = metadata
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{target.name}.ourd-", dir=target.parent
                )
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(candidate.read_bytes())
                        handle.flush()
                        os.fsync(handle.fileno())
                    if metadata["mode"] is not None:
                        os.chmod(temporary, int(metadata["mode"]))
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                applied.append(target_name)
                observed_hash = self.workspace.file_hash_or_none(target_name)
                expected_hash = sha256_bytes(candidate.read_bytes())
                if observed_hash != expected_hash:
                    raise PolicyError(f"post-write hash mismatch for {target_name}")
                record.applied_hashes[target_name] = observed_hash or ""
        except Exception:
            self._restore(record, applied_only=applied)
            raise
        record.applied_snapshot_hash = self.workspace.snapshot_hash()
        record.status = "APPLIED"
        atomic_write_text(
            transaction_dir / "transaction.json",
            json.dumps(record.__dict__, indent=2) + "\n",
        )
        return record

    def verify_applied(self, record: TransactionRecord) -> None:
        if record.status not in {"APPLIED", "VERIFIED"}:
            raise PolicyError(f"transaction is not applied: {record.status}")
        for target_name, expected_hash in record.applied_hashes.items():
            observed_hash = self.workspace.file_hash_or_none(target_name)
            if observed_hash != expected_hash:
                raise PolicyError(f"applied target hash mismatch for {target_name}")
        observed_snapshot = self.workspace.snapshot_hash()
        if record.applied_snapshot_hash and observed_snapshot != record.applied_snapshot_hash:
            raise PolicyError(
                "workspace changed after transaction apply; verification commands are blocked"
            )

    def finalize(self, record: TransactionRecord, evidence_ids: list[str]) -> TransactionRecord:
        if record.status != "APPLIED":
            raise PolicyError("only an applied transaction can be finalized")
        record.verification_evidence_ids = list(dict.fromkeys(evidence_ids))
        record.status = "VERIFIED"
        atomic_write_text(
            self.root / record.transaction_id / "transaction.json",
            json.dumps(record.__dict__, indent=2) + "\n",
        )
        return record

    def rollback(self, record: TransactionRecord) -> TransactionRecord:
        if record.status not in {"APPLIED", "VERIFIED"}:
            raise PolicyError(f"transaction cannot be rolled back from {record.status}")
        self._restore(record, applied_only=record.targets)
        record.status = "ROLLED_BACK"
        atomic_write_text(
            self.root / record.transaction_id / "transaction.json",
            json.dumps(record.__dict__, indent=2) + "\n",
        )
        return record

    def discard(self, record: TransactionRecord) -> TransactionRecord:
        if record.status != "PREPARED":
            raise PolicyError(f"only a prepared transaction can be discarded: {record.status}")
        record.status = "DISCARDED"
        atomic_write_text(
            self.root / record.transaction_id / "transaction.json",
            json.dumps(record.__dict__, indent=2) + "\n",
        )
        return record

    def _restore(self, record: TransactionRecord, applied_only: list[str]) -> None:
        for target_name in reversed(applied_only):
            target = self.workspace.resolve(target_name)
            metadata = record.backup_manifest.get(target_name, {})
            if metadata.get("existed"):
                backup = self.state_dir / str(metadata.get("backup"))
                if not backup.exists():
                    raise PolicyError(f"rollback backup missing for {target_name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                if metadata.get("mode") is not None:
                    os.chmod(target, int(metadata["mode"]))
            elif target.exists():
                target.unlink()
            expected = metadata.get("sha256")
            observed = self.workspace.file_hash_or_none(target_name)
            if expected != observed:
                raise PolicyError(f"rollback hash mismatch for {target_name}")
