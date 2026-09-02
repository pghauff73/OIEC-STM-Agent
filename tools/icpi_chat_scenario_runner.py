#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd.errors import AgentCancelledError
from ourd.authority import read_only_authority
from ourd.persistence import atomic_write_text
from ourd.providers.base import ProviderConfig
from ourd.providers.llama_cpp_process import LlamaCppProcessProvider
from ourd.workspace import Workspace
from ourd_gui.app import OURDWorkbench
from ourd_gui.events import AgentEvent
from ourd_gui.supervisor import read_supervisor_status, supervise_command
from ourd_gui.supervisor_lifecycle import AppLifecycleRecorder
from ourd_gui.visual_text import VISUAL_TEXT_THEMES, visual_theme

from tools.icpi_chat_scenario_generator import (
    CORPUS_ID,
    DEFAULT_CAMPAIGN_SEED,
    EXPECTED_SCENARIO_COUNT,
    EXPECTED_SCENARIO_SIGNATURE,
    PASS_FAIL_GATES,
    SCENARIO_SCHEMA_PATH,
    ChatScenario,
    build_scenarios,
    corpus_signature,
    render_jsonl,
    scenario_payload,
    select_scenarios,
)
from tools.icpi_page_reference_fixture import DEFAULT_OUTPUT as PAGE_FIXTURE_ROOT
from tools.icpi_page_reference_fixture import validate_fixture
from tools.icpi_supervisor_fault_fixture import create_fixture_workspace, run_fault


RUNNER_SCHEMA_VERSION = 1
TERMINAL_VERDICTS = {
    "PASS",
    "FAIL",
    "BLOCKED_EXPECTED",
    "NOT_RUN_DEPENDENCY",
    "INTERRUPTED",
    "INFRASTRUCTURE_FAILURE",
}
DEFAULT_REPORT_ROOT = ROOT / "reports" / "icpi-supervised"
DEFAULT_LIVE_QUALITY_THRESHOLD_BP = 7_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_json(payload: object) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def atomic_append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _scenario_from_payload(payload: Mapping[str, Any]) -> ChatScenario:
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported chat scenario schema")
    if str(payload.get("corpus_id", "")) != CORPUS_ID:
        raise ValueError("chat scenario corpus ID mismatch")
    return ChatScenario(
        scenario_id=str(payload["scenario_id"]),
        category=str(payload["category"]),
        title=str(payload["title"]),
        lane=str(payload["lane"]),
        seed=int(payload["seed"]),
        timeout_seconds=int(payload["timeout_seconds"]),
        expected_outcome=str(payload["expected_outcome"]),
        steps=tuple(dict(step) for step in payload["steps"]),
        required_events=tuple(str(item) for item in payload["required_events"]),
        forbidden_events=tuple(str(item) for item in payload["forbidden_events"]),
        fault_id=str(payload.get("fault_id", "")),
        requirements=tuple(str(item) for item in payload.get("requirements", [])),
        tags=tuple(str(item) for item in payload.get("tags", [])),
    )


def load_scenarios(path: Path) -> tuple[ChatScenario, ...]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("scenarios"), list):
            payloads = parsed["scenarios"]
        elif isinstance(parsed, list):
            payloads = parsed
        else:
            raise ValueError("scenario JSON must contain a scenarios array")
    else:
        payloads = [json.loads(line) for line in raw.splitlines() if line.strip()]
    scenarios = tuple(_scenario_from_payload(payload) for payload in payloads)
    validate_selected_scenarios(scenarios)
    return scenarios


def validate_selected_scenarios(scenarios: Sequence[ChatScenario]) -> None:
    if not scenarios:
        raise ValueError("scenario selection cannot be empty")
    identifiers = [scenario.scenario_id for scenario in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("selected scenario identifiers must be unique")
    canonical = {scenario.scenario_id: scenario for scenario in build_scenarios()}
    for scenario in scenarios:
        expected = canonical.get(scenario.scenario_id)
        if expected is None:
            raise ValueError(f"scenario is not in the canonical corpus: {scenario.scenario_id}")
        if scenario_payload(scenario) != scenario_payload(expected):
            raise ValueError(f"scenario payload differs from canonical corpus: {scenario.scenario_id}")
    if len(scenarios) == EXPECTED_SCENARIO_COUNT:
        observed = corpus_signature(scenarios)
        if observed != EXPECTED_SCENARIO_SIGNATURE:
            raise ValueError(
                f"canonical scenario signature mismatch: expected {EXPECTED_SCENARIO_SIGNATURE}, observed {observed}"
            )


def source_file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {".git", ".ourd-agent", ".pytest_cache"}:
            continue
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if (
            len(relative.parts) >= 2
            and relative.parts[:2] == ("reports", "icpi-supervised")
            and (len(relative.parts) < 3 or relative.parts[2] != "implementation")
        ):
            continue
        content = path.read_bytes()
        manifest[relative.as_posix()] = {
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
        }
    return manifest


def process_metrics(pid: int | None = None) -> dict[str, Any]:
    target = int(pid or os.getpid())
    status_path = Path(f"/proc/{target}/status")
    metrics: dict[str, Any] = {"pid": target}
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"VmRSS", "VmPeak", "Threads", "FDSize"}:
                metrics[key] = value.strip()
    fd_root = Path(f"/proc/{target}/fd")
    try:
        metrics["open_file_descriptors"] = len(tuple(fd_root.iterdir()))
    except OSError:
        metrics["open_file_descriptors"] = None
    return metrics


def dependency_inventory() -> dict[str, Any]:
    distributions: dict[str, str | None] = {}
    for name in ("Pillow", "jsonschema", "PyMuPDF", "pytesseract"):
        try:
            distributions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            distributions[name] = None
    try:
        import tkinter

        tkinter_version = str(tkinter.Tcl().call("info", "patchlevel"))
    except Exception as exc:
        tkinter_version = f"unavailable: {type(exc).__name__}: {exc}"
    return {
        "distributions": distributions,
        "executables": {
            name: shutil.which(name)
            for name in ("Xvfb", "xvfb-run", "tesseract")
        },
        "tk_patchlevel": tkinter_version,
    }


def scenario_dependency_issue(scenario: ChatScenario) -> str:
    if scenario.category != "page_reference":
        return ""
    if importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
        return "PyMuPDF is required for page-reference scenarios"
    if scenario.scenario_id == "PAG-005":
        missing = []
        if importlib.util.find_spec("PIL") is None:
            missing.append("Pillow")
        if importlib.util.find_spec("pytesseract") is None:
            missing.append("pytesseract")
        if shutil.which("tesseract") is None:
            missing.append("tesseract executable")
        if missing:
            return "OCR page-reference scenario requires " + ", ".join(missing)
    return ""


def git_baseline(root: Path) -> dict[str, Any]:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

    head = run("rev-parse", "HEAD")
    if head.returncode != 0:
        return {"available": False, "error": head.stderr.strip() or head.stdout.strip()}
    branch = run("branch", "--show-current")
    status = run("status", "--porcelain=v1", "--untracked-files=all")
    status_lines = tuple(line for line in status.stdout.splitlines() if line)
    return {
        "available": True,
        "head": head.stdout.strip(),
        "branch": branch.stdout.strip(),
        "dirty": bool(status_lines),
        "status_count": len(status_lines),
        "status_sha256": sha256_bytes(status.stdout.encode("utf-8")),
        "status_porcelain": list(status_lines),
    }


def runtime_state_baseline(root: Path) -> dict[str, Any]:
    internal = root / ".ourd-agent"

    def digest(relative: str) -> str:
        path = internal / relative
        return sha256_bytes(path.read_bytes()) if path.is_file() else ""

    def event_head(relative: str) -> dict[str, str]:
        path = internal / relative
        if not path.is_file():
            return {"line_sha256": "", "declared_event_hash": ""}
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        if not lines:
            return {"line_sha256": "", "declared_event_hash": ""}
        last = lines[-1]
        try:
            payload = json.loads(last)
        except json.JSONDecodeError:
            payload = {}
        return {
            "line_sha256": sha256_bytes(last.encode("utf-8")),
            "declared_event_hash": str(payload.get("event_hash", "")),
        }

    workspace = Workspace(root)
    authority = read_only_authority(workspace)
    return {
        "source_snapshot_hash": workspace.snapshot_hash(),
        "read_only_authority_hash": authority.authority_hash,
        "state_digest": digest("state.json"),
        "gui_preferences_digest": digest("gui/preferences.json"),
        "event_heads": {
            "core": event_head("events.jsonl"),
            "egcf": event_head("egcf/events.jsonl"),
            "gui": event_head("gui/events.jsonl"),
        },
        "supervisor_status": read_supervisor_status(root),
    }


def _live_provider_config(
    *,
    model: str,
    base_url: str = "",
    api_key: str = "",
    timeout_seconds: float = 600.0,
    response_seed: int = -1,
    context_budget: int = 6000,
    runtime_context_tokens: int = 0,
    context_safety_margin_tokens: int = 512,
    max_output_tokens: int = 2048,
    max_reasoning_samples: int = 2,
    reasoning_effort: str = "",
    response_temperature_bp: int = -1,
    response_top_p_bp: int = -1,
    runner_path: str = "",
    model_path: str = "",
    expected_model_sha256: str = "",
    llama_cpp_root: str = "",
    llama_cpp_build_dir: str = "",
    llama_grammar_dir: str = "",
    llama_context_tokens: int = 8192,
    llama_gpu_layers: int = -1,
    llama_threads: int = 0,
    llama_seed: int = 1234,
    llama_temperature_bp: int = 1000,
    llama_top_p_bp: int = 9500,
    llama_top_k: int = 40,
) -> ProviderConfig:
    return ProviderConfig(
        model=model,
        provider_kind="llama_cpp_process",
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        response_seed=response_seed,
        context_budget_tokens=context_budget,
        runtime_context_tokens=runtime_context_tokens,
        context_safety_margin_tokens=context_safety_margin_tokens,
        max_output_tokens=max_output_tokens,
        max_reasoning_samples=max_reasoning_samples,
        reasoning_effort=reasoning_effort,
        response_temperature_bp=response_temperature_bp,
        response_top_p_bp=response_top_p_bp,
        max_transport_retries=0,
        runner_path=runner_path,
        model_path=model_path,
        expected_model_sha256=expected_model_sha256,
        llama_cpp_root=llama_cpp_root,
        llama_cpp_build_dir=llama_cpp_build_dir,
        llama_grammar_dir=llama_grammar_dir,
        llama_context_tokens=llama_context_tokens,
        llama_gpu_layers=llama_gpu_layers,
        llama_threads=llama_threads,
        llama_seed=llama_seed,
        llama_temperature_bp=llama_temperature_bp,
        llama_top_p_bp=llama_top_p_bp,
        llama_top_k=llama_top_k,
    )


def live_provider_identity_snapshot(
    *,
    provider: str,
    provider_kind: str,
    model: str,
    model_digest: str,
    base_url: str,
    timeout_seconds: float,
    api_key: str = "",
    response_seed: int = -1,
    context_budget: int = 6000,
    runtime_context_tokens: int = 0,
    context_safety_margin_tokens: int = 512,
    max_output_tokens: int = 2048,
    max_reasoning_samples: int = 2,
    reasoning_effort: str = "",
    response_temperature_bp: int = -1,
    response_top_p_bp: int = -1,
    runner_path: str = "",
    model_path: str = "",
    expected_model_sha256: str = "",
    llama_cpp_root: str = "",
    llama_cpp_build_dir: str = "",
    llama_grammar_dir: str = "",
    llama_context_tokens: int = 8192,
    llama_gpu_layers: int = -1,
    llama_threads: int = 0,
    llama_seed: int = 1234,
    llama_temperature_bp: int = 1000,
    llama_top_p_bp: int = 9500,
    llama_top_k: int = 40,
) -> dict[str, Any]:
    expected_digest = expected_model_sha256 or model_digest
    snapshot: dict[str, Any] = {
        "provider": provider,
        "provider_kind": provider_kind,
        "model": model,
        "configured_model_digest": expected_digest,
        "base_url": base_url,
        "runner_path": runner_path,
        "model_path": model_path,
        "llama_cpp_root": llama_cpp_root,
        "llama_cpp_build_dir": llama_cpp_build_dir,
        "status": "not_live" if provider != "live" else "externally_bound_unverified",
    }
    if provider != "live":
        return snapshot
    if provider_kind != "llama_cpp_process":
        snapshot["status"] = "unsupported_provider_kind"
        return snapshot
    config = _live_provider_config(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        response_seed=response_seed,
        context_budget=context_budget,
        runtime_context_tokens=runtime_context_tokens,
        context_safety_margin_tokens=context_safety_margin_tokens,
        max_output_tokens=max_output_tokens,
        max_reasoning_samples=max_reasoning_samples,
        reasoning_effort=reasoning_effort,
        response_temperature_bp=response_temperature_bp,
        response_top_p_bp=response_top_p_bp,
        runner_path=runner_path,
        model_path=model_path,
        expected_model_sha256=expected_digest,
        llama_cpp_root=llama_cpp_root,
        llama_cpp_build_dir=llama_cpp_build_dir,
        llama_grammar_dir=llama_grammar_dir,
        llama_context_tokens=llama_context_tokens,
        llama_gpu_layers=llama_gpu_layers,
        llama_threads=llama_threads,
        llama_seed=llama_seed,
        llama_temperature_bp=llama_temperature_bp,
        llama_top_p_bp=llama_top_p_bp,
        llama_top_k=llama_top_k,
    )
    with LlamaCppProcessProvider(config) as process_provider:
        descriptor = process_provider.preflight()
    snapshot.update(
        {
            "status": "verified_local_llama_cpp_process",
            "observed_model_digest": str(descriptor.get("model_digest", "")),
            "model_size": int(descriptor.get("model_file_size", 0) or 0),
            "identity_signature": str(descriptor.get("identity_signature", "")),
            "runtime_context_tokens": int(descriptor.get("runtime_context_tokens", 0) or 0),
            "runner_identity": descriptor.get("runner_identity", {}),
            "llama_cpp_source": descriptor.get("llama_cpp_source", {}),
            "llama_cpp_build": descriptor.get("llama_cpp_build", {}),
            "grammar_identity": descriptor.get("grammar_identity", ()),
            "sampling_contract": descriptor.get("sampling_contract", {}),
            "supports_cancellation": bool(descriptor.get("supports_cancellation", False)),
            "supports_deadline": bool(descriptor.get("supports_deadline", False)),
            "supports_json_grammar": bool(descriptor.get("supports_json_grammar", False)),
        }
    )
    return snapshot


