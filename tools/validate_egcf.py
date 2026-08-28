#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ourd.egcf.catalog import command_catalog
from ourd.egcf.models import RECORD_TYPES
from ourd.workspace import Workspace
from tools.generate_egcf_reference import GENERATED


EXCLUDED_PARTS = {
    ".git",
    ".ourd-agent",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        yield path


def python_files(root: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in source_files(root)
        if path.suffix == ".py"
    ]


def source_manifest(root: Path) -> Dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in source_files(root)
    }


def bounded_output(text: str, maximum_lines: int = 100) -> Dict[str, Any]:
    lines = text.splitlines()
    return {
        "sha256": sha256_bytes(text.encode("utf-8")),
        "line_count": len(lines),
        "tail": lines[-maximum_lines:],
        "truncated": len(lines) > maximum_lines,
    }


def run_command(argv: list[str], cwd: Path, timeout: float) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(
                    Path(tempfile.gettempdir()) / "egcf-validator-pycache"
                ),
            },
        )
        returncode = process.returncode
        stdout = process.stdout
        stderr = process.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        timed_out = True
    return {
        "argv": argv,
        "duration_seconds": round(time.monotonic() - started, 6),
        "returncode": returncode,
        "ok": returncode == 0,
        "timed_out": timed_out,
        "stdout": bounded_output(stdout),
        "stderr": bounded_output(stderr),
    }


def validate_contracts() -> Dict[str, Any]:
    objects = json.loads(
        (REPO_ROOT / "schemas" / "egcf-v1" / "objects.schema.json").read_text(
            encoding="utf-8"
        )
    )
    checked_catalog = json.loads(
        (REPO_ROOT / "commands" / "v1" / "catalog.json").read_text(encoding="utf-8")
    )
    algorithm_catalog = json.loads(
        (REPO_ROOT / "algorithms" / "v1" / "catalog.json").read_text(encoding="utf-8")
    )
    failures = []
    generated_stale = [
        relative_path.as_posix()
        for relative_path, renderer in GENERATED.items()
        if not (REPO_ROOT / relative_path).exists()
        or (REPO_ROOT / relative_path).read_text(encoding="utf-8") != renderer()
    ]
    if set(objects.get("$defs", {})) != set(RECORD_TYPES):
        failures.append("canonical object schema does not cover every runtime record")
    if checked_catalog.get("namespaces") != command_catalog().get("namespaces"):
        failures.append("checked-in command catalog differs from runtime catalog")
    if algorithm_catalog.get("floating_versions_allowed") is not False:
        failures.append("algorithm catalog permits floating versions")
    if algorithm_catalog.get("direct_command_callbacks_allowed") is not False:
        failures.append("algorithm catalog permits direct command callbacks")
    if generated_stale:
        failures.append(f"generated schemas or references are stale: {generated_stale}")
    return {
        "name": "egcf_contracts",
        "ok": not failures,
        "failures": failures,
        "record_types": sorted(RECORD_TYPES),
        "command_count": sum(len(verbs) for verbs in checked_catalog["namespaces"].values()),
        "namespace_count": len(checked_catalog["namespaces"]),
        "generated_files": [item.as_posix() for item in GENERATED],
    }


