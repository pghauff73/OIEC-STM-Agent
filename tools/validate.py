#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ourd import OURDAgent, Workspace
from ourd.providers import ProviderConfig


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_command(
    argv: List[str],
    cwd: Path,
    *,
    env_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    process = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(Path(tempfile.gettempdir()) / "ourd-validator-pycache"),
            **dict(env_overrides or {}),
        },
    )
    return {
        "argv": argv,
        "returncode": process.returncode,
        "ok": process.returncode == 0,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def python_files(root: Path) -> List[str]:
    files = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(
            part in {".ourd-agent", "__pycache__", ".venv", "venv", "build", "dist"}
            or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        files.append(relative.as_posix())
    return sorted(files)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hashes(root: Path) -> Dict[str, str]:
    included = []
    for name in (
        "README.md",
        "IMPLEMENTATION_PLAN.md",
        "EGCFV1_IMPLEMENTATION_PLAN.md",
        "OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md",
        "pyproject.toml",
        "ourd_agent.py",
        "egcf.py",
        "test_policy.py",
    ):
        path = root / name
        if path.exists():
            included.append(path)
    included.extend((root / "ourd").rglob("*.py"))
    included.extend((root / "ourd_gui").rglob("*.py"))
    included.extend((root / "tests").rglob("*.py"))
    included.extend((root / "schemas").glob("*.json"))
    included.extend((root / "docs").rglob("*.md"))
    included.extend(
        root / "tools" / name
        for name in ("build_backend.py", "validate.py")
    )
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(set(included))
        if path.exists()
    }


def run_live_llama_cpp(args: argparse.Namespace) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "README.md").write_text("# Live smoke\n\nread only\n", encoding="utf-8")
        config = ProviderConfig(
            model=args.model,
            provider_kind="llama_cpp_process",
            base_url=args.base_url,
            api_key=args.api_key,
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
            context_budget_tokens=args.context_budget,
            runtime_context_tokens=args.runtime_context_tokens,
            timeout_seconds=args.timeout_seconds,
            max_transport_retries=0,
            runner_path=args.runner_path,
            model_path=args.model_path,
            expected_model_sha256=args.expected_model_sha256,
            llama_cpp_root=args.llama_cpp_root,
            llama_cpp_build_dir=args.llama_cpp_build_dir,
            llama_grammar_dir=args.llama_grammar_dir,
            llama_context_tokens=args.llama_context,
            llama_gpu_layers=args.llama_gpu_layers,
            llama_threads=args.llama_threads,
            llama_seed=args.llama_seed,
            llama_temperature_bp=args.llama_temperature_bp,
            llama_top_p_bp=args.llama_top_p_bp,
            llama_top_k=args.llama_top_k,
        )
        with OURDAgent(root, provider_config=config, max_steps=8) as agent:
            preflight = agent.provider_preflight()
            response = agent.run_task(
                "Use read-only tools to list the workspace and read README.md. "
                "Do not establish governance or attempt mutation. Then report the visible files."
            )
            state = agent.state.to_dict()
        return {
            "ok": bool(response.strip()),
            "preflight": preflight,
            "response": response,
            "collisions": state.get("collisions", []),
            "changed_files": state.get("changed_files", []),
        }


def xvfb_server_argv(
    executable: str,
    display_number: int,
    authority_path: Path,
) -> List[str]:
    return [
        executable,
        f":{display_number}",
        "-auth",
        str(authority_path),
        "-screen",
        "0",
        "1280x800x24",
        "-nolisten",
        "unix",
        "-listen",
        "tcp",
    ]


def _available_tcp_display() -> int:
    return 1000 + ((os.getpid() + time.monotonic_ns()) % 50000)


def _wait_for_x_display(
    server: subprocess.Popen[str],
    xdpyinfo: str,
    display: str,
    authority_path: Path,
) -> bool:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if server.poll() is not None:
            return False
        probe = subprocess.run(
            [xdpyinfo, "-display", display],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={
                **os.environ,
                "DISPLAY": display,
                "XAUTHORITY": str(authority_path),
            },
        )
        if probe.returncode == 0:
            return True
        time.sleep(0.05)
    return False