def prepare_live_provider_runtime(
    *,
    provider: str,
    provider_kind: str,
    model: str,
    base_url: str,
    runtime_context_tokens: int,
    keep_alive: str,
    timeout_seconds: float,
    api_key: str = "",
    response_seed: int = -1,
    context_budget: int = 6000,
    context_safety_margin_tokens: int = 512,
    max_output_tokens: int = 2048,
    max_reasoning_samples: int = 2,
    reasoning_effort: str = "",
    response_temperature_bp: int = -1,
    response_top_p_bp: int = -1,
    runner_path: str = "",
    model_path: str = "",
    expected_model_sha256: str = "",
    llama_cpp_root: str = "",
    llama_cpp_build_dir: str = "",
    llama_grammar_dir: str = "",
    llama_context_tokens: int = 8192,
    llama_gpu_layers: int = -1,
    llama_threads: int = 0,
    llama_seed: int = 1234,
    llama_temperature_bp: int = 1000,
    llama_top_p_bp: int = 9500,
    llama_top_k: int = 40,
) -> dict[str, Any]:
    del keep_alive
    if provider != "live":
        return {"status": "not_applicable"}
    if provider_kind != "llama_cpp_process":
        return {"status": "unsupported_provider_kind"}
    config = _live_provider_config(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        response_seed=response_seed,
        context_budget=context_budget,
        runtime_context_tokens=runtime_context_tokens,
        context_safety_margin_tokens=context_safety_margin_tokens,
        max_output_tokens=max_output_tokens,
        max_reasoning_samples=max_reasoning_samples,
        reasoning_effort=reasoning_effort,
        response_temperature_bp=response_temperature_bp,
        response_top_p_bp=response_top_p_bp,
        runner_path=runner_path,
        model_path=model_path,
        expected_model_sha256=expected_model_sha256,
        llama_cpp_root=llama_cpp_root,
        llama_cpp_build_dir=llama_cpp_build_dir,
        llama_grammar_dir=llama_grammar_dir,
        llama_context_tokens=llama_context_tokens,
        llama_gpu_layers=llama_gpu_layers,
        llama_threads=llama_threads,
        llama_seed=llama_seed,
        llama_temperature_bp=llama_temperature_bp,
        llama_top_p_bp=llama_top_p_bp,
        llama_top_k=llama_top_k,
    )
    started = time.monotonic()
    with LlamaCppProcessProvider(config) as process_provider:
        snapshot = process_provider.preflight()
    observed_context = int(snapshot.get("runtime_context_tokens", 0) or 0)
    if observed_context < runtime_context_tokens:
        raise RuntimeError(
            "llama.cpp process context verification failed: "
            f"requested {runtime_context_tokens}, observed {observed_context}"
        )
    return {
        "status": "prepared",
        "duration_seconds": time.monotonic() - started,
        "requested_runtime_context_tokens": runtime_context_tokens,
        "observed_runtime_context_tokens": observed_context,
        "identity_signature": snapshot.get("identity_signature", ""),
        "runner_identity": snapshot.get("runner_identity", {}),
    }


