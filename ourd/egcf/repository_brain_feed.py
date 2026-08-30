from __future__ import annotations

import ast
import fnmatch
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .algebra.brain_feed import MAX_BRAIN_FEED_ITEMS, BrainFeedItem, make_brain_feed_item
from .errors import EGCFError
from .ids import sha256_json


REPOSITORY_BRAIN_FEED_VERSION = "saa-repository-brain-feed-v1"

DEFAULT_IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".ourd-agent",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "out",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
}

LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "Python": (".py", ".pyi"),
    "JavaScript": (".js", ".jsx", ".mjs", ".cjs"),
    "TypeScript": (".ts", ".tsx"),
    "C": (".c", ".h"),
    "C++": (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"),
    "C#": (".cs",),
    "Java": (".java",),
    "Kotlin": (".kt", ".kts"),
    "Go": (".go",),
    "Rust": (".rs",),
    "Swift": (".swift",),
    "Ruby": (".rb",),
    "PHP": (".php",),
    "Shell": (".sh", ".bash", ".zsh"),
    "R": (".r", ".R"),
    "MATLAB": (".m",),
    "Fortran": (".f", ".f90", ".f95", ".f03", ".f08"),
    "Julia": (".jl",),
    "Lua": (".lua",),
    "Perl": (".pl", ".pm"),
    "SQL": (".sql",),
}

_EXTENSION_TO_LANGUAGE = {
    extension.casefold(): language
    for language, extensions in LANGUAGE_EXTENSIONS.items()
    for extension in extensions
}

