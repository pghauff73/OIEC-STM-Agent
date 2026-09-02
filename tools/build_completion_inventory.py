#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


PLAN_FILES = (
    "IMPLEMENTATION_PLAN.md",
    "OIEC_STMV1_2_IMPLEMENTATION_PLAN.md",
    "OIEC_SR_V1_IMPLEMENTATION_PLAN.md",
    "EGCFV1_IMPLEMENTATION_PLAN.md",
    "OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md",
    "DOCS_RELATIONAL_TREE_REFACTOR_PLAN.md",
    "DOCS_BEGINNER_ESSAY_REWRITE_PLAN.md",
    "COMPLETE_IMPLEMENTATION_STRATEGY.md",
)

SOURCE_EXCLUDED_PREFIXES = (
    "reports/",
)

ALLOWED_STATUSES = {
    "NOT_IMPLEMENTED",
    "IMPLEMENTED_UNVERIFIED",
    "FOCUSED_VALIDATED",
    "FULLY_VALIDATED",
    "HUMAN_APPROVAL_REQUIRED",
    "CERTIFIED",
    "RELEASED",
    "EXPLICITLY_EXCLUDED",
}

ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
CODE_REQUIREMENT_RE = re.compile(
    r"(?:^test_[a-zA-Z0-9_]+$|"
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+\.(?:py|json|md|toml|ya?ml|gbnf)$|"
    r"^(?:python3?|git|cmake|ctest|pytest|oiec-stm-agent)\s+|"
    r"^[A-Z][A-Z0-9_ -]{2,}$)"
)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = re.sub(r"[`*_]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.rstrip(".;:")


def requirement_identity(text: str) -> str:
    normalized = normalize_text(text).casefold()
    return f"REQ-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16].upper()}"


@dataclass
class RequirementDraft:
    requirement_id: str
    requirement_text: str
    source_plan: str
    source_heading: str
    source_line: int
    provenance: list[dict[str, object]] = field(default_factory=list)


def _flush_item(
    drafts: list[RequirementDraft],
    *,
    plan: str,
    heading: str,
    line_number: int,
    parts: list[str],
) -> None:
    if not parts:
        return
    text = normalize_text(" ".join(parts))
    if not text:
        return
    drafts.append(
        RequirementDraft(
            requirement_id=requirement_identity(text),
            requirement_text=text,
            source_plan=plan,
            source_heading=heading,
            source_line=line_number,
            provenance=[
                {
                    "source_plan": plan,
                    "source_heading": heading,
                    "source_line": line_number,
                }
            ],
        )
    )


def extract_requirements(path: Path) -> list[RequirementDraft]:
    lines = path.read_text(encoding="utf-8").splitlines()
    drafts: list[RequirementDraft] = []
    heading = "Document"
    in_fence = False
    item_parts: list[str] = []
    item_line = 0

    for line_number, raw in enumerate(lines, 1):
        heading_match = HEADING_RE.match(raw)
        item_match = ITEM_RE.match(raw)

        if raw.strip().startswith("```"):
            _flush_item(
                drafts,
                plan=path.name,
                heading=heading,
                line_number=item_line,
                parts=item_parts,
            )
            item_parts = []
            in_fence = not in_fence
            continue

        if heading_match and not in_fence:
            _flush_item(
                drafts,
                plan=path.name,
                heading=heading,
                line_number=item_line,
                parts=item_parts,
            )
            item_parts = []
            heading = normalize_text(heading_match.group(2))
            if re.search(
                r"\b(?:phase|milestone|gate|objective|deliverable|requirement|"
                r"success target|release|definition of done|exit)\b",
                heading,
                re.IGNORECASE,
            ):
                _flush_item(
                    drafts,
                    plan=path.name,
                    heading=heading,
                    line_number=line_number,
                    parts=[heading],
                )
            continue

        if in_fence:
            text = normalize_text(raw)
            if text and CODE_REQUIREMENT_RE.search(text):
                _flush_item(
                    drafts,
                    plan=path.name,
                    heading=heading,
                    line_number=line_number,
                    parts=[text],
                )
            continue

        if item_match:
            _flush_item(
                drafts,
                plan=path.name,
                heading=heading,
                line_number=item_line,
                parts=item_parts,
            )
            item_parts = [item_match.group(1)]
            item_line = line_number
            continue

        if item_parts and (raw.startswith("  ") or raw.startswith("    ")) and raw.strip():
            item_parts.append(raw.strip())
            continue

        _flush_item(
            drafts,
            plan=path.name,
            heading=heading,
            line_number=item_line,
            parts=item_parts,
        )
        item_parts = []

        if raw.startswith("|") and raw.endswith("|") and "---" not in raw:
            cells = [normalize_text(cell) for cell in raw.strip("|").split("|")]
            if cells and not all(cell.casefold() in {"component", "responsibility"} for cell in cells):
                text = " | ".join(cell for cell in cells if cell)
                if text and not re.match(r"^(requirement|workstream|component)\b", text, re.I):
                    _flush_item(
                        drafts,
                        plan=path.name,
                        heading=heading,
                        line_number=line_number,
                        parts=[text],
                    )

    _flush_item(
        drafts,
        plan=path.name,
        heading=heading,
        line_number=item_line,
        parts=item_parts,
    )
    return drafts


def _owner_for(text: str) -> tuple[str, list[str], list[str]]:
    lowered = text.casefold()
    if any(term in lowered for term in ("documentation", "docs/", "svg", "essay", "markdown")):
        return "documentation", ["tools/build_docs_site.py", "docs"], ["tests/test_docs_site.py"]
    if any(term in lowered for term in ("llama.cpp", "gguf", "gbnf", "qwen3.8", "native runner")):
        return (
            "llama_cpp_provider",
            ["native/oiec_llama_runner", "ourd/providers/llama_cpp_process.py"],
            ["tests/providers/test_llama_cpp_process.py"],
        )
    if any(term in lowered for term in ("super reasoning", "oiec-sr", "hypothesis", "reasoning path", "verifier", "falsifier", "synthesis", "contradiction")):
        return "oiec_sr", ["ourd/reasoning"], ["tests/test_reasoning.py", "tests/reasoning"]
    if any(term in lowered for term in ("gui", "tk", "opengl", "visual", "mesh", "image")):
        return "gui", ["ourd_gui"], ["tests/gui"]
    if "egcf" in lowered or any(term in lowered for term in ("capability ladder", "evidence gate", "c0-c5", "domain pack")):
        return "egcf", ["ourd/egcf"], ["tests/test_egcf_completion.py", "tests/egcf"]
    if any(term in lowered for term in ("persistence", "migration", "hash-chain", "event chain", "runtime state")):
        return "persistence", ["ourd/persistence.py", "ourd/models.py"], ["tests/test_persistence.py"]
    if "cfel" in lowered or "collision" in lowered:
        return "cfel", ["ourd/cfel.py"], ["tests/test_cfel.py", "tests/test_reasoning.py"]
    if any(term in lowered for term in ("oiec-stm", "boundary", "dimension budget", "attemptkey", "no-blind-retry", "progress certificate")):
        return "oiec_stm", ["ourd/oiec.py", "ourd/models.py"], ["tests/test_oiec.py"]
    if any(term in lowered for term in ("authority", "policy", "risk floor", "scope", "approval")):
        return "authority_policy", ["ourd/authority.py", "ourd/policy.py"], ["tests/test_security.py", "tests/test_policy.py"]
    if any(term in lowered for term in ("transaction", "eon", "mutation", "rollback", "write")):
        return "transaction_eon", ["ourd/transactions.py", "ourd/agent.py"], ["tests/test_transactions.py", "tests/test_agent_tools.py"]
    if any(term in lowered for term in ("package", "wheel", "sdist", "github actions", "ci", "release", "merge", "tag")):
        return "release", ["pyproject.toml", ".github/workflows", "tools/build_backend.py"], ["tests/gui/test_packaging.py"]
    return "program", ["COMPLETE_IMPLEMENTATION_STRATEGY.md"], ["reports/completion"]


def _status_for(root: Path, text: str, implementation_paths: Sequence[str]) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("human approval", "exact-hash approval", "obtain explicit human", "certification")):
        return "HUMAN_APPROVAL_REQUIRED"
    if any(term in lowered for term in ("merge to main", "tag release", "publish package", "released", "remote main sha")):
        return "NOT_IMPLEMENTED"
    if any((root / path).exists() for path in implementation_paths):
        return "IMPLEMENTED_UNVERIFIED"
    return "NOT_IMPLEMENTED"