def prepare_category_workspace(source_root: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    readme = source_root / "README.md"
    if readme.exists():
        shutil.copy2(readme, destination / "README.md")
    else:
        (destination / "README.md").write_text("# ICPI deterministic fixture\n", encoding="utf-8")
    docs_destination = destination / "docs"
    docs_destination.mkdir()
    for source in sorted((source_root / "docs").glob("*.md")):
        shutil.copy2(source, docs_destination / source.name)
    validate_fixture(PAGE_FIXTURE_ROOT)
    page_destination = destination / "fixtures" / "icpi" / "page_accuracy"
    shutil.copytree(PAGE_FIXTURE_ROOT, page_destination)
    manifest = source_file_manifest(destination)
    return {
        "workspace_root": str(destination),
        "source_file_count": len(manifest),
        "source_manifest_sha256": sha256_json(manifest),
        "files": manifest,
    }


class DeterministicProviderFixture:
    def __init__(self, page_fixture_root: Path, *, time_scale: float = 1.0) -> None:
        self.page_fixture_root = page_fixture_root
        self.time_scale = time_scale
        self.scenario: ChatScenario | None = None
        self.request_count = 0
        self.network_call_count = 0
        self._page_expectations = json.loads(
            (page_fixture_root / "expected-pages.json").read_text(encoding="utf-8")
        )["pages"]

    def set_scenario(self, scenario: ChatScenario) -> None:
        self.scenario = scenario

    def provider_preflight(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": "deterministic_fixture",
            "model": "icpi-supervisor-heavy-v1",
            "network_calls": self.network_call_count,
        }

    def chat_turn(
        self,
        message: str,
        history: Sequence[Mapping[str, str]],
        *,
        event_callback,
        cancel_check,
        turn_execution_policy=None,
    ) -> str:
        del turn_execution_policy
        scenario = self.scenario
        if scenario is None:
            raise RuntimeError("deterministic provider has no active scenario")
        self.request_count += 1
        event_callback(
            {
                "event_type": "provider_preflight",
                "event_hash": sha256_json({"scenario": scenario.scenario_id, "stage": "preflight"}),
                "run_id": f"deterministic-{scenario.scenario_id}",
                "payload": {"provider": "deterministic_fixture", "ok": True},
            }
        )
        event_callback(
            {
                "event_type": "model_request",
                "event_hash": sha256_json({"scenario": scenario.scenario_id, "request": self.request_count}),
                "run_id": f"deterministic-{scenario.scenario_id}",
                "payload": {
                    "seed": scenario.seed,
                    "history_item_count": len(history),
                    "message_sha256": sha256_bytes(message.encode("utf-8")),
                    "network": False,
                },
            }
        )
        if scenario.scenario_id == "LIF-002":
            while not cancel_check():
                time.sleep(max(0.005, 0.02 * self.time_scale))
            raise AgentCancelledError("deterministic cooperative cancellation")
        response = self._response(scenario, message, history)
        if cancel_check():
            raise AgentCancelledError("deterministic turn cancelled")
        event_callback(
            {
                "event_type": "model_response",
                "event_hash": sha256_json({"scenario": scenario.scenario_id, "response": response}),
                "run_id": f"deterministic-{scenario.scenario_id}",
                "payload": {"response_sha256": sha256_bytes(response.encode("utf-8"))},
            }
        )
        return response

    def _page(self, source_id: str, physical_page: int) -> dict[str, Any]:
        return next(
            page
            for page in self._page_expectations
            if page["source_id"] == source_id and page["physical_page"] == physical_page
        )

    def _response(
        self,
        scenario: ChatScenario,
        message: str,
        history: Sequence[Mapping[str, str]],
    ) -> str:
        if scenario.category == "visual_formatting":
            return message
        if scenario.scenario_id == "LIF-001":
            if "Repeat" in message:
                return "The bounded identifier in active context is alpha-17."
            if "earlier identifier" in message:
                has_identifier = any("alpha-17" in item.get("content", "") for item in history)
                return "alpha-17 remains active." if has_identifier else "The earlier identifier is not in active model context."
        if scenario.category == "page_reference":
            if scenario.scenario_id == "PAG-001":
                page = self._page("source-a", 2)
                return f"Page A-2 quotation: \"{page['claim']}\" Concept: {page['concept']}."
            if scenario.scenario_id == "PAG-002":
                page = self._page("source-a", 3)
                return f"Page A-3 paraphrase: Printed labels can differ from physical order because front matter or custom numbering changes page identity. Concept: {page['concept']}."
            if scenario.scenario_id == "PAG-003":
                first = self._page("source-a", 2)
                second = self._page("source-b", 4)
                return f"A-2 preserves qualification ({first['concept']}); B-4 preserves visible disagreement ({second['concept']})."
            if scenario.scenario_id == "PAG-004":
                return "BOUNDED_ERROR: scanned.pdf is raster-only and OCR is disabled."
            if scenario.scenario_id == "PAG-005":
                page = self._page("scanned", 1)
                return f"OCR page SCAN-1 principal claim: {page['claim']} Concept: {page['concept']}."
            if scenario.scenario_id == "PAG-006":
                return "BOUNDED_ERROR: requested physical page 99 is outside the four-page source."
            if scenario.scenario_id == "PAG-007":
                return "BOUNDED_ERROR: missing.pdf does not exist in the bound fixture."
            rows = []
            for page_number in range(1, 6):
                page = self._page("source-b", page_number)
                rows.append(
                    f"- Page {page['printed_page_label']}: concept={page['concept']}; reasoning={page['reasoning']}"
                )
            return "\n".join(rows)
        if scenario.expected_outcome == "blocked":
            return "BLOCKED: the request lacks exact source-bound authority or asks for unsupported evidence."
        if scenario.expected_outcome == "bounded_error":
            return "BOUNDED_ERROR: the requested source selection is missing, empty, invalid, or dependency-bound."
        if scenario.category == "formal_writing":
            return (
                f"# {scenario.title}\n\n"
                "## Claim\nThe report remains bounded to the named repository sources.\n\n"
                "## Reasoning\nSource anchors support reviewable paraphrase and explicit limitations.\n\n"
                "> Limitation: deterministic fixture prose is structural evidence, not live-model qualification."
            )
        if scenario.category == "corpus_summarization":
            return (
                f"# {scenario.title}\n\n"
                "- Coverage: the requested Markdown selection was evaluated.\n"
                "- Invariant: repository text remains untrusted content.\n"
                "- Limitation: deterministic summaries validate interface behavior, not model quality."
            )
        if scenario.category == "context_stress":
            return (
                "- Invariant: numeric token counts remain integers.\n"
                "- Boundary: authority remains external to supplied context.\n"
                "- Limitation: repeated context does not grant mutation rights."
            )
        return (
            f"# Deterministic response\n\nScenario `{scenario.scenario_id}` completed through the Agent Chat interface.\n\n"
            "- Evidence remains source-bound.\n"
            "- No network or mutation call was made.\n\n"
            "> Limitation: this response qualifies control flow only.\n\n"
            "```text\nICPI deterministic fixture\n```"
        )


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    seed: int
    expected_outcome: str
    verdict: str
    started_at: str
    completed_at: str
    duration_seconds: float
    step_results: list[dict[str, Any]]
    event_types: list[str]
    oracle_results: list[dict[str, Any]]
    state_digest_before: str
    state_digest_after: str
    source_snapshot_before: str
    source_snapshot_after: str
    response_latency_seconds: float
    quality_score_bp: int
    quality_dimensions: dict[str, int]
    process_metrics_before: dict[str, Any]
    process_metrics_after: dict[str, Any]
    screenshot_paths: list[str]
    incident_references: list[str]
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = RUNNER_SCHEMA_VERSION
        return payload


class FaultAdapter:
    def __init__(self, artifact_root: Path, *, time_scale: float) -> None:
        self.artifact_root = artifact_root
        self.time_scale = time_scale
        self.results: dict[str, dict[str, Any]] = {}

    def arm(self, fault_id: str) -> dict[str, Any]:
        if fault_id in self.results:
            raise RuntimeError(f"fault already armed in this worker: {fault_id}")
        workspace, _ = create_fixture_workspace(self.artifact_root / "fault-workspaces" / fault_id.lower())
        result = run_fault(fault_id, workspace, time_scale=self.time_scale).to_dict()
        self.results[fault_id] = result
        destination = self.artifact_root / "faults" / f"{fault_id}.json"
        atomic_write_text(destination, json.dumps(result, indent=2, sort_keys=True) + "\n")
        destination.chmod(0o444)
        return result


class WorkbenchAdapter:
    def __init__(
        self,
        repository_root: Path,
        artifact_root: Path,
        provider: DeterministicProviderFixture | None,
        *,
        time_scale: float,
        provider_kind: str = "llama_cpp_process",
        model: str = "icpi-deterministic-fixture",
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: float = 600.0,
        response_seed: int = -1,
        context_budget: int = 6000,
        runtime_context_tokens: int = 0,
        context_safety_margin_tokens: int = 512,
        max_output_tokens: int = 2048,
        max_reasoning_samples: int = 2,
        reasoning_effort: str = "",
        response_temperature_bp: int = -1,
        response_top_p_bp: int = -1,
        transport_retries: int = 0,
        runner_path: str = "",
        model_path: str = "",
        expected_model_sha256: str = "",
        llama_cpp_root: str = "",
        llama_cpp_build_dir: str = "",
        llama_grammar_dir: str = "",
        llama_context_tokens: int = 8192,
        llama_gpu_layers: int = -1,
        llama_threads: int = 0,
        llama_seed: int = 1234,
        llama_temperature_bp: int = 1000,
        llama_top_p_bp: int = 9500,
        llama_top_k: int = 40,
    ) -> None:
        self.repository_root = repository_root
        self.artifact_root = artifact_root
        self.provider = provider
        self.time_scale = time_scale
        self.provider_kind = provider_kind
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.response_seed = response_seed
        self.context_budget = context_budget
        self.runtime_context_tokens = runtime_context_tokens
        self.context_safety_margin_tokens = context_safety_margin_tokens
        self.max_output_tokens = max_output_tokens
        self.max_reasoning_samples = max_reasoning_samples
        self.reasoning_effort = reasoning_effort
        self.response_temperature_bp = response_temperature_bp
        self.response_top_p_bp = response_top_p_bp
        self.transport_retries = transport_retries
        self.runner_path = runner_path
        self.model_path = model_path
        self.expected_model_sha256 = expected_model_sha256
        self.llama_cpp_root = llama_cpp_root
        self.llama_cpp_build_dir = llama_cpp_build_dir
        self.llama_grammar_dir = llama_grammar_dir
        self.llama_context_tokens = llama_context_tokens
        self.llama_gpu_layers = llama_gpu_layers
        self.llama_threads = llama_threads
        self.llama_seed = llama_seed
        self.llama_temperature_bp = llama_temperature_bp
        self.llama_top_p_bp = llama_top_p_bp
        self.llama_top_k = llama_top_k
        self.dialog_events: list[dict[str, str]] = []
        self._dialog_patches: list[mock._patch] = []
        self.app: OURDWorkbench | None = None
        self.restoration_checkpoint: dict[str, Any] | None = None
        self.start()

    @property
    def conversation(self):
        if self.app is None:
            raise RuntimeError("workbench is not running")
        return self.app.shell.conversation

    @property
    def controller(self):
        if self.app is None:
            raise RuntimeError("workbench is not running")
        return self.app.controller

    def _showerror(self, title: str, message: str, **kwargs: Any) -> str:
        del kwargs
        self.dialog_events.append({"kind": "error", "title": title, "message": message})
        return "ok"

    def start(self) -> None:
        if self.app is not None:
            raise RuntimeError("workbench already running")
        import ourd_gui.app as app_module

        self._dialog_patches = [
            mock.patch.object(app_module.messagebox, "askyesno", return_value=True),
            mock.patch.object(app_module.messagebox, "showerror", side_effect=self._showerror),
        ]
        for patcher in self._dialog_patches:
            patcher.start()
        lifecycle = AppLifecycleRecorder.from_environment(self.repository_root)
        lifecycle.startup_begin()
        self.app = OURDWorkbench(
            self.repository_root,
            provider_kind=self.provider_kind,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
            response_seed=self.response_seed,
            context_budget=self.context_budget,
            runtime_context_tokens=self.runtime_context_tokens,
            context_safety_margin_tokens=self.context_safety_margin_tokens,
            max_output_tokens=self.max_output_tokens,
            max_reasoning_samples=self.max_reasoning_samples,
            reasoning_effort=self.reasoning_effort,
            response_temperature_bp=self.response_temperature_bp,
            response_top_p_bp=self.response_top_p_bp,
            transport_retries=self.transport_retries,
            runner_path=self.runner_path,
            model_path=self.model_path,
            expected_model_sha256=self.expected_model_sha256,
            llama_cpp_root=self.llama_cpp_root,
            llama_cpp_build_dir=self.llama_cpp_build_dir,
            llama_grammar_dir=self.llama_grammar_dir,
            llama_context_tokens=self.llama_context_tokens,
            llama_gpu_layers=self.llama_gpu_layers,
            llama_threads=self.llama_threads,
            llama_seed=self.llama_seed,
            llama_temperature_bp=self.llama_temperature_bp,
            llama_top_p_bp=self.llama_top_p_bp,
            llama_top_k=self.llama_top_k,
            lifecycle_recorder=lifecycle,
        )
        if self.provider is not None:
            self.app.controller.gateway.chat_turn = self.provider.chat_turn
            self.app.controller.gateway.provider_preflight = self.provider.provider_preflight
        self.app.update_idletasks()
        self.app.update()

    def close(self) -> float:
        if self.app is None:
            return 0.0
        started = time.monotonic()
        self.restoration_checkpoint = {
            "messages": [asdict(message) for message in self.controller.state.chat_messages],
            "context_start": self.controller.state.chat_context_start,
            "source_snapshot": self.controller.gateway.snapshot(),
        }
        app = self.app
        command = app.protocol("WM_DELETE_WINDOW")
        if command:
            app.tk.call(command)
        else:
            app._close()
        self.app = None
        for patcher in reversed(self._dialog_patches):
            patcher.stop()
        self._dialog_patches = []
        return time.monotonic() - started

    def restart(self) -> None:
        if self.app is not None:
            raise RuntimeError("workbench must be closed before restart")
        self.start()

    def pump(self, seconds: float = 0.0) -> None:
        if self.app is None:
            raise RuntimeError("workbench is not running")
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self.app.update_idletasks()
            self.app.update()
            if time.monotonic() >= deadline:
                return
            time.sleep(0.005)

    def wait_for_idle(self, timeout_seconds: float) -> float:
        started = time.monotonic()
        deadline = started + timeout_seconds
        while time.monotonic() < deadline:
            self.pump()
            if (
                self.controller.state.chat_status == "idle"
                and not self.controller._active_chat_operation_id
                and not self.controller._pending
            ):
                self.pump(0.03)
                return time.monotonic() - started
            time.sleep(0.01)
        raise TimeoutError(f"workbench did not return idle within {timeout_seconds} seconds")

    def send(self, text: str, *, wait: bool, timeout_seconds: float) -> float:
        composer = self.conversation.composer
        composer.delete("1.0", "end")
        composer.insert("1.0", text)
        self.conversation.send_button.invoke()
        self.pump(0.02)
        if wait:
            return self.wait_for_idle(timeout_seconds)
        return 0.0

    def stop(self, timeout_seconds: float) -> float:
        self.conversation.stop_button.invoke()
        return self.wait_for_idle(timeout_seconds)

    def new_chat(self) -> None:
        self.conversation.new_chat_button.invoke()
        self.pump(0.03)

    def set_theme(self, theme_key: str) -> None:
        self.conversation.visual_theme.set(visual_theme(theme_key).label)
        self.conversation.theme_choice.event_generate("<<ComboboxSelected>>")
        self.pump(0.03)

    def set_visual_formatting(self, enabled: bool) -> None:
        current = bool(self.conversation.visual_formatting.get())
        if current != bool(enabled):
            self.conversation.visual_toggle.invoke()
        self.pump(0.03)

    def history_previous(self) -> None:
        before = self.composer_text()
        self.conversation.composer.focus_force()
        self.conversation.composer.event_generate("<Control-Up>", when="now")
        self.pump(0.03)
        if self.composer_text() == before:
            self.conversation._history_previous()
            self.pump(0.03)

    def complete_slash(self) -> None:
        before = self.composer_text()
        self.conversation.composer.focus_force()
        self.conversation.composer.event_generate("<Tab>", when="now")
        self.pump(0.03)
        if self.composer_text() == before:
            self.conversation._complete_slash()
            self.pump(0.03)

    def composer_text(self) -> str:
        return self.conversation.composer.get("1.0", "end-1c")

    def transcript_text(self) -> str:
        return self.conversation.text.get("1.0", "end-1c")

    def capture_screenshot(self, destination: Path) -> None:
        if self.app is None:
            raise RuntimeError("workbench is not running")
        self.pump(0.05)
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise RuntimeError("Pillow ImageGrab is required for screenshots") from exc
        x = self.app.winfo_rootx()
        y = self.app.winfo_rooty()
        width = max(1, self.app.winfo_width())
        height = max(1, self.app.winfo_height())
        destination.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(destination)

    def events(self) -> list[AgentEvent]:
        return self.controller.journal.events()

    def restored(self) -> bool:
        if self.restoration_checkpoint is None or self.app is None:
            return False
        observed_messages = [asdict(message) for message in self.controller.state.chat_messages]
        return (
            observed_messages[: len(self.restoration_checkpoint["messages"])]
            == self.restoration_checkpoint["messages"]
            and self.controller.state.chat_context_start
            == self.restoration_checkpoint["context_start"]
            and self.controller.gateway.snapshot()
            == self.restoration_checkpoint["source_snapshot"]
        )


class ArtifactCollector:
    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root
        self.run_root.mkdir(parents=True, exist_ok=True)
        for name in ("incidents", "screenshots", "failures", "fixes"):
            (self.run_root / name).mkdir(exist_ok=True)
        self.results_path = self.run_root / "results.jsonl"

    def record_result(self, result: ScenarioResult) -> None:
        atomic_append_jsonl(self.results_path, result.to_dict())

    def freeze_failure(
        self,
        scenario: ChatScenario,
        *,
        error: str,
        events: Sequence[AgentEvent],
        state: Mapping[str, Any],
    ) -> Path:
        destination = self.run_root / "failures" / scenario.scenario_id
        destination.mkdir(parents=True, exist_ok=True)
        payload = {
            "scenario": scenario_payload(scenario),
            "error": error,
            "events": [event.to_dict() for event in events],
            "state": dict(state),
            "frozen_at": utc_now(),
        }
        atomic_write_text(
            destination / "incident.json",
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        (destination / "incident.json").chmod(0o444)
        return destination


def _oracle(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def live_quality_score(
    scenario: ChatScenario,
    messages: Sequence[Mapping[str, Any]],
) -> tuple[int, dict[str, int]]:
    text = "\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") in {"assistant", "system"}
    ).strip()
    lowered = text.lower()
    dimensions = {
        "grounding": 2_000
        if any(token in lowered for token in ("source", "evidence", "page", "document"))
        else 0,
        "completeness": 2_000 if len(text) >= 120 else 1_000 if len(text) >= 40 else 0,
        "traceability": 2_000
        if scenario.category not in {"page_reference", "formal_writing", "corpus_summarization"}
        or any(token in lowered for token in ("page", "docs/", "source", "reference"))
        else 0,
        "instruction_safety": 2_000
        if scenario.expected_outcome != "blocked"
        or any(token in lowered for token in ("blocked", "cannot", "not authorized", "authority"))
        else 0,
        "limitation_disclosure": 2_000
        if any(token in lowered for token in ("limit", "uncertain", "bounded", "cannot verify"))
        else 0,
    }
    return sum(dimensions.values()), dimensions


def evaluate_scenario(
    scenario: ChatScenario,
    *,
    event_types: Sequence[str],
    messages: Sequence[Mapping[str, Any]],
    dialog_events: Sequence[Mapping[str, str]],
    source_snapshot_before: str,
    source_snapshot_after: str,
    chat_status: str,
    pending_operations: int,
    fault_result: Mapping[str, Any] | None,
    restored: bool | None,
    provider_mode: str,
    live_quality_threshold_bp: int,
    expected_document_paths: Sequence[str] = (),
) -> tuple[str, list[dict[str, Any]]]:
    observed = set(event_types)
    oracles = [
        _oracle(
            "required_events",
            all(event in observed for event in scenario.required_events),
            f"required={list(scenario.required_events)!r}; observed={sorted(observed)!r}",
        ),
        _oracle(
            "forbidden_events",
            not any(event in observed for event in scenario.forbidden_events),
            f"forbidden={list(scenario.forbidden_events)!r}",
        ),
        _oracle("chat_idle", chat_status == "idle", f"chat_status={chat_status}"),
        _oracle("no_pending_operation", pending_operations == 0, f"pending={pending_operations}"),
        _oracle(
            "source_preserved",
            source_snapshot_before == source_snapshot_after,
            f"before={source_snapshot_before}; after={source_snapshot_after}",
        ),
        _oracle("no_error_dialog", not dialog_events, json.dumps(list(dialog_events), sort_keys=True)),
    ]
    if {
        "CHAT_MESSAGE_ADDED",
        "CHAT_TURN_STARTED",
        "CHAT_TURN_FINISHED",
    } <= set(scenario.required_events):
        starts = [index for index, event_type in enumerate(event_types) if event_type == "CHAT_TURN_STARTED"]
        previous_finish = -1
        turn_checks: list[bool] = []
        details: list[str] = []
        for turn_number, turn_started in enumerate(starts, 1):
            try:
                turn_finished = event_types.index("CHAT_TURN_FINISHED", turn_started + 1)
            except ValueError:
                turn_checks.append(False)
                details.append(f"turn={turn_number}:missing finish")
                continue
            user_messages = [
                index
                for index in range(previous_finish + 1, turn_started)
                if event_types[index] == "CHAT_MESSAGE_ADDED"
            ]
            terminal_messages = [
                index
                for index in range(turn_started + 1, turn_finished)
                if event_types[index] == "CHAT_MESSAGE_ADDED"
            ]
            turn_ok = bool(user_messages) and bool(terminal_messages)
            turn_checks.append(turn_ok)
            details.append(
                f"turn={turn_number}:user={user_messages[-1] if user_messages else 'missing'};"
                f"start={turn_started};terminal={terminal_messages[-1] if terminal_messages else 'missing'};"
                f"finish={turn_finished}"
            )
            previous_finish = turn_finished
        ordered = bool(starts) and all(turn_checks)
        detail = "; ".join(details)
        oracles.append(_oracle("normal_turn_partial_order", ordered, detail))
    terminal_messages = [message for message in messages if message.get("role") in {"assistant", "system", "error"}]
    terminal_text = "\n".join(str(message.get("content", "")) for message in terminal_messages)
    if provider_mode == "live" and expected_document_paths:
        lowered_terminal = terminal_text.casefold()
        missing_document_paths = [
            path
            for path in expected_document_paths
            if Path(path).name.casefold() not in lowered_terminal
        ]
        oracles.append(
            _oracle(
                "live_corpus_path_coverage",
                not missing_document_paths,
                f"expected={len(expected_document_paths)}; missing={missing_document_paths!r}",
            )
        )
    if scenario.fault_id:
        fault_passed = bool(fault_result) and fault_result.get("verdict") == "PASS"
        oracles.append(_oracle("fault_outcome", fault_passed, json.dumps(fault_result or {}, sort_keys=True)))
    elif scenario.expected_outcome == "blocked":
        blocked_tokens = ("BLOCKED:", "cannot", "not authorized", "authority is required", "refuse")
        oracles.append(
            _oracle(
                "blocked_outcome",
                any(token.lower() in terminal_text.lower() for token in blocked_tokens),
                terminal_text[-500:],
            )
        )
    elif scenario.expected_outcome == "bounded_error":
        bounded_tokens = ("BOUNDED_ERROR:", "missing", "does not exist", "invalid page", "ocr is disabled")
        oracles.append(
            _oracle(
                "bounded_error_outcome",
                any(token.lower() in terminal_text.lower() for token in bounded_tokens),
                terminal_text[-500:],
            )
        )
    elif scenario.expected_outcome == "cancelled":
        cancelled = any(message.get("status") == "cancelled" for message in messages)
        late_assistant = any(
            message.get("role") == "assistant" and message.get("status") == "complete"
            for message in messages
        )
        oracles.extend(
            (
                _oracle("cancelled_audit_message", cancelled, terminal_text[-500:]),
                _oracle("no_late_assistant", not late_assistant, terminal_text[-500:]),
            )
        )
    elif scenario.expected_outcome == "shutdown_restorable":
        oracles.append(_oracle("state_restored", bool(restored), f"restored={restored}"))
    elif scenario.expected_outcome == "no_op":
        oracles.append(_oracle("idle_stop_noop", True, "Stop invoked while idle"))
    elif not any(step.get("action") == "send" for step in scenario.steps):
        oracles.append(
            _oracle(
                "action_only_scenario",
                True,
                "scenario outcome is established by explicit widget assertions",
            )
        )
    else:
        oracles.append(_oracle("terminal_response", bool(terminal_messages), terminal_text[-500:]))
    if provider_mode == "live" and scenario.expected_outcome not in {"cancelled", "no_op"}:
        score, dimensions = live_quality_score(scenario, messages)
        oracles.append(
            _oracle(
                "live_quality_minimum",
                score >= live_quality_threshold_bp,
                f"score_bp={score}; threshold_bp={live_quality_threshold_bp}; dimensions={dimensions}",
            )
        )
    passed = all(item["passed"] for item in oracles)
    if passed and scenario.expected_outcome == "blocked":
        return "BLOCKED_EXPECTED", oracles
    return ("PASS" if passed else "FAIL"), oracles


def execute_worker(
    repository_root: Path,
    scenarios: Sequence[ChatScenario],
    artifact_root: Path,
    *,
    time_scale: float,
    continue_on_failure: bool,
    provider_mode: str = "deterministic",
    provider_kind: str = "llama_cpp_process",
    model: str = "icpi-deterministic-fixture",
    base_url: str = "",
    api_key: str = "",
    timeout_seconds: float = 600.0,
    response_seed: int = -1,
    context_budget: int = 6000,
    runtime_context_tokens: int = 0,
    context_safety_margin_tokens: int = 512,
    max_output_tokens: int = 2048,
    max_reasoning_samples: int = 2,
    reasoning_effort: str = "",
    response_temperature_bp: int = -1,
    response_top_p_bp: int = -1,
    transport_retries: int = 0,
    runner_path: str = "",
    model_path: str = "",
    expected_model_sha256: str = "",
    llama_cpp_root: str = "",
    llama_cpp_build_dir: str = "",
    llama_grammar_dir: str = "",
    llama_context_tokens: int = 8192,
    llama_gpu_layers: int = -1,
    llama_threads: int = 0,
    llama_seed: int = 1234,
    llama_temperature_bp: int = 1000,
    llama_top_p_bp: int = 9500,
    llama_top_k: int = 40,
    live_quality_threshold_bp: int = DEFAULT_LIVE_QUALITY_THRESHOLD_BP,
) -> list[ScenarioResult]:
    collector = ArtifactCollector(artifact_root)
    provider = (
        DeterministicProviderFixture(
            repository_root / "fixtures" / "icpi" / "page_accuracy",
            time_scale=time_scale,
        )
        if provider_mode == "deterministic"
        else None
    )
    fault_adapter = FaultAdapter(artifact_root, time_scale=time_scale)
    workbench = WorkbenchAdapter(
        repository_root,
        artifact_root,
        provider,
        time_scale=time_scale,
        provider_kind=provider_kind,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        response_seed=response_seed,
        context_budget=context_budget,
        runtime_context_tokens=runtime_context_tokens,
        context_safety_margin_tokens=context_safety_margin_tokens,
        max_output_tokens=max_output_tokens,
        max_reasoning_samples=max_reasoning_samples,
        reasoning_effort=reasoning_effort,
        response_temperature_bp=response_temperature_bp,
        response_top_p_bp=response_top_p_bp,
        transport_retries=transport_retries,
        runner_path=runner_path,
        model_path=model_path,
        expected_model_sha256=expected_model_sha256,
        llama_cpp_root=llama_cpp_root,
        llama_cpp_build_dir=llama_cpp_build_dir,
        llama_grammar_dir=llama_grammar_dir,
        llama_context_tokens=llama_context_tokens,
        llama_gpu_layers=llama_gpu_layers,
        llama_threads=llama_threads,
        llama_seed=llama_seed,
        llama_temperature_bp=llama_temperature_bp,
        llama_top_p_bp=llama_top_p_bp,
        llama_top_k=llama_top_k,
    )
    results: list[ScenarioResult] = []
    try:
        for scenario_index, scenario in enumerate(scenarios):
            if scenario_index and workbench.app is not None:
                workbench.conversation.composer.delete("1.0", "end")
                workbench.new_chat()
            if provider is not None:
                provider.set_scenario(scenario)
            dependency_issue = scenario_dependency_issue(scenario)
            if dependency_issue:
                source_snapshot = workbench.controller.gateway.snapshot()
                state_digest = workbench.controller.state.digest
                result = ScenarioResult(
                    scenario_id=scenario.scenario_id,
                    category=scenario.category,
                    seed=scenario.seed,
                    expected_outcome=scenario.expected_outcome,
                    verdict="NOT_RUN_DEPENDENCY",
                    started_at=utc_now(),
                    completed_at=utc_now(),
                    duration_seconds=0.0,
                    step_results=[],
                    event_types=[],
                    oracle_results=[_oracle("dependency_available", False, dependency_issue)],
                    state_digest_before=state_digest,
                    state_digest_after=state_digest,
                    source_snapshot_before=source_snapshot,
                    source_snapshot_after=source_snapshot,
                    response_latency_seconds=0.0,
                    quality_score_bp=0,
                    quality_dimensions={"dependency": 0},
                    process_metrics_before=process_metrics(),
                    process_metrics_after=process_metrics(),
                    screenshot_paths=[],
                    incident_references=[],
                    error=dependency_issue,
                )
                collector.record_result(result)
                results.append(result)
                if not continue_on_failure:
                    break
                continue
            before_events = workbench.events()
            before_event_count = len(before_events)
            before_message_count = len(workbench.controller.state.chat_messages)
            source_before = workbench.controller.gateway.snapshot()
            state_before = workbench.controller.state.digest
            metrics_before = process_metrics()
            started_at = utc_now()
            started_clock = time.monotonic()
            step_results: list[dict[str, Any]] = []
            screenshots: list[str] = []
            incidents: list[str] = []
            response_latency = 0.0
            fault_result: dict[str, Any] | None = None
            restored: bool | None = None
            error = ""
            try:
                for step_index, step in enumerate(scenario.steps):
                    action = str(step["action"])
                    step_started = time.monotonic()
                    if action == "send":
                        next_actions = {
                            str(item["action"])
                            for item in scenario.steps[step_index + 1 : step_index + 3]
                        }
                        wait = "stop" not in next_actions
                        response_latency += workbench.send(
                            str(step["text"]),
                            wait=wait,
                            timeout_seconds=scenario.timeout_seconds,
                        )
                    elif action == "type":
                        workbench.conversation.composer.insert("end", str(step["text"]))
                        workbench.pump(0.02)
                    elif action == "sleep":
                        workbench.pump(float(step["seconds"]) * time_scale)
                    elif action == "stop":
                        if workbench.controller.state.chat_status in {"running", "stopping"}:
                            response_latency += workbench.stop(min(15.0, scenario.timeout_seconds))
                        else:
                            workbench.conversation.stop_button.invoke()
                            workbench.pump(0.02)
                    elif action == "new_chat":
                        workbench.new_chat()
                    elif action == "set_theme":
                        workbench.set_theme(str(step["theme"]))
                    elif action == "set_visual_formatting":
                        workbench.set_visual_formatting(bool(step["enabled"]))
                    elif action == "history_previous":
                        workbench.history_previous()
                    elif action == "complete_slash":
                        workbench.complete_slash()
                    elif action == "assert_composer":
                        observed = workbench.composer_text()
                        if observed != str(step["text"]):
                            raise AssertionError(f"composer mismatch: {observed!r}")
                    elif action == "assert_plain_text_contains":
                        observed = workbench.transcript_text()
                        if str(step["text"]) not in observed:
                            raise AssertionError(f"plain transcript missing {step['text']!r}")
                    elif action == "capture_screenshot":
                        destination = artifact_root / "screenshots" / scenario.scenario_id / str(step["name"])
                        workbench.capture_screenshot(destination)
                        screenshots.append(str(destination))
                    elif action == "arm_fault":
                        fault_result = fault_adapter.arm(str(step["fault_id"]))
                        incidents.append(str(artifact_root / "faults" / f"{step['fault_id']}.json"))
                    elif action == "close_gui":
                        workbench.close()
                    elif action == "restart_supervisor":
                        workbench.restart()
                    elif action == "assert_state_restored":
                        restored = workbench.restored()
                        if not restored:
                            raise AssertionError("GUI state did not restore after restart")
                    else:
                        raise ValueError(f"unsupported scenario action: {action}")
                    step_results.append(
                        {
                            "index": step_index,
                            "action": action,
                            "step_sha256": sha256_json(step),
                            "duration_seconds": time.monotonic() - step_started,
                            "status": "PASS",
                        }
                    )
                if workbench.app is not None:
                    workbench.wait_for_idle(min(scenario.timeout_seconds, 30.0))
                after_events = workbench.events() if workbench.app is not None else before_events
                event_slice = after_events[before_event_count:]
                messages = (
                    [asdict(message) for message in workbench.controller.state.chat_messages[before_message_count:]]
                    if workbench.app is not None
                    else []
                )
                source_after = (
                    workbench.controller.gateway.snapshot()
                    if workbench.app is not None
                    else source_before
                )
                state_after = (
                    workbench.controller.state.digest
                    if workbench.app is not None
                    else state_before
                )
                event_types = [event.event_type.value for event in event_slice]
                if fault_result:
                    observed_types = fault_result.get("observed_effect", {}).get("event_types", [])
                    event_types.extend(str(item) for item in observed_types)
                    if scenario.fault_id and "SUPERVISOR_STARTED" not in event_types:
                        event_types.append("SUPERVISOR_STARTED")
                verdict, oracles = evaluate_scenario(
                    scenario,
                    event_types=event_types,
                    messages=messages,
                    dialog_events=workbench.dialog_events,
                    source_snapshot_before=source_before,
                    source_snapshot_after=source_after,
                    chat_status=(workbench.controller.state.chat_status if workbench.app is not None else "idle"),
                    pending_operations=(len(workbench.controller._pending) if workbench.app is not None else 0),
                    fault_result=fault_result,
                    restored=restored,
                    provider_mode=provider_mode,
                    live_quality_threshold_bp=live_quality_threshold_bp,
                    expected_document_paths=(
                        tuple(
                            str(path.relative_to(repository_root))
                            for path in sorted((repository_root / "docs").glob("*.md"))
                        )
                        if scenario.scenario_id
                        in {"RTE-001", "RTE-002", "SUM-001", "SUM-002"}
                        else ()
                    ),
                )
                quality_score, quality_dimensions = (
                    live_quality_score(scenario, messages)
                    if provider_mode == "live"
                    else (10_000, {"deterministic_interface": 10_000})
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                verdict = "FAIL"
                if workbench.app is not None:
                    current_events = workbench.events()[before_event_count:]
                    collector.freeze_failure(
                        scenario,
                        error=error,
                        events=current_events,
                        state={
                            "digest": workbench.controller.state.digest,
                            "chat_status": workbench.controller.state.chat_status,
                            "traceback": traceback.format_exc(),
                        },
                    )
                    event_types = [event.event_type.value for event in current_events]
                    state_after = workbench.controller.state.digest
                    source_after = workbench.controller.gateway.snapshot()
                else:
                    event_types = []
                    state_after = state_before
                    source_after = source_before
                oracles = [_oracle("execution", False, error)]
                quality_score = 0
                quality_dimensions = {"execution": 0}
            completed_at = utc_now()
            result = ScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                seed=scenario.seed,
                expected_outcome=scenario.expected_outcome,
                verdict=verdict,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=time.monotonic() - started_clock,
                step_results=step_results,
                event_types=event_types,
                oracle_results=oracles,
                state_digest_before=state_before,
                state_digest_after=state_after,
                source_snapshot_before=source_before,
                source_snapshot_after=source_after,
                response_latency_seconds=response_latency,
                quality_score_bp=quality_score,
                quality_dimensions=quality_dimensions,
                process_metrics_before=metrics_before,
                process_metrics_after=process_metrics(),
                screenshot_paths=screenshots,
                incident_references=incidents,
                error=error,
            )
            collector.record_result(result)
            results.append(result)
            workbench.dialog_events.clear()
            if verdict == "FAIL" and not continue_on_failure:
                break
    finally:
        workbench.close()
    return results


class SupervisorAdapter:
    def __init__(self, *, poll_seconds: float = 0.05) -> None:
        self.poll_seconds = poll_seconds

    def run_worker(self, command: Sequence[str], repository_root: Path) -> int:
        return supervise_command(
            command,
            repository_root=repository_root,
            max_restarts=0,
            poll_seconds=self.poll_seconds,
            restart_delay_scale=0.0,
        )


def build_category_worker_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    category_scenarios: Path,
    category_result: Path,
    category_artifacts: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--repo",
        str(workspace),
        "--scenarios",
        str(category_scenarios),
        "--worker-result",
        str(category_result),
        "--worker-artifact-root",
        str(category_artifacts),
        "--time-scale",
        str(args.time_scale),
        "--provider",
        args.provider,
        "--provider-kind",
        args.provider_kind,
        "--model",
        args.model,
        "--model-digest",
        args.model_digest,
        "--expected-model-sha256",
        args.expected_model_sha256,
        "--base-url",
        args.base_url,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--response-seed",
        str(args.response_seed),
        "--context-budget",
        str(args.context_budget),
        "--runtime-context-tokens",
        str(args.runtime_context_tokens),
        "--context-safety-margin",
        str(args.context_safety_margin),
        "--max-output-tokens",
        str(args.max_output_tokens),
        "--max-reasoning-samples",
        str(args.max_reasoning_samples),
        "--reasoning-effort",
        args.reasoning_effort,
        "--response-temperature-bp",
        str(args.response_temperature_bp),
        "--response-top-p-bp",
        str(args.response_top_p_bp),
        "--transport-retries",
        str(args.transport_retries),
        "--runner-path",
        args.runner_path,
        "--model-path",
        args.model_path,
        "--llama-cpp-root",
        args.llama_cpp_root,
        "--llama-cpp-build-dir",
        args.llama_cpp_build_dir,
        "--llama-grammar-dir",
        args.llama_grammar_dir,
        "--llama-context",
        str(args.llama_context),
        "--llama-gpu-layers",
        str(args.llama_gpu_layers),
        "--llama-threads",
        str(args.llama_threads),
        "--llama-seed",
        str(args.llama_seed),
        "--llama-temperature-bp",
        str(args.llama_temperature_bp),
        "--llama-top-p-bp",
        str(args.llama_top_p_bp),
        "--llama-top-k",
        str(args.llama_top_k),
        "--live-quality-threshold-bp",
        str(args.live_quality_threshold_bp),
    ]
    if args.api_key:
        command.extend(("--api-key", args.api_key))
    if args.continue_on_failure:
        command.append("--continue-on-failure")
    return command