DOCUMENT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc", ".tex"}
SPECIAL_TEXT_FILES = {
    "README",
    "README.md",
    "README.rst",
    "LICENSE",
    "CHANGELOG",
    "CHANGELOG.md",
    "Makefile",
    "Dockerfile",
    "CMakeLists.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}

_GENERIC_SYMBOL_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "JavaScript": (
        re.compile(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"),
        re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"),
        re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>"),
    ),
    "TypeScript": (
        re.compile(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"),
        re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"),
    ),
    "Go": (
        re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)"),
    ),
    "Rust": (
        re.compile(r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)"),
    ),
    "Ruby": (
        re.compile(r"^\s*def\s+([A-Za-z_]\w*[!?=]?)\s*(?:\(([^)]*)\)|\s*([^#]*))?"),
    ),
    "PHP": (
        re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)"),
    ),
    "Shell": (
        re.compile(r"^\s*([A-Za-z_]\w*)\s*\(\s*\)\s*\{"),
        re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*(?:\(\s*\))?\s*\{"),
    ),
    "R": (
        re.compile(r"^\s*([A-Za-z_.][\w.]*)\s*<-\s*function\s*\(([^)]*)\)"),
    ),
    "MATLAB": (
        re.compile(r"^\s*function\s+(?:\[[^]]*\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)"),
    ),
    "Fortran": (
        re.compile(r"^\s*(?:recursive\s+|pure\s+|elemental\s+)?(?:subroutine|function)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.IGNORECASE),
    ),
    "Julia": (
        re.compile(r"^\s*function\s+([A-Za-z_]\w*[!?]?)\s*\(([^)]*)\)"),
        re.compile(r"^\s*([A-Za-z_]\w*[!?]?)\s*\(([^)]*)\)\s*="),
    ),
    "Lua": (
        re.compile(r"^\s*(?:local\s+)?function\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\(([^)]*)\)"),
    ),
    "Perl": (
        re.compile(r"^\s*sub\s+([A-Za-z_]\w*)\b"),
    ),
}

_C_FAMILY_PATTERN = re.compile(
    r"^\s*(?:(?:public|private|protected|static|virtual|inline|extern|constexpr|async|final|synchronized|native|abstract|override|sealed|unsafe)\s+)*"
    r"(?:[A-Za-z_][\w:<>,.?\[\]*&]+\s+)+([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*(?:const\s*)?(?:noexcept\s*)?(?:throws\s+[^\{]+)?\{"
)

_CONTROL_WORDS = {"if", "for", "while", "switch", "catch", "sizeof", "return", "new", "delete"}


@dataclass(frozen=True)
class RepositoryScanPolicy:
    max_files: int = 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024
    max_symbols: int = 8192
    max_items_per_batch: int = MAX_BRAIN_FEED_ITEMS
    include_tests: bool = True
    include_docs: bool = True
    include_unknown_text: bool = True
    include_invariants: bool = True
    include_globs: tuple[str, ...] = ()
    exclude_globs: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()

    def canonical(self) -> "RepositoryScanPolicy":
        if self.max_files < 1 or self.max_files > 100000:
            raise EGCFError("repository brain-feed max_files must be in 1..100000")
        if self.max_total_bytes < 1 or self.max_total_bytes > 8 * 1024 * 1024 * 1024:
            raise EGCFError("repository brain-feed max_total_bytes outside bounded range")
        if self.max_file_bytes < 1 or self.max_file_bytes > 128 * 1024 * 1024:
            raise EGCFError("repository brain-feed max_file_bytes outside bounded range")
        if self.max_symbols < 0 or self.max_symbols > 250000:
            raise EGCFError("repository brain-feed max_symbols must be in 0..250000")
        if self.max_items_per_batch < 2 or self.max_items_per_batch > MAX_BRAIN_FEED_ITEMS:
            raise EGCFError(
                f"repository brain-feed max_items_per_batch must be in 2..{MAX_BRAIN_FEED_ITEMS}"
            )
        known = {name.casefold(): name for name in LANGUAGE_EXTENSIONS}
        canonical_languages: list[str] = []
        for language in self.languages:
            key = str(language).strip().casefold()
            if key not in known:
                raise EGCFError(f"unknown repository brain-feed language filter: {language}")
            canonical_languages.append(known[key])
        return RepositoryScanPolicy(
            max_files=int(self.max_files),
            max_total_bytes=int(self.max_total_bytes),
            max_file_bytes=int(self.max_file_bytes),
            max_symbols=int(self.max_symbols),
            max_items_per_batch=int(self.max_items_per_batch),
            include_tests=bool(self.include_tests),
            include_docs=bool(self.include_docs),
            include_unknown_text=bool(self.include_unknown_text),
            include_invariants=bool(self.include_invariants),
            include_globs=tuple(sorted({str(value).strip() for value in self.include_globs if str(value).strip()})),
            exclude_globs=tuple(sorted({str(value).strip() for value in self.exclude_globs if str(value).strip()})),
            languages=tuple(sorted(set(canonical_languages))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_files": self.max_files,
            "max_total_bytes": self.max_total_bytes,
            "max_file_bytes": self.max_file_bytes,
            "max_symbols": self.max_symbols,
            "max_items_per_batch": self.max_items_per_batch,
            "include_tests": self.include_tests,
            "include_docs": self.include_docs,
            "include_unknown_text": self.include_unknown_text,
            "include_invariants": self.include_invariants,
            "include_globs": list(self.include_globs),
            "exclude_globs": list(self.exclude_globs),
            "languages": list(self.languages),
        }


@dataclass(frozen=True)
class RepositorySourceFile:
    relative_path: str
    language: str
    category: str
    size_bytes: int
    sha256: str
    text: str
    is_test: bool
    is_document: bool

    def identity(self) -> dict[str, Any]:
        return {
            "path": self.relative_path,
            "language": self.language,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "is_test": self.is_test,
            "is_document": self.is_document,
        }


@dataclass(frozen=True)
class RepositorySymbol:
    name: str
    qualified_name: str
    symbol_kind: str
    language: str
    relative_path: str
    line_start: int
    line_end: int
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    documentation: str
    annotations: tuple[str, ...]
    calls: tuple[str, ...]
    semantic_clues: tuple[str, ...]
    extraction_mode: str
    symbol_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "symbol_kind": self.symbol_kind,
            "language": self.language,
            "relative_path": self.relative_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "documentation": self.documentation,
            "annotations": list(self.annotations),
            "calls": list(self.calls),
            "semantic_clues": list(self.semantic_clues),
            "extraction_mode": self.extraction_mode,
            "symbol_sha256": self.symbol_sha256,
        }


@dataclass(frozen=True)
class RepositoryBrainFeedPlan:
    source_root: str
    repository_name: str
    repository_signature: str
    git_commit: str
    git_branch: str
    files: tuple[RepositorySourceFile, ...]
    symbols: tuple[RepositorySymbol, ...]
    file_groups: tuple[tuple[BrainFeedItem, ...], ...]
    summary_item: BrainFeedItem
    skipped: tuple[dict[str, str], ...]
    language_counts: tuple[tuple[str, int], ...]
    total_bytes: int
    policy: RepositoryScanPolicy

    @property
    def item_count(self) -> int:
        return 1 + sum(len(group) for group in self.file_groups)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "version": REPOSITORY_BRAIN_FEED_VERSION,
            "source_root": self.source_root,
            "repository_name": self.repository_name,
            "repository_signature": self.repository_signature,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "file_count": len(self.files),
            "symbol_count": len(self.symbols),
            "item_count": self.item_count,
            "total_bytes": self.total_bytes,
            "language_counts": {key: value for key, value in self.language_counts},
            "skipped_count": len(self.skipped),
            "skipped": list(self.skipped),
            "policy": self.policy.to_dict(),
            "safety": {
                "static_read_only": True,
                "code_executed": False,
                "code_imported": False,
                "tests_executed": False,
                "canonical_algorithm_admissions": 0,
            },
        }


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_probably_text(content: bytes) -> bool:
    if b"\x00" in content[:8192]:
        return False
    if not content:
        return True
    sample = content[:8192]
    control = sum(byte < 9 or (13 < byte < 32) for byte in sample)
    return control / max(1, len(sample)) < 0.08


def _language_for_path(path: Path) -> str:
    name = path.name
    if name == "Makefile":
        return "Make"
    if name == "Dockerfile":
        return "Dockerfile"
    return _EXTENSION_TO_LANGUAGE.get(path.suffix.casefold(), "")


def _is_document_path(path: Path) -> bool:
    return path.suffix.casefold() in DOCUMENT_EXTENSIONS or path.name in SPECIAL_TEXT_FILES


def _is_test_path(relative_path: str) -> bool:
    parts = [part.casefold() for part in Path(relative_path).parts]
    name = Path(relative_path).name.casefold()
    return (
        any(part in {"test", "tests", "spec", "specs", "testing"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name.endswith("_test.go")
        or name.endswith("test.rs")
    )


def _path_allowed(relative_path: str, policy: RepositoryScanPolicy) -> bool:
    normalized = relative_path.replace(os.sep, "/")
    if policy.include_globs and not any(fnmatch.fnmatch(normalized, pattern) for pattern in policy.include_globs):
        return False
    if any(fnmatch.fnmatch(normalized, pattern) for pattern in policy.exclude_globs):
        return False
    return True


def _git_value(source_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _read_repository_files(source_root: Path, policy: RepositoryScanPolicy) -> tuple[list[RepositorySourceFile], list[dict[str, str]], int]:
    files: list[RepositorySourceFile] = []
    skipped: list[dict[str, str]] = []
    total_bytes = 0
    allowed_languages = set(policy.languages)

    for current_root, directory_names, file_names in os.walk(source_root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in DEFAULT_IGNORED_DIRECTORIES and not (Path(current_root) / name).is_symlink()
        )
        for file_name in sorted(file_names):
            path = Path(current_root) / file_name
            if path.is_symlink():
                skipped.append({"path": str(path.relative_to(source_root)), "reason": "SYMLINK_SKIPPED"})
                continue
            relative = str(path.relative_to(source_root)).replace(os.sep, "/")
            if not _path_allowed(relative, policy):
                continue
            language = _language_for_path(path)
            is_document = _is_document_path(path)
            is_test = _is_test_path(relative)
            if language and allowed_languages and language not in allowed_languages:
                continue
            if is_test and not policy.include_tests:
                continue
            if is_document and not policy.include_docs and not language:
                continue
            if not language and not is_document and not policy.include_unknown_text:
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped.append({"path": relative, "reason": f"STAT_FAILED:{type(exc).__name__}"})
                continue
            if size > policy.max_file_bytes:
                skipped.append({"path": relative, "reason": "FILE_SIZE_LIMIT"})
                continue
            if len(files) >= policy.max_files:
                skipped.append({"path": relative, "reason": "FILE_COUNT_LIMIT"})
                continue
            if total_bytes + size > policy.max_total_bytes:
                skipped.append({"path": relative, "reason": "TOTAL_BYTE_LIMIT"})
                continue
            try:
                content = path.read_bytes()
            except OSError as exc:
                skipped.append({"path": relative, "reason": f"READ_FAILED:{type(exc).__name__}"})
                continue
            if not _is_probably_text(content):
                skipped.append({"path": relative, "reason": "BINARY_FILE"})
                continue
            text = content.decode("utf-8", errors="replace")
            category = "source-code" if language else ("documentation" if is_document else "text-source")
            files.append(
                RepositorySourceFile(
                    relative_path=relative,
                    language=language or "Text",
                    category=category,
                    size_bytes=len(content),
                    sha256=_sha256_bytes(content),
                    text=text,
                    is_test=is_test,
                    is_document=is_document,
                )
            )
            total_bytes += len(content)
    return files, skipped, total_bytes


def _identifier_words(value: str) -> tuple[str, ...]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value.replace("_", " ").replace("-", " "))
    words = [word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", separated)]
    stop = {"self", "cls", "get", "set", "do", "run", "make", "build", "new", "impl", "func", "function"}
    return tuple(sorted({word for word in words if word not in stop and len(word) > 1}))


def _semantic_clues(name: str, parameters: Sequence[str], documentation: str, annotations: Sequence[str]) -> tuple[str, ...]:
    clues: set[str] = set()
    for value in (name, *parameters, *annotations):
        clues.update(_identifier_words(value))
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", documentation[:800]):
        clues.update(_identifier_words(word))
    return tuple(sorted(clues))[:64]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _annotation(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _python_symbol_source(text: str, node: ast.AST) -> str:
    lines = text.splitlines()
    start = max(1, int(getattr(node, "lineno", 1)))
    end = max(start, int(getattr(node, "end_lineno", start)))
    return "\n".join(lines[start - 1 : end])


def _python_symbols(file: RepositorySourceFile) -> tuple[list[RepositorySymbol], list[tuple[str, int]] , list[str]]:
    symbols: list[RepositorySymbol] = []
    assertions: list[tuple[str, int]] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(file.text, filename=file.relative_path)
    except SyntaxError as exc:
        warnings.append(f"PYTHON_PARSE_ERROR:{file.relative_path}:{exc.lineno or 0}")
        return symbols, assertions, warnings

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified = ".".join([*self.scope, node.name]) if self.scope else node.name
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            parameters = [item.arg for item in args]
            if node.args.vararg:
                parameters.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                parameters.append("**" + node.args.kwarg.arg)
            annotations = [
                f"{item.arg}:{_annotation(item.annotation)}"
                for item in args
                if item.annotation is not None
            ]
            return_annotation = _annotation(node.returns)
            if return_annotation:
                annotations.append("return:" + return_annotation)
            documentation = ast.get_docstring(node, clean=True) or ""
            calls = sorted(
                {
                    name
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    for name in [_call_name(child.func)]
                    if name
                }
            )
            has_value_return = any(
                isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node)
            )
            has_yield = any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))
            outputs: list[str] = []
            if return_annotation:
                outputs.append(return_annotation)
            elif has_value_return:
                outputs.append("return_value")
            if has_yield:
                outputs.append("yielded_value")
            symbol_text = _python_symbol_source(file.text, node)
            symbols.append(
                RepositorySymbol(
                    name=node.name,
                    qualified_name=qualified,
                    symbol_kind="async-function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                    language="Python",
                    relative_path=file.relative_path,
                    line_start=int(node.lineno),
                    line_end=int(getattr(node, "end_lineno", node.lineno)),
                    inputs=tuple(parameters),
                    outputs=tuple(outputs),
                    documentation=documentation[:1200],
                    annotations=tuple(annotations),
                    calls=tuple(calls[:128]),
                    semantic_clues=_semantic_clues(node.name, parameters, documentation, annotations),
                    extraction_mode="PYTHON_AST_EXACT_SYMBOL_BOUNDARY",
                    symbol_sha256=_sha256_bytes(symbol_text.encode("utf-8")),
                )
            )
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._function(node)

        def visit_Assert(self, node: ast.Assert) -> None:
            try:
                statement = ast.unparse(node.test)
            except Exception:
                statement = "assertion at line " + str(node.lineno)
            assertions.append((statement, int(node.lineno)))
            self.generic_visit(node)

    Visitor().visit(tree)
    return symbols, assertions, warnings


def _generic_params(raw: str) -> tuple[str, ...]:
    values: list[str] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        token = token.split("=")[0].strip()
        match = re.findall(r"[A-Za-z_$][\w$]*", token)
        if match:
            values.append(match[-1])
    return tuple(values)


def _generic_symbols(file: RepositorySourceFile) -> list[RepositorySymbol]:
    patterns = list(_GENERIC_SYMBOL_PATTERNS.get(file.language, ()))
    if file.language in {"C", "C++", "C#", "Java", "Kotlin", "Swift"}:
        patterns.append(_C_FAMILY_PATTERN)
    if not patterns:
        return []
    symbols: list[RepositorySymbol] = []
    seen: set[tuple[str, int]] = set()
    for line_number, line in enumerate(file.text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "--", "/*", "*")):
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            name = match.group(1)
            if name.casefold() in _CONTROL_WORDS:
                continue
            key = (name, line_number)
            if key in seen:
                continue
            seen.add(key)
            params = _generic_params(match.group(2) if match.lastindex and match.lastindex >= 2 and match.group(2) else "")
            signature = stripped[:1000]
            symbols.append(
                RepositorySymbol(
                    name=name,
                    qualified_name=name,
                    symbol_kind="function-like-symbol",
                    language=file.language,
                    relative_path=file.relative_path,
                    line_start=line_number,
                    line_end=line_number,
                    inputs=params,
                    outputs=(),
                    documentation="",
                    annotations=(),
                    calls=(),
                    semantic_clues=_semantic_clues(name, params, "", ()),
                    extraction_mode="CONSERVATIVE_SIGNATURE_HEURISTIC",
                    symbol_sha256=_sha256_bytes(signature.encode("utf-8")),
                )
            )
            break
    return symbols


def _safe_item_fragment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:/-]+", "_", value).strip("_/")
    return normalized[:180] or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _file_evidence_item(file: RepositorySourceFile, repo_signature: str, git_commit: str) -> BrainFeedItem:
    item_id = "repo-file::" + _safe_item_fragment(file.relative_path)
    return make_brain_feed_item(
        item_id=item_id,
        kind="EVIDENCE",
        payload={
            "subject_id": f"repository:{repo_signature}",
            "category": "repository-source",
            "producer": "deterministic-repository-static-scanner",
            "method": "sha256-source-fingerprint",
            "target": file.relative_path,
            "oracle": "sha256-file-content",
            "independence_group": f"repo-snapshot:{repo_signature[:20]}",
            "source_snapshot_hash": repo_signature,
            "sha256": file.sha256,
            "success": True,
            "simulated": False,
            "content": {
                "path": file.relative_path,
                "language": file.language,
                "category": file.category,
                "size_bytes": file.size_bytes,
                "sha256": file.sha256,
                "git_commit": git_commit,
            },
            "limitations": [
                "Source fingerprint proves inspected bytes and path, not algorithm correctness.",
                "Repository code was not imported, executed, built, or tested by the scanner.",
            ],
        },
        source_path=file.relative_path,
    )