def run_gui_smoke() -> Dict[str, Any]:
    xvfb = shutil.which("Xvfb")
    xauth = shutil.which("xauth")
    xdpyinfo = shutil.which("xdpyinfo")
    if xvfb is None or xauth is None or xdpyinfo is None:
        return {
            "argv": ["Xvfb", sys.executable, "-m", "ourd_gui"],
            "returncode": None,
            "ok": True,
            "skipped": True,
            "stdout": "",
            "stderr": "Xvfb, xauth, or xdpyinfo unavailable; headless GUI smoke skipped",
        }
    attempts = []
    for _ in range(3):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# GUI validation fixture\n", encoding="utf-8")
            authority_path = root / "Xauthority"
            authority_path.touch(mode=0o600)
            display_number = _available_tcp_display()
            display = f"127.0.0.1:{display_number}"
            cookie = hashlib.sha256(
                f"{os.getpid()}:{time.monotonic_ns()}:{root}".encode("utf-8")
            ).hexdigest()[:32]
            authority = run_command(
                [
                    xauth,
                    "-f",
                    str(authority_path),
                    "add",
                    display,
                    "MIT-MAGIC-COOKIE-1",
                    cookie,
                ],
                REPO_ROOT,
            )
            if not authority["ok"]:
                authority["skipped"] = False
                authority["transport"] = "authenticated-tcp"
                return authority
            server_log = root / "xvfb.log"
            server_argv = xvfb_server_argv(xvfb, display_number, authority_path)
            application_argv = [
                sys.executable,
                "-m",
                "ourd_gui",
                "--repo",
                str(root),
                "--smoke-test",
            ]
            with server_log.open("w", encoding="utf-8") as server_output:
                server = subprocess.Popen(
                    server_argv,
                    cwd=REPO_ROOT,
                    text=True,
                    stdout=server_output,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, "XAUTHORITY": str(authority_path)},
                )
                try:
                    ready = _wait_for_x_display(
                        server,
                        xdpyinfo,
                        display,
                        authority_path,
                    )
                    if ready:
                        result = run_command(
                            application_argv,
                            REPO_ROOT,
                            env_overrides={
                                "DISPLAY": display,
                                "XAUTHORITY": str(authority_path),
                            },
                        )
                    else:
                        result = {
                            "argv": application_argv,
                            "returncode": None,
                            "ok": False,
                            "stdout": "",
                            "stderr": "Xvfb did not become ready within 5 seconds",
                        }
                finally:
                    if server.poll() is None:
                        server.terminate()
                        try:
                            server.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            server.kill()
                            server.wait(timeout=3)
            x_server_stderr = server_log.read_text(encoding="utf-8", errors="replace")
            result["skipped"] = False
            result["transport"] = "authenticated-tcp"
            result["display"] = display
            result["xvfb_argv"] = server_argv
            result["xvfb_returncode"] = server.returncode
            result["xvfb_output"] = x_server_stderr[-8192:]
            attempts.append(
                {
                    "application_returncode": result["returncode"],
                    "xvfb_returncode": server.returncode,
                    "stderr": result["stderr"],
                    "xvfb_output": x_server_stderr[-2048:],
                }
            )
            if result["ok"]:
                result["attempts"] = attempts
                return result
    result["attempts"] = attempts
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate OIEC-STM-Agent")
    parser.add_argument("--live-llama-cpp", action="store_true")
    parser.add_argument("--model", default="qwen3.8-27b-direct")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument("--max-output-tokens", type=int, default=700)
    parser.add_argument("--context-budget", type=int, default=6000)
    parser.add_argument("--runtime-context-tokens", type=int, default=8192)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--runner-path", default="")
    parser.add_argument("--model-path", default="")
    parser.add_argument("--expected-model-sha256", default="")
    parser.add_argument("--llama-cpp-root", default="")
    parser.add_argument("--llama-cpp-build-dir", default="")
    parser.add_argument("--llama-grammar-dir", default="")
    parser.add_argument("--llama-context", type=int, default=8192)
    parser.add_argument("--llama-gpu-layers", type=int, default=-1)
    parser.add_argument("--llama-threads", type=int, default=0)
    parser.add_argument("--llama-seed", type=int, default=1234)
    parser.add_argument("--llama-temperature-bp", type=int, default=1000)
    parser.add_argument("--llama-top-p-bp", type=int, default=9500)
    parser.add_argument("--llama-top-k", type=int, default=40)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-report", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    checks = [
        run_gui_smoke(),
        run_command([sys.executable, "-m", "py_compile", *python_files(REPO_ROOT)], REPO_ROOT),
        run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], REPO_ROOT),
        run_command([sys.executable, "-c", "import ourd, ourd_agent; print('imports: PASS')"], REPO_ROOT),
    ]
    live = None
    live_error = ""
    if args.live_llama_cpp:
        try:
            live = run_live_llama_cpp(args)
        except Exception as exc:
            live_error = f"{type(exc).__name__}: {exc}"
    deterministic_ok = all(check["ok"] for check in checks)
    live_ok = not args.live_llama_cpp or (
        live is not None and live.get("ok") and not live.get("changed_files")
    )
    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "repository": str(REPO_ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "dependency_availability": {
            "setuptools": importlib.util.find_spec("setuptools") is not None,
        },
        "workspace_snapshot_hash": Workspace(REPO_ROOT).snapshot_hash(),
        "source_hashes": source_hashes(REPO_ROOT),
        "deterministic_checks": checks,
        "deterministic_ok": deterministic_ok,
        "live_llama_cpp_requested": args.live_llama_cpp,
        "live_llama_cpp": live,
        "live_llama_cpp_error": live_error,
        "live_llama_cpp_ok": live_ok,
        "overall_ok": deterministic_ok and live_ok,
    }
    if not args.no_report:
        report_path = args.report
        if report_path is None:
            timestamp = report["generated_at"].replace(":", "").replace("-", "")
            report_path = REPO_ROOT / ".ourd-agent" / "evidence" / f"validation-{timestamp}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)
    print(json.dumps(report, indent=2))
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