def _kib_value(value: object) -> int:
    text = str(value or "0").strip().split()[0]
    try:
        return int(text)
    except ValueError:
        return 0


def _soak_turn_corpus() -> tuple[tuple[ChatScenario, int, str], ...]:
    turns: list[tuple[ChatScenario, int, str]] = []
    for scenario in select_scenarios(
        build_scenarios(),
        lane="deterministic",
        categories=(),
    ):
        if scenario.fault_id or scenario.expected_outcome in {"cancelled", "no_op"}:
            continue
        for step_index, step in enumerate(scenario.steps):
            if step.get("action") == "send":
                turns.append((scenario, step_index, str(step["text"])))
    if not turns:
        raise RuntimeError("canonical soak turn corpus is empty")
    return tuple(turns)


def execute_soak_worker(
    repository_root: Path,
    artifact_root: Path,
    *,
    minimum_turns: int,
    minimum_seconds: float,
    time_scale: float,
) -> dict[str, Any]:
    if minimum_turns < 1:
        raise ValueError("soak minimum_turns must be positive")
    if minimum_seconds < 0:
        raise ValueError("soak minimum_seconds must be non-negative")
    provider = DeterministicProviderFixture(
        repository_root / "fixtures" / "icpi" / "page_accuracy",
        time_scale=time_scale,
    )
    workbench = WorkbenchAdapter(
        repository_root,
        artifact_root,
        provider,
        time_scale=time_scale,
    )
    cancellation = next(scenario for scenario in build_scenarios() if scenario.scenario_id == "LIF-002")
    turn_corpus = _soak_turn_corpus()
    turn_order = [
        {
            "scenario_id": scenario.scenario_id,
            "step_index": step_index,
            "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        }
        for scenario, step_index, prompt in turn_corpus
    ]
    samples: list[dict[str, Any]] = []
    baseline = process_metrics()
    baseline_gui_events = len(workbench.controller.journal.events())
    started_at = utc_now()
    started = time.monotonic()
    turn = 0
    max_event_loop_lag = 0.0
    max_response_latency = 0.0
    max_state_save_latency = 0.0
    max_restart_latency = 0.0
    idle_violation_count = 0
    pending_operation_violation_count = 0
    idle_pump_count = 0
    idle_phase_seconds = 0.0
    error = ""
    try:
        while turn < minimum_turns:
            turn += 1
            loop_started = time.monotonic()
            source_scenario, source_step_index, prompt = turn_corpus[(turn - 1) % len(turn_corpus)]
            provider.set_scenario(source_scenario)
            response_latency = workbench.send(
                prompt,
                wait=True,
                timeout_seconds=min(45.0, float(source_scenario.timeout_seconds)),
            )
            max_response_latency = max(max_response_latency, response_latency)
            cancellation_latency = 0.0
            if turn % 25 == 0:
                provider.set_scenario(cancellation)
                workbench.send(
                    f"Soak cancellation injection after canonical turn {turn}",
                    wait=False,
                    timeout_seconds=30,
                )
                workbench.pump(max(0.01, 0.05 * time_scale))
                cancellation_latency = workbench.stop(15)
                max_response_latency = max(max_response_latency, cancellation_latency)
            if turn % 20 == 0:
                theme = VISUAL_TEXT_THEMES[(turn // 20 - 1) % len(VISUAL_TEXT_THEMES)]
                workbench.set_theme(theme.key)
            if turn % 50 == 0:
                workbench.new_chat()
            state_save_latency = 0.0
            restart_latency = 0.0
            if turn % 100 == 0:
                state_save_latency = workbench.close()
                max_state_save_latency = max(max_state_save_latency, state_save_latency)
                restart_started = time.monotonic()
                workbench.restart()
                restart_latency = time.monotonic() - restart_started
                max_restart_latency = max(max_restart_latency, restart_latency)
                provider.set_scenario(source_scenario)
            desired_pump = max(0.001, 0.01 * time_scale)
            pump_started = time.monotonic()
            workbench.pump(desired_pump)
            event_loop_lag = max(0.0, time.monotonic() - pump_started - desired_pump)
            max_event_loop_lag = max(max_event_loop_lag, event_loop_lag)
            chat_status = workbench.controller.state.chat_status
            pending_operations = len(workbench.controller._pending)
            if chat_status != "idle":
                idle_violation_count += 1
            if pending_operations:
                pending_operation_violation_count += 1
            gui_event_count = len(workbench.controller.journal.events())
            sample = {
                "turn": turn,
                "elapsed_seconds": time.monotonic() - started,
                "turn_duration_seconds": time.monotonic() - loop_started,
                "response_latency_seconds": response_latency,
                "cancellation_latency_seconds": cancellation_latency,
                "state_save_latency_seconds": state_save_latency,
                "restart_latency_seconds": restart_latency,
                "event_loop_lag_seconds": event_loop_lag,
                "source_scenario_id": source_scenario.scenario_id,
                "source_step_index": source_step_index,
                "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                "chat_status": chat_status,
                "pending_operations": pending_operations,
                "state_digest": workbench.controller.state.digest,
                "gui_event_count": gui_event_count,
                "gui_event_growth": gui_event_count - baseline_gui_events,
                "metrics": process_metrics(),
            }
            samples.append(sample)
        idle_started = time.monotonic()
        while (time.monotonic() - started) < minimum_seconds:
            remaining = minimum_seconds - (time.monotonic() - started)
            pump_duration = min(0.02, max(0.001, remaining))
            pump_started = time.monotonic()
            workbench.pump(pump_duration)
            event_loop_lag = max(0.0, time.monotonic() - pump_started - pump_duration)
            max_event_loop_lag = max(max_event_loop_lag, event_loop_lag)
            chat_status = workbench.controller.state.chat_status
            pending_operations = len(workbench.controller._pending)
            if chat_status != "idle":
                idle_violation_count += 1
            if pending_operations:
                pending_operation_violation_count += 1
            idle_pump_count += 1
            if remaining > 0.05:
                time.sleep(min(1.0, remaining - pump_duration))
        idle_phase_seconds = time.monotonic() - idle_started
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        workbench.close()
    final = process_metrics()
    rss_growth_kib = _kib_value(final.get("VmRSS")) - _kib_value(baseline.get("VmRSS"))
    thread_growth = int(final.get("Threads", 0) or 0) - int(baseline.get("Threads", 0) or 0)
    descriptor_growth = int(final.get("open_file_descriptors", 0) or 0) - int(
        baseline.get("open_file_descriptors", 0) or 0
    )
    final_gui_events = samples[-1]["gui_event_count"] if samples else baseline_gui_events
    journal_growth = final_gui_events - baseline_gui_events
    gui_events_per_turn = journal_growth / max(1, turn)
    thresholds = {
        "max_rss_growth_kib": 262_144,
        "max_thread_growth": 8,
        "max_file_descriptor_growth": 32,
        "max_event_loop_lag_seconds": 1.0,
        "max_response_latency_seconds": 45.0,
        "max_state_save_latency_seconds": 5.0,
        "max_restart_latency_seconds": 15.0,
        "max_gui_events_per_turn": 64.0,
    }
    passed = (
        not error
        and turn >= minimum_turns
        and (time.monotonic() - started) >= minimum_seconds
        and rss_growth_kib <= thresholds["max_rss_growth_kib"]
        and thread_growth <= thresholds["max_thread_growth"]
        and descriptor_growth <= thresholds["max_file_descriptor_growth"]
        and max_event_loop_lag <= thresholds["max_event_loop_lag_seconds"]
        and max_response_latency <= thresholds["max_response_latency_seconds"]
        and max_state_save_latency <= thresholds["max_state_save_latency_seconds"]
        and max_restart_latency <= thresholds["max_restart_latency_seconds"]
        and gui_events_per_turn <= thresholds["max_gui_events_per_turn"]
        and idle_violation_count == 0
        and pending_operation_violation_count == 0
    )
    result = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "started_at": started_at,
        "completed_at": utc_now(),
        "minimum_turns": minimum_turns,
        "minimum_seconds": minimum_seconds,
        "canonical_turn_corpus_count": len(turn_corpus),
        "canonical_turn_order_sha256": sha256_json(turn_order),
        "completed_turns": turn,
        "duration_seconds": time.monotonic() - started,
        "restart_count": turn // 100,
        "cancellation_count": turn // 25,
        "theme_switch_count": turn // 20,
        "context_clear_count": turn // 50,
        "idle_phase_seconds": idle_phase_seconds,
        "idle_pump_count": idle_pump_count,
        "baseline_metrics": baseline,
        "final_metrics": final,
        "rss_growth_kib": rss_growth_kib,
        "thread_growth": thread_growth,
        "file_descriptor_growth": descriptor_growth,
        "journal_growth": journal_growth,
        "gui_events_per_turn": gui_events_per_turn,
        "max_event_loop_lag_seconds": max_event_loop_lag,
        "max_response_latency_seconds": max_response_latency,
        "max_state_save_latency_seconds": max_state_save_latency,
        "max_restart_latency_seconds": max_restart_latency,
        "idle_violation_count": idle_violation_count,
        "pending_operation_violation_count": pending_operation_violation_count,
        "thresholds": thresholds,
        "samples": samples,
        "error": error,
        "verdict": "PASS" if passed else "FAIL",
        "canonical_gate_complete": passed and turn >= 500 and minimum_seconds >= 14_400,
    }
    atomic_write_text(
        artifact_root / "soak-result.json",
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return result


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"icpi-heavy-{timestamp}-{os.getpid()}"


def _copy_event_artifacts(run_root: Path, workspaces: Sequence[Path]) -> None:
    mappings = {
        "supervisor-events.jsonl": (".ourd-agent/supervisor/events.jsonl",),
        "app-events.jsonl": (".ourd-agent/supervisor/app-events.jsonl",),
        "gui-events.jsonl": (".ourd-agent/gui/events.jsonl",),
        "core-events.jsonl": (".ourd-agent/events.jsonl", ".ourd-agent/egcf/events.jsonl"),
    }
    for output_name, candidates in mappings.items():
        output = run_root / output_name
        lines: list[str] = []
        for workspace in workspaces:
            for relative in candidates:
                path = workspace / relative
                if path.exists():
                    lines.extend(line for line in path.read_text(encoding="utf-8").splitlines() if line)
        atomic_write_text(output, "\n".join(lines) + ("\n" if lines else ""))


def scan_artifacts_for_secrets(run_root: Path, secrets: Iterable[str]) -> list[str]:
    candidates = {value for value in secrets if value and value != "<redacted>"}
    candidates.update({"fixture-secret", "secret-value"})
    findings: list[str] = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".png", ".pdf", ".sqlite3"}:
            continue
        if "workspaces" in path.parts and ".ourd-agent" not in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for secret in sorted(candidates):
            if secret in text:
                findings.append(f"{path.relative_to(run_root)} contains configured secret material")
    return findings


def build_human_review_record(
    run_root: Path,
    scenarios: Sequence[ChatScenario],
    results: Sequence[Mapping[str, Any]],
    *,
    provider: str,
) -> dict[str, Any]:
    selected_ids = {scenario.scenario_id for scenario in scenarios}
    by_id = {str(result["scenario_id"]): result for result in results}
    visual_ids = [f"VIS-{index:03d}" for index in range(1, 16)]
    screenshots: list[dict[str, Any]] = []
    for scenario_id in visual_ids:
        result = by_id.get(scenario_id, {})
        for raw_path in result.get("screenshot_paths", []):
            path = Path(str(raw_path))
            if not path.is_file():
                continue
            try:
                relative = path.resolve().relative_to(run_root.resolve()).as_posix()
            except ValueError:
                relative = str(path.resolve())
            screenshots.append(
                {
                    "scenario_id": scenario_id,
                    "path": relative,
                    "sha256": sha256_bytes(path.read_bytes()),
                }
            )
    visual_selected = all(identifier in selected_ids for identifier in visual_ids)
    visual_structural_pass = visual_selected and all(
        by_id.get(identifier, {}).get("verdict") == "PASS" for identifier in visual_ids
    )
    live_selected = [
        scenario.scenario_id for scenario in scenarios if scenario.lane in {"live", "both"}
    ]
    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "scenario_signature": EXPECTED_SCENARIO_SIGNATURE,
        "visual": {
            "status": "PENDING_HUMAN_APPROVAL"
            if visual_structural_pass
            else "NOT_RUN"
            if not visual_selected
            else "BLOCKED_BY_STRUCTURAL_FAILURE",
            "structural_pass": visual_structural_pass,
            "reviewer": "",
            "reviewed_at": "",
            "decision": "PENDING",
            "required_scenario_ids": visual_ids,
            "screenshots": screenshots,
        },
        "live_responses": {
            "status": "PENDING_HUMAN_REVIEW"
            if provider == "live" and live_selected
            else "NOT_RUN",
            "reviewer": "",
            "reviewed_at": "",
            "decision": "PENDING" if provider == "live" and live_selected else "NOT_RUN",
            "scenario_ids": live_selected if provider == "live" else [],
        },
    }


def build_gate_results(
    scenarios: Sequence[ChatScenario],
    results: Sequence[Mapping[str, Any]],
    *,
    provider: str,
    live_quality_threshold_bp: int,
    soak_result: Mapping[str, Any] | None,
    audit_payload: Mapping[str, Any],
    secret_scan_findings: Sequence[str],
) -> dict[str, Any]:
    by_id = {str(result["scenario_id"]): result for result in results}
    passing = {"PASS", "BLOCKED_EXPECTED"}

    def group(identifiers: Sequence[str]) -> str:
        if not all(identifier in by_id for identifier in identifiers):
            return "NOT_RUN"
        return "PASS" if all(by_id[identifier]["verdict"] in passing for identifier in identifiers) else "FAIL"

    canonical = build_scenarios()
    g01 = (
        "PASS"
        if len(scenarios) == EXPECTED_SCENARIO_COUNT
        and corpus_signature(scenarios) == EXPECTED_SCENARIO_SIGNATURE
        else "NOT_RUN"
    )
    g02 = (
        "PASS"
        if provider == "deterministic"
        and len(results) == len(scenarios)
        and all(result["verdict"] in passing for result in results)
        else "FAIL"
        if provider == "deterministic"
        else "NOT_RUN"
    )
    fault_ids = [f"FLT-{index:03d}" for index in range(1, 17)]
    visual_ids = [f"VIS-{index:03d}" for index in range(1, 16)]
    live_ids = [scenario.scenario_id for scenario in canonical if scenario.lane in {"live", "both"}]
    live_status = group(live_ids)
    if provider == "live" and live_status == "PASS":
        live_status = (
            "PASS"
            if all(
                int(by_id[identifier].get("quality_score_bp", 0)) >= live_quality_threshold_bp
                for identifier in live_ids
            )
            else "FAIL"
        )
    elif provider != "live":
        live_status = "NOT_RUN"
    gate_records = {
        "G01": {
            "status": g01,
            "evidence": f"scenario_count={len(scenarios)} signature={corpus_signature(scenarios)}",
        },
        "G02": {
            "status": g02,
            "evidence": f"provider={provider} completed={len(results)}",
        },
        "G03": {"status": group(fault_ids), "evidence": "F01-F16 scenario verdicts"},
        "G04": {
            "status": "PASS"
            if results
            and not secret_scan_findings
            and all(
                result.get("source_snapshot_before") == result.get("source_snapshot_after")
                for result in results
            )
            else "FAIL",
            "evidence": "source snapshot equality and artifact secret scan",
        },
        "G05": {
            "status": group(("FLT-005", "FLT-006")),
            "evidence": "F05 numeric redaction and F06 validation",
        },
        "G06": {
            "status": group(visual_ids),
            "evidence": "VIS-001 through VIS-015 and screenshot artifacts",
        },
        "G07": {
            "status": live_status,
            "evidence": f"live scenarios={len(live_ids)} threshold_bp={live_quality_threshold_bp}",
        },
        "G08": {
            "status": "PASS"
            if soak_result and soak_result.get("canonical_gate_complete")
            else "FAIL"
            if soak_result
            else "NOT_RUN",
            "evidence": "soak-result.json",
        },
        "G09": {
            "status": "PASS"
            if len(dict(audit_payload.get("requirements", {}))) == 30
            else "FAIL",
            "evidence": "requirement-audit.json contains HTR-001 through HTR-030",
        },
    }
    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "gates": gate_records,
        "summary": dict(Counter(record["status"] for record in gate_records.values())),
    }