def _algorithm_item(symbol: RepositorySymbol, file_evidence_id: str, repo_signature: str) -> BrainFeedItem:
    item_id = "repo-alg::" + _safe_item_fragment(f"{symbol.relative_path}::{symbol.qualified_name}:{symbol.line_start}")
    return make_brain_feed_item(
        item_id=item_id,
        kind="ALGORITHM_CANDIDATE",
        payload={
            "name": symbol.qualified_name,
            "inputs": list(symbol.inputs),
            "outputs": list(symbol.outputs),
            "implementation": {
                "language": symbol.language,
                "path": symbol.relative_path,
                "qualified_name": symbol.qualified_name,
                "symbol_kind": symbol.symbol_kind,
                "line_start": symbol.line_start,
                "line_end": symbol.line_end,
                "symbol_sha256": symbol.symbol_sha256,
                "repository_signature": repo_signature,
            },
            "meanings": {
                "status": "UNRESOLVED_FROM_SOURCE_CODE",
                "identifier_clues": list(symbol.semantic_clues),
                "documentation": symbol.documentation,
                "annotations": list(symbol.annotations),
            },
            "calls": list(symbol.calls),
            "extraction": {
                "mode": symbol.extraction_mode,
                "static_only": True,
                "limitations": [
                    "Source identifiers and documentation are semantic clues, not verified meanings.",
                    "Static extraction does not establish behavioral equivalence or correctness.",
                ],
            },
        },
        evidence_from=(file_evidence_id,),
        source_path=symbol.relative_path,
    )