def inspect_wheel(wheel_path: Path) -> Dict[str, Any]:
    required_suffixes = {
        "ourd/egcf/engine.py",
        "ourd/egcf/cli.py",
        "ourd/egcf/adapters/eon.py",
        "ourd/egcf/adapters/control.py",
        "commands/v1/catalog.json",
        "commands/v1/contracts.json",
        "algorithms/v1/catalog.json",
        "schemas/egcf-v1/objects.schema.json",
        "workflows/v1/parser-regression.json",
        "egcf.py",
    }
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
        entry_points = next(
            (
                archive.read(name).decode("utf-8")
                for name in names
                if name.endswith(".dist-info/entry_points.txt")
            ),
            "",
        )
    missing = sorted(required_suffixes - names)
    return {
        "path": str(wheel_path),
        "sha256": sha256_file(wheel_path),
        "size": wheel_path.stat().st_size,
        "missing_required_files": missing,
        "egcf_entry_point": "egcf = ourd.egcf.cli:main" in entry_points,
        "ok": not missing and "egcf = ourd.egcf.cli:main" in entry_points,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an exact-snapshot deterministic EGCFv1 validation bundle"
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--no-report", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    started_at = utc_now()
    snapshot_before = Workspace(REPO_ROOT).snapshot_hash()
    manifest_before = source_manifest(REPO_ROOT)
    with tempfile.TemporaryDirectory(prefix="egcf-wheel-") as temporary:
        wheel_dir = Path(temporary) / "first"
        repeat_wheel_dir = Path(temporary) / "second"
        wheel_dir.mkdir()
        repeat_wheel_dir.mkdir()
        checks = [
            run_command(
                [sys.executable, "-m", "py_compile", *python_files(REPO_ROOT)],
                REPO_ROOT,
                args.timeout,
            ),
            run_command(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                REPO_ROOT,
                args.timeout,
            ),
            run_command(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(repeat_wheel_dir),
                ],
                REPO_ROOT,
                args.timeout,
            ),
            run_command(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheel_dir),
                ],
                REPO_ROOT,
                args.timeout,
            ),
            run_command(
                [
                    sys.executable,
                    "egcf.py",
                    "capability",
                    "list",
                    "--repo",
                    str(REPO_ROOT),
                    "--dry-run",
                    "--why",
                    "--json",
                    "--graph",
                    "--trace",
                    "--record",
                ],
                REPO_ROOT,
                args.timeout,
            ),
        ]
        test_check = next(
            check
            for check in checks
            if check["argv"][1:4] == ["-m", "unittest", "discover"]
        )
        test_text = "\n".join(
            line
            for stream in ("stdout", "stderr")
            for line in test_check[stream]["tail"]
        )
        match = re.search(r"Ran (\d+) tests?", test_text)
        wheel_paths = sorted(wheel_dir.glob("*.whl"))
        repeat_wheel_paths = sorted(repeat_wheel_dir.glob("*.whl"))
        wheel = inspect_wheel(wheel_paths[0]) if len(wheel_paths) == 1 else {
            "ok": False,
            "error": f"expected one wheel, found {len(wheel_paths)}",
        }
        repeat_wheel = (
            inspect_wheel(repeat_wheel_paths[0])
            if len(repeat_wheel_paths) == 1
            else {
                "ok": False,
                "error": f"expected one repeat wheel, found {len(repeat_wheel_paths)}",
            }
        )
        wheel["repeat_sha256"] = repeat_wheel.get("sha256", "")
        wheel["reproducible"] = bool(
            wheel.get("ok")
            and repeat_wheel.get("ok")
            and wheel.get("sha256") == repeat_wheel.get("sha256")
        )
        if wheel.get("ok"):
            wheel_import = run_command(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "import ourd, ourd.egcf, egcf; "
                    "from ourd.egcf.cli import build_parser; "
                    "assert build_parser().prog == 'egcf'; print('wheel-import: PASS')",
                    wheel["path"],
                ],
                REPO_ROOT,
                args.timeout,
            )
            checks.append(wheel_import)
            wheel["import_ok"] = wheel_import["ok"]
        else:
            wheel["import_ok"] = False
        contracts = validate_contracts()
        snapshot_after = Workspace(REPO_ROOT).snapshot_hash()
        manifest_after = source_manifest(REPO_ROOT)
        source_stable = snapshot_before == snapshot_after and manifest_before == manifest_after
        deterministic_ok = (
            all(check["ok"] for check in checks)
            and wheel["ok"]
            and wheel["reproducible"]
            and wheel["import_ok"]
            and contracts["ok"]
        )
        report: Dict[str, Any] = {
            "schema_version": 1,
            "report_kind": "egcfv1-deterministic-validation",
            "status": "DETERMINISTICALLY_VALIDATED" if deterministic_ok and source_stable else "FAILED",
            "generated_at": utc_now(),
            "started_at": started_at,
            "repository": str(REPO_ROOT),
            "python": sys.version,
            "platform": platform.platform(),
            "candidate_snapshot_hash": snapshot_before,
            "post_validation_snapshot_hash": snapshot_after,
            "source_stable": source_stable,
            "source_manifest": manifest_before,
            "contracts": contracts,
            "checks": checks,
            "test_count": int(match.group(1)) if match else None,
            "wheel": wheel,
            "deterministic_ok": deterministic_ok,
            "overall_ok": deterministic_ok and source_stable,
            "human_approval_required": True,
            "certified": False,
            "limitations": [
                "This report does not constitute human approval or certification.",
                "Live-model quality is evaluated separately and cannot grant authority.",
                "C4 and C5 external or destructive mutation remain fail-closed.",
            ],
        }
        if not args.no_report:
            report_path = args.report or (
                REPO_ROOT
                / ".ourd-agent"
                / "egcf"
                / "validation"
                / f"{snapshot_before}.json"
            )
            report["report_path"] = str(report_path)
        report["payload_sha256"] = sha256_bytes(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        if not args.no_report:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