def merge_requirements(root: Path, drafts: Iterable[RequirementDraft]) -> list[dict[str, object]]:
    merged: dict[str, RequirementDraft] = {}
    for draft in drafts:
        existing = merged.get(draft.requirement_id)
        if existing is None:
            merged[draft.requirement_id] = draft
            continue
        for provenance in draft.provenance:
            if provenance not in existing.provenance:
                existing.provenance.append(provenance)

    rows: list[dict[str, object]] = []
    for draft in sorted(merged.values(), key=lambda item: item.requirement_id):
        owner, implementation_paths, evidence_paths = _owner_for(draft.requirement_text)
        existing_implementation = [path for path in implementation_paths if (root / path).exists()]
        existing_evidence = [path for path in evidence_paths if (root / path).exists()]
        status = _status_for(root, draft.requirement_text, implementation_paths)
        if status not in ALLOWED_STATUSES:
            raise RuntimeError(f"invalid status: {status}")
        rows.append(
            {
                "requirement_id": draft.requirement_id,
                "source_plan": draft.source_plan,
                "source_heading": draft.source_heading,
                "source_line": draft.source_line,
                "requirement_text": draft.requirement_text,
                "provenance": sorted(
                    draft.provenance,
                    key=lambda item: (
                        str(item["source_plan"]),
                        int(item["source_line"]),
                        str(item["source_heading"]),
                    ),
                ),
                "canonical_owner": owner,
                "implementation_paths": implementation_paths,
                "existing_implementation_paths": existing_implementation,
                "test_or_evidence_owner": evidence_paths,
                "existing_test_or_evidence_owner": existing_evidence,
                "status": status,
                "blocking_dependencies": [],
                "last_verified_source_hash": "",
            }
        )
    return rows