def _experiment_item(symbol: RepositorySymbol, file_evidence_id: str, repo_signature: str) -> BrainFeedItem:
    item_id = "repo-test::" + _safe_item_fragment(f"{symbol.relative_path}::{symbol.qualified_name}:{symbol.line_start}")
    return make_brain_feed_item(
        item_id=item_id,
        kind="EXPERIMENT_CANDIDATE",
        payload={
            "objective": f"Evaluate the behavior encoded by repository test {symbol.qualified_name}",
            "metrics": ["pass_fail"],
            "implementation": {
                "language": symbol.language,
                "path": symbol.relative_path,
                "qualified_name": symbol.qualified_name,
                "line_start": symbol.line_start,
                "line_end": symbol.line_end,
                "symbol_sha256": symbol.symbol_sha256,
                "repository_signature": repo_signature,
            },
            "semantic_clues": list(symbol.semantic_clues),
            "static_only": True,
            "execution_status": "NOT_EXECUTED_BY_REPOSITORY_SCANNER",
        },
        evidence_from=(file_evidence_id,),
        source_path=symbol.relative_path,
    )


def _invariant_item(statement: str, line: int, file: RepositorySourceFile, file_evidence_id: str) -> BrainFeedItem:
    item_id = "repo-invariant::" + _safe_item_fragment(f"{file.relative_path}:{line}:{statement[:80]}")
    return make_brain_feed_item(
        item_id=item_id,
        kind="INVARIANT_CANDIDATE",
        payload={
            "statement": statement,
            "source": {
                "path": file.relative_path,
                "line": line,
                "language": file.language,
            },
            "status": "SOURCE_ASSERTION_REQUIRES_SEMANTIC_AND_EVIDENCE_QUALIFICATION",
        },
        evidence_from=(file_evidence_id,),
        source_path=file.relative_path,
    )


