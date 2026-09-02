#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_completion_inventory import (
    ALLOWED_STATUSES,
    build_inventory,
    canonical_json,
    markdown_projection,
    sha256_file,
    stable_hash,
)


REQUIRED_GATE_IDS = (
    "compileall",
    "focused_changed_modules",
    "oiec_cfel_persistence",
    "sr_provider_benchmark",
    "egcf",
    "gui",
    "docs",
    "docs_reproducible",
    "full_discovery",
    "gui_smoke",
    "opengl_optional",
    "packaging",
    "install_smoke",
    "validation_tools",
    "git_audit",
    "ollama_qwen38",
    "direct_qwen38",
    "benchmark_ablations",
    "ci_definition",
)

SKIPPABLE_GATE_IDS = {"opengl_optional"}

OWNER_GATE_IDS = {
    "authority_policy": (
        "focused_changed_modules",
        "full_discovery",
        "validation_tools",
    ),
    "transaction_eon": (
        "focused_changed_modules",
        "full_discovery",
        "validation_tools",
    ),
    "persistence": (
        "oiec_cfel_persistence",
        "full_discovery",
    ),
    "oiec_stm": (
        "oiec_cfel_persistence",
        "full_discovery",
    ),
    "cfel": (
        "oiec_cfel_persistence",
        "full_discovery",
    ),
    "oiec_sr": (
        "sr_provider_benchmark",
        "benchmark_ablations",
        "ollama_qwen38",
        "direct_qwen38",
        "full_discovery",
    ),
    "egcf": ("egcf", "validation_tools", "full_discovery"),
    "llama_cpp_provider": (
        "sr_provider_benchmark",
        "direct_qwen38",
        "full_discovery",
    ),
    "gui": ("gui", "gui_smoke", "full_discovery"),
    "documentation": ("docs", "docs_reproducible", "full_discovery"),
    "release": (
        "packaging",
        "install_smoke",
        "git_audit",
        "ci_definition",
    ),
    "program": REQUIRED_GATE_IDS,
}

REQUIRED_BUNDLE_PATHS = (
    "source_manifest.json",
    "requirements.json",
    "validation_report.json",
    "test_logs",
    "package_hashes.sha256",
    "docs_manifest.json",
    "benchmark_reports",
    "limitations.json",
    "rollback_manifest.json",
    "candidate_summary.md",
)

PENDING_RELEASE_TERMS = (
    "merge to main",
    "merged commit",
    "remote main sha",
    "tag release",
    "publish package",
    "publish release",
    "publicly retrievable",
    "approved candidate",
    "ci green on exact head",
    "released",
)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _relative_artifact(staging: Path, raw_path: object) -> Path:
    relative = Path(str(raw_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"qualification artifact path is unsafe: {relative}")
    resolved = (staging / relative).resolve()
    try:
        resolved.relative_to(staging.resolve())
    except ValueError as exc:
        raise ValueError(f"qualification artifact escapes staging: {relative}") from exc
    return resolved


def validate_evidence_manifest(
    staging: Path,
    payload: Mapping[str, Any],
    *,
    source_tree_hash: str,
) -> dict[str, dict[str, Any]]:
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("qualification evidence schema_version must be 1")
    if str(payload.get("source_tree_hash", "")) != source_tree_hash:
        raise ValueError("qualification evidence source tree hash mismatch")
    gates_payload = payload.get("gates")
    if not isinstance(gates_payload, list):
        raise ValueError("qualification evidence gates must be a list")
    gates: dict[str, dict[str, Any]] = {}
    for raw_gate in gates_payload:
        if not isinstance(raw_gate, dict):
            raise ValueError("qualification gate must be a JSON object")
        gate_id = str(raw_gate.get("gate_id", "")).strip()
        status = str(raw_gate.get("status", "")).strip().upper()
        if not gate_id or gate_id in gates:
            raise ValueError(f"duplicate or empty qualification gate: {gate_id!r}")
        if status not in {"PASS", "FAIL", "SKIP"}:
            raise ValueError(f"invalid qualification gate status: {status!r}")
        if status == "SKIP" and gate_id not in SKIPPABLE_GATE_IDS:
            raise ValueError(f"qualification gate may not be skipped: {gate_id}")
        for field in ("command", "started_utc", "ended_utc", "runtime"):
            if not raw_gate.get(field):
                raise ValueError(f"qualification gate {gate_id} omitted {field}")
        artifacts = raw_gate.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError(f"qualification gate {gate_id} has no artifacts")
        validated_artifacts = []
        for raw_artifact in artifacts:
            if not isinstance(raw_artifact, dict):
                raise ValueError(f"qualification gate {gate_id} artifact is invalid")
            relative = Path(str(raw_artifact.get("path", "")))
            path = _relative_artifact(staging, relative)
            if not path.is_file():
                raise ValueError(f"qualification artifact is missing: {relative}")
            digest = sha256_file(path)
            if digest != str(raw_artifact.get("sha256", "")):
                raise ValueError(f"qualification artifact hash mismatch: {relative}")
            validated_artifacts.append(
                {
                    "path": relative.as_posix(),
                    "sha256": digest,
                    "size": path.stat().st_size,
                }
            )
        gate = dict(raw_gate)
        gate["gate_id"] = gate_id
        gate["status"] = status
        gate["artifacts"] = validated_artifacts
        gate["signature"] = stable_hash(
            {key: value for key, value in gate.items() if key != "signature"}
        )
        gates[gate_id] = gate
    missing = sorted(set(REQUIRED_GATE_IDS) - set(gates))
    extra = sorted(set(gates) - set(REQUIRED_GATE_IDS))
    if missing or extra:
        raise ValueError(
            f"qualification gate set mismatch: missing={missing!r} extra={extra!r}"
        )
    return gates


def gate_accepted(gate: Mapping[str, Any]) -> bool:
    status = str(gate["status"])
    return status == "PASS" or (
        status == "SKIP" and str(gate["gate_id"]) in SKIPPABLE_GATE_IDS
    )


def _pending_release_requirement(text: str) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in PENDING_RELEASE_TERMS)


