from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable

from .errors import EGCFError


class SimulationEngine:
    @staticmethod
    def _tree_hash(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            if relative.startswith(".ourd-agent/"):
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def worktree(self, root: Path, changes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        source = root.resolve()
        before_hash = self._tree_hash(source)
        with tempfile.TemporaryDirectory(prefix="egcf-worktree-") as temporary:
            clone = Path(temporary) / "repo"
            shutil.copytree(
                source,
                clone,
                symlinks=False,
                ignore=shutil.ignore_patterns(".ourd-agent", "__pycache__", "*.pyc"),
            )
            applied = []
            for raw in changes:
                change = dict(raw)
                operation = str(change.get("type", change.get("operation", "")))
                relative = Path(str(change.get("path", "")))
                if not relative.as_posix() or relative.is_absolute() or ".." in relative.parts:
                    raise EGCFError("worktree simulation change path must remain relative")
                target = clone / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if operation == "write":
                    target.write_text(str(change.get("content", "")), encoding="utf-8")
                elif operation == "replace":
                    if not target.is_file():
                        raise EGCFError(f"worktree replace target does not exist: {relative}")
                    original = target.read_text(encoding="utf-8")
                    old = str(change.get("old", ""))
                    if old not in original:
                        raise EGCFError(f"worktree replace text not found: {relative}")
                    count = int(change.get("count", 1))
                    updated = original.replace(old, str(change.get("new", "")), count)
                    target.write_text(updated, encoding="utf-8")
                else:
                    raise EGCFError(f"unsupported worktree simulation operation: {operation}")
                applied.append({**change, "path": relative.as_posix(), "type": operation})
            after_hash = self._tree_hash(clone)
            changed_paths = sorted({item["path"] for item in applied})
        return {
            "simulated": True,
            "source_tree_hash": before_hash,
            "simulated_tree_hash": after_hash,
            "changed": before_hash != after_hash,
            "changed_paths": changed_paths,
            "operations": applied,
            "disposed": True,
            "fidelity_limits": [
                "filesystem-only disposable copy",
                "no repository-native commands executed",
                "symlink semantics are not preserved",
            ],
        }

    def migration(self, before: Dict[str, Any], operations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        state = copy.deepcopy(before)
        rollback: list[Dict[str, Any]] = []
        applied: list[Dict[str, Any]] = []
        for operation in operations:
            kind = operation.get("operation")
            key = operation.get("key")
            if not isinstance(key, str) or not key:
                raise EGCFError("migration operations require a non-empty key")
            if kind == "add":
                if key in state:
                    raise EGCFError(f"migration add target already exists: {key}")
                state[key] = copy.deepcopy(operation.get("value"))
                rollback.insert(0, {"operation": "remove", "key": key})
            elif kind == "remove":
                if key not in state:
                    raise EGCFError(f"migration remove target does not exist: {key}")
                previous = state.pop(key)
                rollback.insert(0, {"operation": "add", "key": key, "value": previous})
            elif kind == "set":
                existed = key in state
                previous = copy.deepcopy(state.get(key))
                state[key] = copy.deepcopy(operation.get("value"))
                rollback.insert(
                    0,
                    {"operation": "set", "key": key, "value": previous}
                    if existed
                    else {"operation": "remove", "key": key},
                )
            elif kind == "rename":
                target = operation.get("target")
                if key not in state or not isinstance(target, str) or not target or target in state:
                    raise EGCFError("migration rename requires existing source and unused target")
                state[target] = state.pop(key)
                rollback.insert(0, {"operation": "rename", "key": target, "target": key})
            else:
                raise EGCFError(f"unsupported migration operation: {kind}")
            applied.append(dict(operation))
        changed = sorted(set(before).union(state))
        diff = {
            key: {"before": before.get(key), "after": state.get(key)}
            for key in changed
            if before.get(key) != state.get(key) or (key in before) != (key in state)
        }
        return {
            "simulated": True,
            "before": before,
            "after": state,
            "operations": applied,
            "rollback_operations": rollback,
            "diff": diff,
            "fidelity_limits": ["dictionary-state migration model", "no external side effects"],
        }

    @staticmethod
    def rollback(simulation: Dict[str, Any]) -> Dict[str, Any]:
        engine = SimulationEngine()
        result = engine.migration(simulation["after"], simulation["rollback_operations"])
        return {
            "simulated": True,
            "restored": result["after"] == simulation["before"],
            "expected": simulation["before"],
            "observed": result["after"],
        }