def _document_item(file: RepositorySourceFile, file_evidence_id: str, repo_signature: str) -> BrainFeedItem:
    item_id = "repo-doc::" + _safe_item_fragment(file.relative_path)
    return make_brain_feed_item(
        item_id=item_id,
        kind="SOURCE_DOCUMENT",
        payload={
            "title": file.relative_path,
            "path": file.relative_path,
            "content_digest": file.sha256,
            "language": file.language,
            "category": file.category,
            "repository_signature": repo_signature,
            "semantic_status": "UNRESOLVED_SOURCE_MATERIAL",
        },
        evidence_from=(file_evidence_id,),
        source_path=file.relative_path,
    )


def _repository_summary_item(
    source_root: Path,
    repository_name: str,
    repo_signature: str,
    git_commit: str,
    git_branch: str,
    files: Sequence[RepositorySourceFile],
    symbols: Sequence[RepositorySymbol],
    skipped: Sequence[Mapping[str, str]],
    language_counts: Mapping[str, int],
    total_bytes: int,
    policy: RepositoryScanPolicy,
) -> BrainFeedItem:
    return make_brain_feed_item(
        item_id=f"repo-summary::{_safe_item_fragment(repository_name)}::{repo_signature[:16]}",
        kind="SOURCE_DOCUMENT",
        payload={
            "title": f"Static repository scan: {repository_name}",
            "path": str(source_root),
            "content_digest": repo_signature,
            "repository_signature": repo_signature,
            "git_commit": git_commit,
            "git_branch": git_branch,
            "file_count": len(files),
            "symbol_count": len(symbols),
            "total_bytes": total_bytes,
            "language_counts": dict(sorted(language_counts.items())),
            "skipped_count": len(skipped),
            "policy": policy.to_dict(),
            "safety": {
                "static_read_only": True,
                "code_executed": False,
                "code_imported": False,
                "tests_executed": False,
                "canonical_algorithm_admissions": 0,
            },
        },
        source_path=str(source_root),
    )