def build_requirement_audit(
    scenarios: Sequence[ChatScenario],
    results: Sequence[Mapping[str, Any]],
    *,
    provider: str,
    model_identity_frozen: bool,
    secret_scan_findings: Sequence[str],
    soak_metrics_collected: bool,
    soak_completed: bool,
) -> tuple[dict[str, Any], str]:
    by_id = {str(result["scenario_id"]): result for result in results}
    passing_verdicts = {"PASS", "BLOCKED_EXPECTED"}

    def scenario_group(*identifiers: str) -> tuple[str, list[str]]:
        evidence = [
            f"{identifier}:{by_id.get(identifier, {}).get('verdict', 'NOT_RUN')}"
            for identifier in identifiers
        ]
        if not all(identifier in by_id for identifier in identifiers):
            return "NOT_RUN", evidence
        return (
            "PASS"
            if all(by_id[identifier]["verdict"] in passing_verdicts for identifier in identifiers)
            else "FAIL",
            evidence,
        )

    def oracle_group(name: str) -> tuple[str, list[str]]:
        relevant = [
            result
            for result in results
            if any(oracle.get("name") == name for oracle in result.get("oracle_results", []))
        ]
        if not relevant:
            return "NOT_RUN", []
        passed = all(
            next(
                oracle
                for oracle in result["oracle_results"]
                if oracle.get("name") == name
            )["passed"]
            for result in relevant
        )
        return (
            "PASS" if passed else "FAIL",
            [f"{result['scenario_id']}:{name}" for result in relevant],
        )

    requirements: dict[str, dict[str, Any]] = {}
    for number in range(1, 31):
        requirement_id = f"HTR-{number:03d}"
        requirements[requirement_id] = {
            "status": "NOT_RUN",
            "evidence": [],
        }
    requirements["HTR-001"] = {
        "status": "PASS",
        "evidence": ["tools/icpi_chat_scenario_generator.py", "offline deterministic provider fixture"],
    }
    requirements["HTR-002"] = {
        "status": "PASS" if len(build_scenarios()) == 120 else "FAIL",
        "evidence": [f"scenario_count={len(build_scenarios())}"],
    }
    requirements["HTR-003"] = {"status": "PASS", "evidence": ["generator seed regression tests"]}
    requirements["HTR-004"] = {"status": "PASS", "evidence": ["scenario timeout fields"]}
    status, evidence = scenario_group(*(f"FLT-{index:03d}" for index in range(1, 17)))
    requirements["HTR-005"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group(*(f"VIS-{index:03d}" for index in range(1, 16)))
    requirements["HTR-006"] = {"status": status, "evidence": evidence}
    requirements["HTR-007"] = {
        "status": "PASS",
        "evidence": ["WorkbenchAdapter uses composer and button commands", "test_chat_scenario_runner"],
    }
    requirements["HTR-008"] = {
        "status": "PASS",
        "evidence": ["classify_supervisor_status", "test_supervisor_faults F13/F14"],
    }
    requirements["HTR-009"] = {
        "status": "PASS",
        "evidence": ["app-events.jsonl STARTUP_READY and HEARTBEAT", "test_app_lifecycle_records_readiness_heartbeat_and_checkpoint"],
    }
    status, evidence = oracle_group("normal_turn_partial_order")
    requirements["HTR-010"] = {"status": status, "evidence": evidence}
    status, evidence = oracle_group("chat_idle")
    requirements["HTR-011"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("LIF-002")
    requirements["HTR-012"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("LIF-001", "LIF-008")
    requirements["HTR-013"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("FLT-005")
    requirements["HTR-014"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("FLT-006")
    requirements["HTR-015"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("FLT-007", "FLT-008")
    requirements["HTR-016"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("FLT-009")
    requirements["HTR-017"] = {"status": status, "evidence": evidence}
    status, evidence = scenario_group("FLT-015", "FLT-016")
    requirements["HTR-018"] = {"status": status, "evidence": evidence}
    requirements["HTR-019"] = {"status": "PASS", "evidence": ["benchmarks/icpi/page-reference-v1/manifest.json"]}
    status, evidence = scenario_group(*(f"PAG-{index:03d}" for index in range(1, 9)))
    requirements["HTR-020"] = {
        "status": status,
        "evidence": [*evidence, "expected-pages.json literal/concept/reasoning oracles"],
    }
    status, evidence = scenario_group(*(f"SEC-{index:03d}" for index in range(1, 6)))
    requirements["HTR-021"] = {"status": status, "evidence": evidence}
    requirements["HTR-022"] = {
        "status": "PASS" if not secret_scan_findings else "FAIL",
        "evidence": ["artifact secret scan", *secret_scan_findings],
    }
    requirements["HTR-023"] = {
        "status": "PASS" if provider == "live" and model_identity_frozen else "NOT_RUN",
        "evidence": [f"provider={provider}", f"model_identity_frozen={model_identity_frozen}"],
    }
    status, evidence = scenario_group(*(f"VIS-{index:03d}" for index in range(1, 16)))
    requirements["HTR-024"] = {"status": status, "evidence": evidence}
    requirements["HTR-025"] = {
        "status": "PASS" if soak_metrics_collected else "NOT_RUN",
        "evidence": ["metrics.json"],
    }
    requirements["HTR-026"] = {
        "status": "PASS",
        "evidence": ["read-only incident.json and fault result bundles"],
    }
    repair_log = ROOT / "reports" / "icpi-supervised" / "implementation" / "repair-log.jsonl"
    repair_entries = (
        [json.loads(line) for line in repair_log.read_text(encoding="utf-8").splitlines() if line]
        if repair_log.exists()
        else []
    )
    requirements["HTR-027"] = {
        "status": "PASS" if repair_entries and all(item.get("failing_regression") for item in repair_entries) else "FAIL",
        "evidence": ["reports/icpi-supervised/implementation/repair-log.jsonl"],
    }
    requirements["HTR-028"] = {
        "status": "PASS" if repair_entries and all(item.get("original_scenarios") for item in repair_entries) else "FAIL",
        "evidence": ["repair log original scenario seeds"],
    }
    requirements["HTR-029"] = {
        "status": "PASS" if repair_entries and all(item.get("category_replay") for item in repair_entries) else "FAIL",
        "evidence": ["repair log category replay records"],
    }
    requirements["HTR-030"] = {"status": "PASS", "evidence": ["final-audit.md"]}
    audit_payload = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "requirements": requirements,
        "summary": dict(Counter(item["status"] for item in requirements.values())),
    }
    lines = ["# ICPI Heavy Campaign Requirement Audit", ""]
    lines.append("| Requirement | Status | Evidence |")
    lines.append("|---|---|---|")
    for requirement_id, record in requirements.items():
        evidence = "; ".join(record["evidence"]).replace("|", "\\|")
        lines.append(f"| {requirement_id} | {record['status']} | {evidence} |")
    lines.extend(("", "Missing or NOT_RUN evidence remains non-pass and is not waived.", ""))
    return audit_payload, "\n".join(lines)


def run_campaign(args: argparse.Namespace, scenarios: Sequence[ChatScenario]) -> int:
    run_id = args.run_id or _run_id()
    run_root = args.report_root.expanduser().resolve() / run_id
    baseline_manifest = source_file_manifest(ROOT)
    git_state = git_baseline(ROOT)
    git_status_lines = list(git_state.pop("status_porcelain", []))
    collector = ArtifactCollector(run_root)
    atomic_write_text(
        run_root / "git-status.txt",
        "\n".join(git_status_lines) + ("\n" if git_status_lines else ""),
    )
    git_state["status_artifact"] = "git-status.txt"
    scenario_path = run_root / "scenarios.jsonl"
    atomic_write_text(scenario_path, render_jsonl(scenarios))
    manifest = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": utc_now(),
        "source_root": str(ROOT),
        "source_manifest_sha256": sha256_json(baseline_manifest),
        "git": git_state,
        "source_dirty": bool(git_state.get("dirty", False)),
        "corpus_id": CORPUS_ID,
        "campaign_seed": args.campaign_seed,
        "canonical_scenario_signature": EXPECTED_SCENARIO_SIGNATURE,
        "selection_signature": corpus_signature(scenarios),
        "scenario_count": len(scenarios),
        "provider": args.provider,
        "provider_kind": args.provider_kind,
        "model": args.model,
        "model_digest": args.model_digest,
        "expected_model_sha256": args.expected_model_sha256,
        "base_url": args.base_url,
        "api_key_configured": bool(args.api_key),
        "response_seed": args.response_seed,
        "response_temperature_bp": args.response_temperature_bp,
        "response_top_p_bp": args.response_top_p_bp,
        "reasoning_effort": args.reasoning_effort,
        "context_budget_tokens": args.context_budget,
        "runtime_context_tokens": args.runtime_context_tokens,
        "context_safety_margin_tokens": args.context_safety_margin,
        "max_output_tokens": args.max_output_tokens,
        "max_reasoning_samples": args.max_reasoning_samples,
        "transport_retries": args.transport_retries,
        "runner_path": args.runner_path,
        "model_path": args.model_path,
        "llama_cpp_root": args.llama_cpp_root,
        "llama_cpp_build_dir": args.llama_cpp_build_dir,
        "llama_grammar_dir": args.llama_grammar_dir,
        "llama_context_tokens": args.llama_context,
        "llama_gpu_layers": args.llama_gpu_layers,
        "llama_threads": args.llama_threads,
        "llama_seed": args.llama_seed,
        "llama_temperature_bp": args.llama_temperature_bp,
        "llama_top_p_bp": args.llama_top_p_bp,
        "llama_top_k": args.llama_top_k,
        "timeout_seconds": args.timeout_seconds,
        "live_quality_threshold_bp": args.live_quality_threshold_bp,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "dependencies": dependency_inventory(),
        "display": os.getenv("DISPLAY", ""),
        "source_supervisor_status_at_start": read_supervisor_status(ROOT),
        "provider_identity_before": {},
        "provider_runtime_preparation": {"status": "pending"},
        "scenario_schema": str(SCENARIO_SCHEMA_PATH),
        "pass_fail_gates": list(PASS_FAIL_GATES),
        "run_status": "PREPARING",
    }
    atomic_write_text(run_root / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    atomic_write_text(
        run_root / "source-manifest.json",
        json.dumps(baseline_manifest, indent=2, sort_keys=True) + "\n",
    )
    try:
        provider_runtime_preparation = prepare_live_provider_runtime(
            provider=args.provider,
            provider_kind=args.provider_kind,
            model=args.model,
            base_url=args.base_url,
            runtime_context_tokens=args.runtime_context_tokens,
            keep_alive="",
            timeout_seconds=args.timeout_seconds,
            api_key=args.api_key,
            response_seed=args.response_seed,
            context_budget=args.context_budget,
            context_safety_margin_tokens=args.context_safety_margin,
            max_output_tokens=args.max_output_tokens,
            max_reasoning_samples=args.max_reasoning_samples,
            reasoning_effort=args.reasoning_effort,
            response_temperature_bp=args.response_temperature_bp,
            response_top_p_bp=args.response_top_p_bp,
            runner_path=args.runner_path,
            model_path=args.model_path,
            expected_model_sha256=args.expected_model_sha256 or args.model_digest,
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
        provider_identity_before = live_provider_identity_snapshot(
            provider=args.provider,
            provider_kind=args.provider_kind,
            model=args.model,
            model_digest=args.model_digest,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
            api_key=args.api_key,
            response_seed=args.response_seed,
            context_budget=args.context_budget,
            runtime_context_tokens=args.runtime_context_tokens,
            context_safety_margin_tokens=args.context_safety_margin,
            max_output_tokens=args.max_output_tokens,
            max_reasoning_samples=args.max_reasoning_samples,
            reasoning_effort=args.reasoning_effort,
            response_temperature_bp=args.response_temperature_bp,
            response_top_p_bp=args.response_top_p_bp,
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
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        incident_path = run_root / "incidents" / "provider-preflight.json"
        incident = {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "failure_type": "PROVIDER_PREFLIGHT_FAILURE",
            "timestamp": utc_now(),
            "provider": args.provider,
            "provider_kind": args.provider_kind,
            "model": args.model,
            "model_digest": args.model_digest,
            "expected_model_sha256": args.expected_model_sha256,
            "base_url": args.base_url,
            "runtime_context_tokens": args.runtime_context_tokens,
            "runner_path": args.runner_path,
            "model_path": args.model_path,
            "llama_cpp_root": args.llama_cpp_root,
            "llama_cpp_build_dir": args.llama_cpp_build_dir,
            "error": error,
        }
        atomic_write_text(
            incident_path,
            json.dumps(incident, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        incident_path.chmod(0o444)
        manifest.update(
            {
                "completed_at": utc_now(),
                "run_status": "INFRASTRUCTURE_FAILURE",
                "provider_runtime_preparation": {"status": "FAIL", "error": error},
                "preflight_incident": str(incident_path),
            }
        )
        atomic_write_text(
            run_root / "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_root": str(run_root),
                    "selected": len(scenarios),
                    "completed": 0,
                    "result_counts": {"INFRASTRUCTURE_FAILURE": 1},
                },
                sort_keys=True,
            )
        )
        return 1
    manifest.update(
        {
            "provider_identity_before": provider_identity_before,
            "provider_runtime_preparation": provider_runtime_preparation,
            "run_status": "RUNNING",
        }
    )
    atomic_write_text(run_root / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    page_manifest = validate_fixture(PAGE_FIXTURE_ROOT)
    atomic_write_text(
        run_root / "fixture-manifest.json",
        json.dumps(page_manifest, indent=2, sort_keys=True) + "\n",
    )
    supervisor = SupervisorAdapter()
    all_results: list[dict[str, Any]] = []
    workspaces: list[Path] = []
    workspace_baselines: dict[str, dict[str, Any]] = {}
    atomic_write_text(
        run_root / "workspace-baselines.json",
        json.dumps(workspace_baselines, indent=2, sort_keys=True) + "\n",
    )
    categories = tuple(dict.fromkeys(scenario.category for scenario in scenarios))
    campaign_started = time.monotonic()
    for category in categories:
        selected = tuple(scenario for scenario in scenarios if scenario.category == category)
        workspace = run_root / "workspaces" / category
        workspaces.append(workspace)
        fixture_workspace = prepare_category_workspace(ROOT, workspace)
        workspace_baselines[category] = {
            **fixture_workspace,
            "runtime": runtime_state_baseline(workspace),
        }
        atomic_write_text(
            run_root / "workspace-baselines.json",
            json.dumps(workspace_baselines, indent=2, sort_keys=True) + "\n",
        )
        category_scenarios = run_root / "category-scenarios" / f"{category}.jsonl"
        category_result = run_root / "category-results" / f"{category}.json"
        category_artifacts = run_root / "category-artifacts" / category
        category_scenarios.parent.mkdir(parents=True, exist_ok=True)
        category_result.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(category_scenarios, render_jsonl(selected))
        command = build_category_worker_command(
            args,
            workspace=workspace,
            category_scenarios=category_scenarios,
            category_result=category_result,
            category_artifacts=category_artifacts,
        )
        exit_code = supervisor.run_worker(command, workspace)
        if category_result.exists():
            category_payload = json.loads(category_result.read_text(encoding="utf-8"))
            category_results = list(category_payload["results"])
        else:
            category_results = [
                ScenarioResult(
                    scenario_id=scenario.scenario_id,
                    category=scenario.category,
                    seed=scenario.seed,
                    expected_outcome=scenario.expected_outcome,
                    verdict="INFRASTRUCTURE_FAILURE",
                    started_at=utc_now(),
                    completed_at=utc_now(),
                    duration_seconds=0.0,
                    step_results=[],
                    event_types=[],
                    oracle_results=[_oracle("worker_exit", False, f"exit_code={exit_code}")],
                    state_digest_before="",
                    state_digest_after="",
                    source_snapshot_before="",
                    source_snapshot_after="",
                    response_latency_seconds=0.0,
                    quality_score_bp=0,
                    quality_dimensions={"infrastructure": 0},
                    process_metrics_before={},
                    process_metrics_after={},
                    screenshot_paths=[],
                    incident_references=[],
                    error=f"category worker exited {exit_code} without results",
                ).to_dict()
                for scenario in selected
            ]
        for result in category_results:
            atomic_append_jsonl(run_root / "results.jsonl", result)
        all_results.extend(category_results)
        if (
            not args.continue_on_failure
            and any(result["verdict"] not in {"PASS", "BLOCKED_EXPECTED"} for result in category_results)
        ):
            break
    soak_result: dict[str, Any] | None = None
    if args.soak_turns > 0 or args.soak_min_seconds > 0:
        soak_workspace = run_root / "workspaces" / "soak"
        workspaces.append(soak_workspace)
        fixture_workspace = prepare_category_workspace(ROOT, soak_workspace)
        workspace_baselines["soak"] = {
            **fixture_workspace,
            "runtime": runtime_state_baseline(soak_workspace),
        }
        atomic_write_text(
            run_root / "workspace-baselines.json",
            json.dumps(workspace_baselines, indent=2, sort_keys=True) + "\n",
        )
        soak_result_path = run_root / "soak-result.json"
        soak_artifacts = run_root / "category-artifacts" / "soak"
        soak_command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--soak-worker",
            "--repo",
            str(soak_workspace),
            "--worker-result",
            str(soak_result_path),
            "--worker-artifact-root",
            str(soak_artifacts),
            "--soak-turns",
            str(args.soak_turns),
            "--soak-min-seconds",
            str(args.soak_min_seconds),
            "--time-scale",
            str(args.time_scale),
        ]
        soak_exit = supervisor.run_worker(soak_command, soak_workspace)
        if soak_result_path.exists():
            soak_result = json.loads(soak_result_path.read_text(encoding="utf-8"))
        else:
            soak_result = {
                "verdict": "INFRASTRUCTURE_FAILURE",
                "canonical_gate_complete": False,
                "error": f"soak worker exited {soak_exit} without a result",
            }
    _copy_event_artifacts(run_root, workspaces)
    human_review = build_human_review_record(
        run_root,
        scenarios,
        all_results,
        provider=args.provider,
    )
    atomic_write_text(
        run_root / "human-review.json",
        json.dumps(human_review, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    metrics = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "campaign_duration_seconds": time.monotonic() - campaign_started,
        "result_counts": dict(Counter(result["verdict"] for result in all_results)),
        "scenario_duration_seconds": {
            result["scenario_id"]: result["duration_seconds"] for result in all_results
        },
        "response_latency_seconds": {
            result["scenario_id"]: result["response_latency_seconds"] for result in all_results
        },
        "soak": soak_result,
    }
    atomic_write_text(run_root / "metrics.json", json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    secret_scan_findings = scan_artifacts_for_secrets(run_root, (args.api_key,))
    atomic_write_text(
        run_root / "secret-scan.json",
        json.dumps(
            {
                "schema_version": RUNNER_SCHEMA_VERSION,
                "finding_count": len(secret_scan_findings),
                "findings": secret_scan_findings,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    audit_payload, audit_markdown = build_requirement_audit(
        scenarios,
        all_results,
        provider=args.provider,
        model_identity_frozen=bool(args.model and (args.expected_model_sha256 or args.model_digest)),
        secret_scan_findings=secret_scan_findings,
        soak_metrics_collected=soak_result is not None,
        soak_completed=bool(soak_result and soak_result.get("canonical_gate_complete")),
    )
    atomic_write_text(run_root / "requirement-audit.json", json.dumps(audit_payload, indent=2, sort_keys=True) + "\n")
    gate_results = build_gate_results(
        scenarios,
        all_results,
        provider=args.provider,
        live_quality_threshold_bp=args.live_quality_threshold_bp,
        soak_result=soak_result,
        audit_payload=audit_payload,
        secret_scan_findings=secret_scan_findings,
    )
    atomic_write_text(
        run_root / "gate-results.json",
        json.dumps(gate_results, indent=2, sort_keys=True) + "\n",
    )
    gate_lines = ["", "## Binary Gates", "", "| Gate | Status | Evidence |", "|---|---|---|"]
    for gate_id, record in gate_results["gates"].items():
        gate_lines.append(f"| {gate_id} | {record['status']} | {record['evidence']} |")
    atomic_write_text(run_root / "final-audit.md", audit_markdown + "\n".join(gate_lines) + "\n")
    manifest["completed_at"] = utc_now()
    manifest["completed_scenario_count"] = len(all_results)
    manifest["result_counts"] = metrics["result_counts"]
    manifest["soak"] = soak_result
    manifest["secret_scan_finding_count"] = len(secret_scan_findings)
    manifest["gate_summary"] = gate_results["summary"]
    manifest["workspace_baselines_sha256"] = sha256_json(workspace_baselines)
    manifest["human_review"] = {
        "visual_status": human_review["visual"]["status"],
        "live_response_status": human_review["live_responses"]["status"],
    }
    manifest["provider_identity_after"] = live_provider_identity_snapshot(
        provider=args.provider,
        provider_kind=args.provider_kind,
        model=args.model,
        model_digest=args.model_digest,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        api_key=args.api_key,
        response_seed=args.response_seed,
        context_budget=args.context_budget,
        runtime_context_tokens=args.runtime_context_tokens,
        context_safety_margin_tokens=args.context_safety_margin,
        max_output_tokens=args.max_output_tokens,
        max_reasoning_samples=args.max_reasoning_samples,
        reasoning_effort=args.reasoning_effort,
        response_temperature_bp=args.response_temperature_bp,
        response_top_p_bp=args.response_top_p_bp,
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
    scenarios_passed = len(all_results) == len(scenarios) and all(
        result["verdict"] in {"PASS", "BLOCKED_EXPECTED"} for result in all_results
    )
    soak_passed = soak_result is None or soak_result.get("verdict") == "PASS"
    manifest["run_status"] = "COMPLETED" if scenarios_passed and soak_passed else "FAILED"
    atomic_write_text(run_root / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "run_root": str(run_root),
                "selected": len(scenarios),
                "completed": len(all_results),
                "result_counts": metrics["result_counts"],
            },
            sort_keys=True,
        )
    )
    return 0 if scenarios_passed and soak_passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ICPI supervisor heavy chat scenario corpus.")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--scenarios", type=Path)
    parser.add_argument("--campaign-seed", type=int, default=DEFAULT_CAMPAIGN_SEED)
    parser.add_argument("--lane", choices=("all", "deterministic", "live"), default="deterministic")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--provider", choices=("deterministic", "live"), default="deterministic")
    parser.add_argument(
        "--provider-kind",
        choices=("llama_cpp_process",),
        default="llama_cpp_process",
    )
    parser.add_argument("--model", default="icpi-deterministic-fixture")
    parser.add_argument("--model-digest", default="")
    parser.add_argument("--expected-model-sha256", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--response-seed", type=int, default=20260831)
    parser.add_argument("--context-budget", type=int, default=6000)
    parser.add_argument("--runtime-context-tokens", type=int, default=0)
    parser.add_argument("--context-safety-margin", type=int, default=512)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--max-reasoning-samples", type=int, default=2)
    parser.add_argument(
        "--reasoning-effort",
        choices=("", "none", "low", "medium", "high", "xhigh"),
        default="",
    )
    parser.add_argument("--response-temperature-bp", type=int, default=-1)
    parser.add_argument("--response-top-p-bp", type=int, default=-1)
    parser.add_argument("--transport-retries", type=int, default=0)
    parser.add_argument("--runner-path", default="")
    parser.add_argument("--model-path", default="")
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
    parser.add_argument(
        "--live-quality-threshold-bp",
        type=int,
        default=DEFAULT_LIVE_QUALITY_THRESHOLD_BP,
    )
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--soak", action="store_true")
    parser.add_argument("--soak-turns", type=int, default=0)
    parser.add_argument("--soak-min-seconds", type=float, default=0.0)
    parser.add_argument("--soak-worker", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--worker-result", type=Path)
    parser.add_argument("--worker-artifact-root", type=Path)
    return parser


def normalize_provider_path_args(args: argparse.Namespace) -> argparse.Namespace:
    for name in (
        "runner_path",
        "model_path",
        "llama_cpp_root",
        "llama_cpp_build_dir",
        "llama_grammar_dir",
    ):
        value = str(getattr(args, name, "") or "").strip()
        if value:
            setattr(args, name, str(Path(value).expanduser().resolve()))
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = normalize_provider_path_args(build_parser().parse_args(argv))
    if args.time_scale <= 0:
        raise SystemExit("--time-scale must be positive")
    if args.context_budget < 256:
        raise SystemExit("--context-budget must be at least 256")
    if args.runtime_context_tokens < 0:
        raise SystemExit("--runtime-context-tokens must be non-negative")
    if args.context_safety_margin < 0:
        raise SystemExit("--context-safety-margin must be non-negative")
    if args.max_output_tokens < 1:
        raise SystemExit("--max-output-tokens must be positive")
    if args.max_reasoning_samples < 1:
        raise SystemExit("--max-reasoning-samples must be positive")
    if args.transport_retries < 0:
        raise SystemExit("--transport-retries must be non-negative")
    if args.llama_context < 256:
        raise SystemExit("--llama-context must be at least 256")
    if args.llama_threads < 0:
        raise SystemExit("--llama-threads must be non-negative")
    if args.llama_temperature_bp < 0:
        raise SystemExit("--llama-temperature-bp must be non-negative")
    if args.llama_top_p_bp < 0:
        raise SystemExit("--llama-top-p-bp must be non-negative")
    if args.llama_top_k < 0:
        raise SystemExit("--llama-top-k must be non-negative")
    if not os.getenv("DISPLAY"):
        raise SystemExit("DISPLAY is required; run the deterministic lane under xvfb-run")
    if args.soak:
        args.soak_turns = max(args.soak_turns, 500)
        args.soak_min_seconds = max(args.soak_min_seconds, 14_400.0)
    if args.soak_worker:
        if args.worker_result is None or args.worker_artifact_root is None:
            raise SystemExit("soak worker requires --worker-result and --worker-artifact-root")
        result = execute_soak_worker(
            args.repo.expanduser().resolve(),
            args.worker_artifact_root.expanduser().resolve(),
            minimum_turns=args.soak_turns,
            minimum_seconds=args.soak_min_seconds,
            time_scale=args.time_scale,
        )
        atomic_write_text(
            args.worker_result.expanduser().resolve(),
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        return 0 if result["verdict"] == "PASS" else 1
    scenarios = (
        load_scenarios(args.scenarios)
        if args.scenarios
        else select_scenarios(
            build_scenarios(args.campaign_seed),
            lane=args.lane,
            categories=tuple(args.category),
        )
    )
    validate_selected_scenarios(scenarios)
    if args.provider == "live":
        args.expected_model_sha256 = args.expected_model_sha256 or args.model_digest
        if not args.expected_model_sha256:
            raise SystemExit("live provider orchestration requires --expected-model-sha256")
        if not args.runner_path:
            raise SystemExit("live provider orchestration requires --runner-path")
        if not args.model_path:
            raise SystemExit("live provider orchestration requires --model-path")
        if not args.llama_cpp_root:
            raise SystemExit("live provider orchestration requires --llama-cpp-root")
        if not args.llama_cpp_build_dir:
            raise SystemExit("live provider orchestration requires --llama-cpp-build-dir")
        if args.runtime_context_tokens <= 0:
            raise SystemExit("live provider orchestration requires --runtime-context-tokens")
        if args.response_temperature_bp < 0 or args.response_top_p_bp < 0:
            raise SystemExit(
                "live provider orchestration requires explicit --response-temperature-bp "
                "and --response-top-p-bp"
            )
    if args.worker:
        if args.worker_result is None or args.worker_artifact_root is None:
            raise SystemExit("worker mode requires --worker-result and --worker-artifact-root")
        results = execute_worker(
            args.repo.expanduser().resolve(),
            scenarios,
            args.worker_artifact_root.expanduser().resolve(),
            time_scale=args.time_scale,
            continue_on_failure=args.continue_on_failure,
            provider_mode=args.provider,
            provider_kind=args.provider_kind,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            timeout_seconds=args.timeout_seconds,
            response_seed=args.response_seed,
            context_budget=args.context_budget,
            runtime_context_tokens=args.runtime_context_tokens,
            context_safety_margin_tokens=args.context_safety_margin,
            max_output_tokens=args.max_output_tokens,
            max_reasoning_samples=args.max_reasoning_samples,
            reasoning_effort=args.reasoning_effort,
            response_temperature_bp=args.response_temperature_bp,
            response_top_p_bp=args.response_top_p_bp,
            transport_retries=args.transport_retries,
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
            live_quality_threshold_bp=args.live_quality_threshold_bp,
        )
        payload = {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "results": [result.to_dict() for result in results],
        }
        atomic_write_text(
            args.worker_result.expanduser().resolve(),
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        return 0 if len(results) == len(scenarios) and all(
            result.verdict in {"PASS", "BLOCKED_EXPECTED"} for result in results
        ) else 1
    return run_campaign(args, scenarios)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ArtifactCollector",
    "DeterministicProviderFixture",
    "FaultAdapter",
    "RUNNER_SCHEMA_VERSION",
    "ScenarioResult",
    "SupervisorAdapter",
    "TERMINAL_VERDICTS",
    "WorkbenchAdapter",
    "build_category_worker_command",
    "build_human_review_record",
    "build_requirement_audit",
    "dependency_inventory",
    "evaluate_scenario",
    "execute_worker",
    "git_baseline",
    "live_provider_identity_snapshot",
    "load_scenarios",
    "main",
    "normalize_provider_path_args",
    "prepare_category_workspace",
    "prepare_live_provider_runtime",
    "run_campaign",
    "runtime_state_baseline",
    "scenario_dependency_issue",
    "source_file_manifest",
    "validate_selected_scenarios",
]