def git_candidate_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", errors="surrogateescape")
        if path.startswith(SOURCE_EXCLUDED_PREFIXES):
            continue
        candidate = root / path
        if candidate.is_file():
            paths.append(path)
    return sorted(set(paths))


def build_source_manifest(root: Path) -> dict[str, object]:
    files = []
    for relative in git_candidate_paths(root):
        path = root / relative
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
                "mode": oct(path.stat().st_mode & 0o777),
            }
        )
    tree_hash = stable_hash(files)
    return {
        "schema_version": 1,
        "tree_hash": tree_hash,
        "file_count": len(files),
        "files": files,
    }


def markdown_projection(payload: dict[str, object]) -> str:
    rows = payload["requirements"]
    lines = [
        "# Completion Requirement Inventory",
        "",
        f"Source tree hash: `{payload['source_tree_hash']}`",
        f"Requirement count: **{len(rows)}**",
        "",
        "| ID | Status | Owner | Source | Requirement |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        text = str(row["requirement_text"]).replace("|", "\\|")
        source = f"{row['source_plan']}:{row['source_line']}"
        lines.append(
            f"| `{row['requirement_id']}` | `{row['status']}` | "
            f"`{row['canonical_owner']}` | `{source}` | {text} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_inventory(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    missing = [name for name in PLAN_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing accepted plan files: {missing!r}")
    source_manifest = build_source_manifest(root)
    drafts = []
    plan_hashes = {}
    for name in PLAN_FILES:
        path = root / name
        plan_hashes[name] = sha256_file(path)
        drafts.extend(extract_requirements(path))
    requirements = merge_requirements(root, drafts)
    for row in requirements:
        row["last_verified_source_hash"] = source_manifest["tree_hash"]
    payload = {
        "schema_version": 1,
        "source_tree_hash": source_manifest["tree_hash"],
        "plan_hashes": plan_hashes,
        "requirement_count": len(requirements),
        "requirements": requirements,
    }
    payload["signature"] = stable_hash(payload)
    return source_manifest, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the OIEC completion inventory")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_manifest, inventory = build_inventory(root)
    (output / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "requirements.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "requirements.md").write_text(
        markdown_projection(inventory),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "source_tree_hash": source_manifest["tree_hash"],
                "requirements": inventory["requirement_count"],
                "signature": inventory["signature"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