def scan_repository(source: Path, policy: RepositoryScanPolicy | None = None) -> RepositoryBrainFeedPlan:
    source_root = source.expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise EGCFError(f"repository brain-feed source must be an existing directory: {source_root}")
    canonical_policy = (policy or RepositoryScanPolicy()).canonical()
    files, skipped, total_bytes = _read_repository_files(source_root, canonical_policy)
    if not files:
        raise EGCFError("repository brain-feed found no eligible text/source files")

    file_identity = [file.identity() for file in sorted(files, key=lambda value: value.relative_path)]
    repo_signature = sha256_json(
        {
            "version": REPOSITORY_BRAIN_FEED_VERSION,
            "files": file_identity,
        }
    )
    git_commit = _git_value(source_root, "rev-parse", "HEAD")
    git_branch = _git_value(source_root, "rev-parse", "--abbrev-ref", "HEAD")
    repository_name = source_root.name or "repository"

    all_symbols: list[RepositorySymbol] = []
    file_symbols: dict[str, list[RepositorySymbol]] = {}
    file_assertions: dict[str, list[tuple[str, int]]] = {}
    scan_warnings: list[dict[str, str]] = []
    for file in files:
        if file.language == "Python":
            symbols, assertions, warnings = _python_symbols(file)
            file_assertions[file.relative_path] = assertions
            for warning in warnings:
                scan_warnings.append({"path": file.relative_path, "reason": warning})
        else:
            symbols = _generic_symbols(file) if file.language != "Text" else []
        remaining = max(0, canonical_policy.max_symbols - len(all_symbols))
        if remaining <= 0:
            if symbols:
                scan_warnings.append({"path": file.relative_path, "reason": "SYMBOL_COUNT_LIMIT"})
            file_symbols[file.relative_path] = []
            continue
        selected = symbols[:remaining]
        if len(selected) < len(symbols):
            scan_warnings.append({"path": file.relative_path, "reason": "SYMBOL_COUNT_LIMIT"})
        file_symbols[file.relative_path] = selected
        all_symbols.extend(selected)
    skipped.extend(scan_warnings)

    language_counts: dict[str, int] = {}
    for file in files:
        language_counts[file.language] = language_counts.get(file.language, 0) + 1

    groups: list[tuple[BrainFeedItem, ...]] = []
    for file in files:
        evidence = _file_evidence_item(file, repo_signature, git_commit)
        group: list[BrainFeedItem] = [evidence]
        symbols = file_symbols.get(file.relative_path, [])
        if symbols:
            for symbol in symbols:
                if file.is_test or symbol.name.casefold().startswith(("test_", "test")):
                    group.append(_experiment_item(symbol, evidence.item_id, repo_signature))
                else:
                    group.append(_algorithm_item(symbol, evidence.item_id, repo_signature))
        elif file.is_document or file.language == "Text" or file.category != "source-code":
            group.append(_document_item(file, evidence.item_id, repo_signature))
        elif file.is_test and canonical_policy.include_tests:
            pseudo = RepositorySymbol(
                name=Path(file.relative_path).stem,
                qualified_name=Path(file.relative_path).stem,
                symbol_kind="test-file",
                language=file.language,
                relative_path=file.relative_path,
                line_start=1,
                line_end=max(1, len(file.text.splitlines())),
                inputs=(),
                outputs=(),
                documentation="",
                annotations=(),
                calls=(),
                semantic_clues=_identifier_words(Path(file.relative_path).stem),
                extraction_mode="FILE_LEVEL_TEST_CANDIDATE",
                symbol_sha256=file.sha256,
            )
            group.append(_experiment_item(pseudo, evidence.item_id, repo_signature))
        else:
            group.append(_document_item(file, evidence.item_id, repo_signature))

        if canonical_policy.include_invariants and file.language == "Python":
            for statement, line in file_assertions.get(file.relative_path, [])[:32]:
                group.append(_invariant_item(statement, line, file, evidence.item_id))
        groups.append(tuple(group))

    summary = _repository_summary_item(
        source_root,
        repository_name,
        repo_signature,
        git_commit,
        git_branch,
        files,
        all_symbols,
        skipped,
        language_counts,
        total_bytes,
        canonical_policy,
    )
    return RepositoryBrainFeedPlan(
        source_root=str(source_root),
        repository_name=repository_name,
        repository_signature=repo_signature,
        git_commit=git_commit,
        git_branch=git_branch,
        files=tuple(files),
        symbols=tuple(all_symbols),
        file_groups=tuple(groups),
        summary_item=summary,
        skipped=tuple(dict(item) for item in skipped),
        language_counts=tuple(sorted(language_counts.items())),
        total_bytes=total_bytes,
        policy=canonical_policy,
    )


