from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .errors import PolicyError


DEFAULT_IGNORES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".ourd-agent",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
}


class Workspace:
    internal_name = ".ourd-agent"

    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(self.root)

    def canonical(self, relative: str, *, allow_internal: bool = False) -> str:
        if not isinstance(relative, str) or not relative.strip():
            raise PolicyError("path must be a non-empty string")
        if "\x00" in relative:
            raise PolicyError("path contains a NUL byte")
        requested = Path(relative)
        if requested.is_absolute():
            raise PolicyError(f"absolute path is not allowed: {relative}")
        resolved = (self.root / requested).resolve(strict=False)
        try:
            canonical = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise PolicyError(f"path escapes workspace: {relative}") from exc
        canonical = canonical or "."
        if not allow_internal and (
            canonical == self.internal_name
            or canonical.startswith(f"{self.internal_name}/")
        ):
            raise PolicyError("internal OURD agent state is not accessible to model tools")
        return canonical

    def resolve(self, relative: str, *, allow_internal: bool = False) -> Path:
        canonical = self.canonical(relative, allow_internal=allow_internal)
        return self.root if canonical == "." else self.root / canonical

    def rel(self, path: Path, *, allow_internal: bool = False) -> str:
        return self.canonical(
            path.resolve(strict=False).relative_to(self.root).as_posix(),
            allow_internal=allow_internal,
        )

    @staticmethod
    def matches(path: str, patterns: List[str]) -> bool:
        if not patterns:
            return False
        normalized = path.replace("\\", "/")
        for pattern in patterns:
            normalized_pattern = pattern.replace("\\", "/").strip()
            if normalized_pattern in {"*", "**", "."}:
                return True
            if fnmatch.fnmatchcase(normalized, normalized_pattern):
                return True
            if normalized_pattern.endswith("/**") and normalized == normalized_pattern[:-3].rstrip("/"):
                return True
            if normalized == normalized_pattern.rstrip("/"):
                return True
        return False

    def require_scope(
        self,
        relative: str,
        allowed_patterns: List[str],
        forbidden_patterns: Optional[List[str]] = None,
    ) -> str:
        canonical = self.canonical(relative)
        if not self.matches(canonical, allowed_patterns):
            raise PolicyError(
                f"{canonical!r} is outside allowed paths: {allowed_patterns!r}"
            )
        if forbidden_patterns and self.matches(canonical, forbidden_patterns):
            raise PolicyError(
                f"{canonical!r} intersects forbidden paths: {forbidden_patterns!r}"
            )
        return canonical

    def iter_files(self, relative: str = ".") -> Iterable[Path]:
        root = self.resolve(relative)
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file():
                continue
            try:
                relative_parts = path.resolve(strict=False).relative_to(self.root).parts
            except ValueError:
                continue
            if self.ignored_parts(relative_parts):
                continue
            yield path

    @staticmethod
    def ignored_parts(parts: Iterable[str]) -> bool:
        return any(part in DEFAULT_IGNORES or part.endswith(".egg-info") for part in parts)

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def file_hash_or_none(self, relative: str) -> Optional[str]:
        path = self.resolve(relative)
        return self.file_sha256(path) if path.exists() and path.is_file() else None

    def snapshot(self) -> Dict[str, str]:
        return {
            self.rel(path): self.file_sha256(path)
            for path in sorted(self.iter_files(), key=lambda value: self.rel(value))
        }

    def snapshot_hash(self) -> str:
        digest = hashlib.sha256()
        for path, file_hash in self.snapshot().items():
            mode = oct((self.root / path).stat().st_mode & 0o777)
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\0")
            digest.update(mode.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def safe_child_environment(self) -> Dict[str, str]:
        allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "HOME"}
        environment = {key: value for key, value in os.environ.items() if key in allowed}
        environment.setdefault("PATH", os.defpath)
        environment.setdefault("HOME", str(Path.home()))
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPYCACHEPREFIX"] = str(
            Path(environment.get("TMPDIR", "/tmp")) / "ourd-agent-pycache"
        )
        return environment