def qualify_requirements(
    inventory: Mapping[str, Any],
    gates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    qualified_rows = []
    for raw_row in inventory["requirements"]:
        row = dict(raw_row)
        owner = str(row["canonical_owner"])
        required_gates = OWNER_GATE_IDS.get(owner, REQUIRED_GATE_IDS)
        evidence = [
            {
                "gate_id": gate_id,
                "status": gates[gate_id]["status"],
                "signature": gates[gate_id]["signature"],
                "artifacts": gates[gate_id]["artifacts"],
            }
            for gate_id in required_gates
        ]
        current_status = str(row["status"])
        blocking = []
        if current_status in {"HUMAN_APPROVAL_REQUIRED", "CERTIFIED", "RELEASED"}:
            pass
        elif current_status == "NOT_IMPLEMENTED" or _pending_release_requirement(
            str(row["requirement_text"])
        ):
            row["status"] = "NOT_IMPLEMENTED"
            blocking.append("release_transition_not_performed")
        else:
            blocking = [
                gate_id for gate_id in required_gates if not gate_accepted(gates[gate_id])
            ]
            row["status"] = "FULLY_VALIDATED" if not blocking else "IMPLEMENTED_UNVERIFIED"
        if row["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"invalid qualified requirement status: {row['status']}")
        row["blocking_dependencies"] = blocking
        row["qualification_evidence"] = evidence
        qualified_rows.append(row)
    payload = dict(inventory)
    payload["requirements"] = qualified_rows
    payload["status_counts"] = dict(sorted(Counter(row["status"] for row in qualified_rows).items()))
    payload["signature"] = stable_hash(
        {key: value for key, value in payload.items() if key != "signature"}
    )
    return payload


def build_docs_manifest(root: Path) -> dict[str, Any]:
    docs_root = root / "docs"
    files = []
    for path in sorted(item for item in docs_root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    suffix_counts = Counter(Path(item["path"]).suffix.lower() for item in files)
    return {
        "schema_version": 1,
        "file_count": len(files),
        "html_count": suffix_counts[".html"],
        "svg_count": suffix_counts[".svg"],
        "tree_hash": stable_hash(files),
        "files": files,
    }


def _copy_stage_tree(staging: Path, destination: Path, relative: str) -> None:
    source = _relative_artifact(staging, relative)
    target = destination / relative
    if source.is_dir():
        shutil.copytree(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    else:
        raise ValueError(f"required qualification staging path is missing: {relative}")


def _git_text(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def build_rollback_manifest(
    root: Path,
    source_manifest: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    rollback = evidence.get("rollback", {})
    if not isinstance(rollback, Mapping):
        raise ValueError("qualification rollback metadata must be an object")
    status = subprocess.check_output(
        ["git", "status", "--short"], cwd=root, text=True
    ).splitlines()
    payload = {
        "schema_version": 1,
        "source_tree_hash": source_manifest["tree_hash"],
        "git_head": _git_text(root, "rev-parse", "HEAD"),
        "branch": _git_text(root, "branch", "--show-current"),
        "upstream": _git_text(root, "rev-parse", "--abbrev-ref", "@{upstream}"),
        "worktree_dirty": bool(status),
        "worktree_status_sha256": stable_hash(status),
        "recovery_bundle": str(rollback.get("recovery_bundle", "")),
        "recovery_stash": str(rollback.get("recovery_stash", "")),
        "restore_sequence": tuple(
            rollback.get(
                "restore_sequence",
                (
                    "preserve the qualification bundle outside the worktree",
                    "reset the integration branch only after explicit human approval",
                    "restore the named recovery bundle or stash if rollback is required",
                    "re-run the source manifest and deterministic qualification",
                ),
            )
        ),
    }
    payload["signature"] = stable_hash(payload)
    return payload


def _hash_bundle_files(output: Path) -> str:
    lines = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == "qualification_hashes.sha256":
            continue
        relative = path.relative_to(output).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    return "\n".join(lines) + "\n"


def finalize_bundle(root: Path, staging: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"qualification output already exists: {output}")
    source_manifest, inventory = build_inventory(root)
    evidence_path = staging / "evidence_manifest.json"
    evidence = _load_object(evidence_path, "qualification evidence manifest")
    gates = validate_evidence_manifest(
        staging,
        evidence,
        source_tree_hash=str(source_manifest["tree_hash"]),
    )
    qualified = qualify_requirements(inventory, gates)
    docs_manifest = build_docs_manifest(root)
    limitations = list(evidence.get("limitations", []))
    for gate in gates.values():
        if gate["status"] == "SKIP":
            limitations.append(f"{gate['gate_id']} was skipped: {gate.get('summary', '')}")
    limitations = sorted(set(str(item) for item in limitations if str(item).strip()))
    rollback_manifest = build_rollback_manifest(root, source_manifest, evidence)
    gate_status_counts = dict(sorted(Counter(gate["status"] for gate in gates.values()).items()))
    unresolved_non_release = [
        row
        for row in qualified["requirements"]
        if row["canonical_owner"] != "release"
        and row["status"] not in {"FULLY_VALIDATED", "HUMAN_APPROVAL_REQUIRED"}
    ]
    required_gate_failures = [
        gate_id for gate_id, gate in gates.items() if not gate_accepted(gate)
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / output.name
        temporary_output.mkdir()
        for relative in ("test_logs", "packages", "benchmark_reports", "package_hashes.sha256"):
            _copy_stage_tree(staging, temporary_output, relative)
        shutil.copy2(evidence_path, temporary_output / "evidence_manifest.json")
        (temporary_output / "source_manifest.json").write_text(
            json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temporary_output / "requirements.json").write_text(
            json.dumps(qualified, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temporary_output / "requirements.md").write_text(
            markdown_projection(qualified), encoding="utf-8"
        )
        (temporary_output / "docs_manifest.json").write_text(
            json.dumps(docs_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        limitations_payload = {
            "schema_version": 1,
            "source_tree_hash": source_manifest["tree_hash"],
            "limitations": limitations,
        }
        limitations_payload["signature"] = stable_hash(limitations_payload)
        (temporary_output / "limitations.json").write_text(
            json.dumps(limitations_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temporary_output / "rollback_manifest.json").write_text(
            json.dumps(rollback_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        validation_report = {
            "schema_version": 1,
            "applicable_date": str(evidence.get("applicable_date", "")),
            "source_tree_hash": source_manifest["tree_hash"],
            "source_file_count": source_manifest["file_count"],
            "git_head": rollback_manifest["git_head"],
            "branch": rollback_manifest["branch"],
            "gate_status_counts": gate_status_counts,
            "gates": [gates[key] for key in REQUIRED_GATE_IDS],
            "requirement_count": qualified["requirement_count"],
            "requirement_status_counts": qualified["status_counts"],
            "unresolved_non_release_requirement_ids": [
                row["requirement_id"] for row in unresolved_non_release
            ],
            "required_gate_failures": required_gate_failures,
            "limitations": limitations,
            "p8_gate_passed": not required_gate_failures and not unresolved_non_release,
            "human_approval_required": True,
            "release_ready": False,
        }
        validation_report["signature"] = stable_hash(validation_report)
        (temporary_output / "validation_report.json").write_text(
            json.dumps(validation_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary_lines = [
            "# OIEC-STM-Agent Qualification Candidate",
            "",
            f"- Applicable date: `{validation_report['applicable_date']}`",
            f"- Source tree hash: `{source_manifest['tree_hash']}`",
            f"- Git base HEAD: `{rollback_manifest['git_head']}`",
            f"- Qualification gates: `{gate_status_counts}`",
            f"- Requirement statuses: `{qualified['status_counts']}`",
            f"- P8 gate passed: `{str(validation_report['p8_gate_passed']).lower()}`",
            "- Release state: `HUMAN_APPROVAL_REQUIRED`",
            "",
            "The local model remains advisory. This bundle is deterministic and",
            "source-bound evidence, not human approval, certification, merge, or release.",
            "",
        ]
        (temporary_output / "candidate_summary.md").write_text(
            "\n".join(summary_lines), encoding="utf-8"
        )
        missing_paths = [
            relative
            for relative in REQUIRED_BUNDLE_PATHS
            if not (temporary_output / relative).exists()
        ]
        if missing_paths:
            raise ValueError(f"qualification bundle is incomplete: {missing_paths!r}")
        (temporary_output / "qualification_hashes.sha256").write_text(
            _hash_bundle_files(temporary_output), encoding="utf-8"
        )
        os.replace(temporary_output, output)
    return {
        "output": str(output),
        "source_tree_hash": source_manifest["tree_hash"],
        "requirements_signature": qualified["signature"],
        "validation_signature": validation_report["signature"],
        "p8_gate_passed": validation_report["p8_gate_passed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize an immutable OIEC P8 bundle")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = finalize_bundle(
        args.root.resolve(), args.staging.resolve(), args.output.resolve()
    )
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