def chunk_repository_plan(plan: RepositoryBrainFeedPlan) -> list[list[BrainFeedItem]]:
    limit = plan.policy.max_items_per_batch
    batches: list[list[BrainFeedItem]] = []
    current: list[BrainFeedItem] = [plan.summary_item]
    for group in plan.file_groups:
        if len(group) > limit:
            evidence = group[0]
            payload_items = list(group[1:])
            while payload_items:
                capacity = max(1, limit - 1)
                batches.append([evidence, *payload_items[:capacity]])
                payload_items = payload_items[capacity:]
            continue
        if len(current) + len(group) > limit:
            batches.append(current)
            current = []
        current.extend(group)
    if current:
        batches.append(current)
    if not batches:
        batches = [[plan.summary_item]]
    if any(len(batch) > limit for batch in batches):
        raise EGCFError("repository brain-feed internal chunking exceeded item limit")
    return batches


def plan_as_manifests(plan: RepositoryBrainFeedPlan) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    batches = chunk_repository_plan(plan)
    for index, batch in enumerate(batches, start=1):
        manifests.append(
            {
                "schema_version": 1,
                "batch_id": f"repo-{_safe_item_fragment(plan.repository_name)}-{plan.repository_signature[:12]}-{index:04d}",
                "source_label": f"Static repository feed {plan.repository_name} [{index}/{len(batches)}]",
                "repository_scan": plan.to_summary_dict(),
                "items": [
                    {
                        "id": item.item_id,
                        "kind": item.kind,
                        "depends_on": list(item.depends_on),
                        "evidence_from": list(item.evidence_from),
                        "payload": item.payload,
                    }
                    for item in batch
                ],
            }
        )
    return manifests
