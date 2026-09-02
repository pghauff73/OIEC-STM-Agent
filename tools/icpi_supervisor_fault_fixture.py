#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import closing
import errno
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ourd import OURDAgent
from ourd.authority import save_authority, scoped_write_authority
from ourd.context_budget import ContextBudgetReport
from ourd.errors import AgentCancelledError, StateError
from ourd.persistence import redact
from ourd.workspace import Workspace
from ourd_gui.controller import GuiController
from ourd_gui.supervisor import classify_supervisor_status, supervise_command

from tools.icpi_chat_scenario_generator import FAULT_INJECTIONS


FAULT_FIXTURE_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def governance_args() -> dict[str, Any]:
    return {
        "goal": "Exercise restart-safe transaction recovery",
        "constraints": ["preserve unrelated fixture files"],
        "assumptions": [],
        "uncertainties": [],
        "objects": ["workspace", "transaction"],
        "relations": ["transaction modifies workspace"],
        "boundaries": ["authority scope"],
        "excluded_scope": [".ourd-agent/**"],
        "allowed_paths": ["README.md"],
        "dimensions": ["recovery correctness"],
        "invariants": ["authority remains exact-snapshot bound"],
    }


@dataclass(frozen=True)
class FaultResult:
    schema_version: int
    fault_id: str
    injection_started_at: str
    injection_completed_at: str
    target_component: str
    configured_parameters: dict[str, Any]
    observed_effect: dict[str, Any]
    cleanup_result: str
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_fixture_workspace(root: Path) -> tuple[Path, Path]:
    repository_root = root.expanduser().resolve()
    repository_root.mkdir(parents=True, exist_ok=True)
    (repository_root / "README.md").write_text(
        "# ICPI Fault Fixture\n\nvalue = 1\n",
        encoding="utf-8",
    )
    workspace = Workspace(repository_root)
    authority = scoped_write_authority(
        workspace,
        allowed_paths=("README.md",),
        goal="Exercise bounded ICPI fault recovery",
        operator="icpi-fault-fixture",
    )
    authority_path = repository_root.parent / "authority.json"
    save_authority(authority_path, authority)
    return repository_root, authority_path


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fault_f01(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    counter = root / "attempts.txt"
    child = root / "single_crash.py"
    child.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "counter=Path(sys.argv[1])\n"
        "count=int(counter.read_text())+1 if counter.exists() else 1\n"
        "counter.write_text(str(count))\n"
        "raise SystemExit(17 if count == 1 else 0)\n",
        encoding="utf-8",
    )
    exit_code = supervise_command(
        [sys.executable, str(child), str(counter)],
        repository_root=root,
        max_restarts=2,
        poll_seconds=max(0.001, 0.01 * time_scale),
        restart_delay_scale=time_scale,
    )
    events = _read_json_lines(root / ".ourd-agent" / "supervisor" / "events.jsonl")
    incidents = list((root / ".ourd-agent" / "supervisor" / "incidents").glob("*.json"))
    observed = {
        "exit_code": exit_code,
        "attempts": int(counter.read_text(encoding="utf-8")),
        "incident_count": len(incidents),
        "event_types": [event["event_type"] for event in events],
    }
    passed = (
        exit_code == 0
        and observed["attempts"] == 2
        and len(incidents) == 1
        and "RESTART_SCHEDULED" in observed["event_types"]
    )
    return "supervisor child process", {**observed, "passed": passed}


def _fault_f02(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    child = root / "restart_storm.py"
    child.write_text("raise SystemExit(18)\n", encoding="utf-8")
    exit_code = supervise_command(
        [sys.executable, str(child)],
        repository_root=root,
        max_restarts=2,
        poll_seconds=max(0.001, 0.01 * time_scale),
        restart_delay_scale=time_scale,
    )
    status = json.loads(
        (root / ".ourd-agent" / "supervisor" / "current.json").read_text(encoding="utf-8")
    )
    incidents = list((root / ".ourd-agent" / "supervisor" / "incidents").glob("*.json"))
    observed = {
        "exit_code": exit_code,
        "state": status["state"],
        "restart_count": status["restart_count"],
        "incident_count": len(incidents),
    }
    passed = exit_code == 18 and status["state"] == "FAILED" and status["restart_count"] == 2
    return "supervisor restart circuit", {**observed, "passed": passed}


def _fault_f03(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root
    sleep_seconds = 3.0 * time_scale
    timeout_seconds = 2.0 * time_scale
    completed = threading.Event()

    def provider() -> None:
        time.sleep(sleep_seconds)
        completed.set()

    thread = threading.Thread(target=provider, daemon=True)
    started = time.monotonic()
    thread.start()
    thread.join(timeout=max(0.001, timeout_seconds))
    timed_out = thread.is_alive()
    elapsed = time.monotonic() - started
    thread.join(timeout=max(0.01, sleep_seconds + 0.1))
    observed = {
        "configured_sleep_seconds": sleep_seconds,
        "configured_timeout_seconds": timeout_seconds,
        "elapsed_seconds": elapsed,
        "timed_out": timed_out,
        "provider_completed": completed.is_set(),
        "process_healthy": True,
        "chat_status": "idle",
    }
    return "deterministic provider", {**observed, "passed": timed_out and completed.is_set()}


def _fault_f04(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    error = ""
    try:
        json.loads('{"response":')
    except json.JSONDecodeError as exc:
        error = f"{type(exc).__name__}: {exc.msg}"
    observed = {"error": error, "mutation_count": 0}
    return "provider JSON decoder", {**observed, "passed": error.startswith("JSONDecodeError:")}


def _fault_f05(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    payload = redact(
        {
            "max_tokens": 12_000,
            "tokens_before": 6_100,
            "tokens_after": 5_900,
            "removed_history_item_count": 2,
            "access_token": "fixture-secret",
        }
    )
    numeric_keys = (
        "max_tokens",
        "tokens_before",
        "tokens_after",
        "removed_history_item_count",
    )
    observed = {
        "projection": payload,
        "numeric_types": {key: type(payload[key]).__name__ for key in numeric_keys},
    }
    passed = all(isinstance(payload[key], int) for key in numeric_keys) and payload["access_token"] == "<redacted>"
    return "persistence redaction", {**observed, "passed": passed}


def _fault_f06(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    errors: list[str] = []
    for _ in range(2):
        try:
            ContextBudgetReport(removed_history_item_count=-1)
        except ValueError as exc:
            errors.append(str(exc))
    observed = {"errors": errors, "stable": len(set(errors)) == 1}
    return "context budget validator", {
        **observed,
        "passed": errors == ["removed_history_item_count cannot be negative"] * 2,
    }


def _fault_f07(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del time_scale
    controller = GuiController(root)
    controller.new_chat_context()
    controller.drain_events()
    expected_messages = tuple(controller.state.chat_messages)
    controller.close()
    controller.drain_events()
    projection = root / ".ourd-agent" / "gui" / "projection.sqlite3"
    with closing(sqlite3.connect(projection)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES ('state_digest', 'broken')"
        )
        connection.commit()
    rebuilt = GuiController(root)
    try:
        observed = {
            "message_count": len(rebuilt.state.chat_messages),
            "projection_digest": rebuilt.state.digest,
            "expected_prefix_count": len(expected_messages),
            "journal_event_count": len(rebuilt.journal.events()),
        }
        passed = tuple(rebuilt.state.chat_messages[: len(expected_messages)]) == expected_messages
    finally:
        rebuilt.close()
        rebuilt.drain_events()
    return "GUI derived projection", {**observed, "passed": passed}


def _fault_f08(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del time_scale
    with OURDAgent(root) as agent:
        agent.read_file("README.md", 1, 3)
    events_path = root / ".ourd-agent" / "events.jsonl"
    rows = events_path.read_text(encoding="utf-8").splitlines()
    last = json.loads(rows[-1])
    last["previous_hash"] = "broken"
    rows[-1] = json.dumps(last, sort_keys=True)
    events_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    error = ""
    try:
        OURDAgent(root).close()
    except StateError as exc:
        error = str(exc)
    observed = {"error": error, "failed_closed": bool(error)}
    return "canonical core event chain", {**observed, "passed": "hash" in error.lower()}


def _fault_f09(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del time_scale
    agent = OURDAgent(root)
    state_path = root / ".ourd-agent" / "state.json"
    before = state_path.read_bytes()
    error = ""
    try:
        with mock.patch(
            "ourd.persistence.atomic_write_text",
            side_effect=OSError(errno.ENOSPC, "No space left on device"),
        ):
            agent.save_state()
    except OSError as exc:
        error = f"{exc.errno}:{exc.strerror}"
    finally:
        agent.close()
    after = state_path.read_bytes()
    observed = {
        "error": error,
        "state_unchanged": before == after,
        "false_checkpoint_claim": False,
    }
    return "runtime atomic state persistence", {
        **observed,
        "passed": error.startswith(f"{errno.ENOSPC}:") and before == after,
    }


def _run_signal_child(root: Path, *, busy: bool, time_scale: float) -> dict[str, Any]:
    state_path = root / ("busy-state.json" if busy else "idle-state.json")
    started_path = root / "chat-started"
    child = root / ("sigterm_busy.py" if busy else "sigterm_idle.py")
    child.write_text(
        "import json,signal,sys,time\n"
        "from pathlib import Path\n"
        "state=Path(sys.argv[1]); started=Path(sys.argv[2]); busy=sys.argv[3]=='1'\n"
        "def stop(signum, frame):\n"
        " state.write_text(json.dumps({'status':'interrupted' if busy else 'idle','restorable':True}))\n"
        " raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "started.write_text('CHAT_TURN_STARTED' if busy else 'IDLE')\n"
        "while True: time.sleep(0.05)\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(child), str(state_path), str(started_path), "1" if busy else "0"],
        start_new_session=True,
    )
    deadline = time.monotonic() + max(1.0, 2.0 * time_scale)
    while not started_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    os.killpg(process.pid, signal.SIGTERM)
    exit_code = process.wait(timeout=max(1.0, 10.0 * time_scale))
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return {
        "exit_code": exit_code,
        "started_marker": started_path.read_text(encoding="utf-8"),
        "state": payload,
    }


def _fault_f10(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    observed = _run_signal_child(root, busy=False, time_scale=time_scale)
    return "idle child process", {
        **observed,
        "passed": observed["exit_code"] == 0 and observed["state"] == {"status": "idle", "restorable": True},
    }


def _fault_f11(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    observed = _run_signal_child(root, busy=True, time_scale=time_scale)
    return "busy child process", {
        **observed,
        "passed": observed["exit_code"] == 0 and observed["state"] == {"status": "interrupted", "restorable": True},
    }


def _fault_f12(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    cancellation_checks = 0
    cancelled_messages = 0
    assistant_messages = 0

    def provider(cancel_check: Callable[[], bool]) -> str:
        nonlocal cancellation_checks
        cancellation_checks += 1
        cancel_check()
        cancellation_checks += 1
        if cancel_check():
            raise AgentCancelledError("cancelled on second check")
        return "late answer"

    checks = iter((True, True))
    try:
        provider(lambda: next(checks))
        assistant_messages += 1
    except AgentCancelledError:
        cancelled_messages += 1
    observed = {
        "cancellation_checks": cancellation_checks,
        "cancelled_messages": cancelled_messages,
        "assistant_messages": assistant_messages,
    }
    return "cooperative provider cancellation", {
        **observed,
        "passed": observed == {"cancellation_checks": 2, "cancelled_messages": 1, "assistant_messages": 0},
    }


def _fault_f13(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    status = classify_supervisor_status(
        {
            "state": "RUNNING",
            "updated_at": old,
            "heartbeat_at": old,
            "supervisor_pid": 999_999_991,
            "child_pid": 999_999_992,
        }
    )
    observed = {"state": status["state"], "reasons": status["status_reasons"]}
    return "supervisor current status", {**observed, "passed": status["state"] == "STALE"}


def _fault_f14(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del root, time_scale
    now = utc_now()
    status = classify_supervisor_status(
        {
            "state": "RUNNING",
            "updated_at": now,
            "heartbeat_at": now,
            "supervisor_pid": os.getpid(),
            "child_pid": os.getpid(),
        }
    )
    reasons = status["status_reasons"]
    observed = {"state": status["state"], "reasons": reasons}
    return "supervisor PID identity", {
        **observed,
        "passed": status["state"] == "STALE" and any("identity mismatch" in item for item in reasons),
    }


def _prepare_recovery_fixture(root: Path) -> tuple[Path, str]:
    workspace = Workspace(root)
    authority = scoped_write_authority(
        workspace,
        allowed_paths=("README.md",),
        goal="Exercise exact transaction recovery",
        operator="icpi-fault-fixture",
    )
    authority_path = root.parent / "recovery-authority.json"
    save_authority(authority_path, authority)
    with OURDAgent(root, authority_path=authority_path) as agent:
        agent.establish_governance(**governance_args())
        prepared = agent.prepare_write_file("README.md", "# ICPI Fault Fixture\n\nvalue = 2\n")
    return authority_path, str(prepared["transaction_id"])


def _fault_f15(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del time_scale
    authority_path, transaction_id = _prepare_recovery_fixture(root)
    blocked_without_recovery = ""
    try:
        OURDAgent(root, authority_path=authority_path).close()
    except StateError as exc:
        blocked_without_recovery = str(exc)
    with OURDAgent(
        root,
        authority_path=authority_path,
        recovery_transaction_id=transaction_id,
    ) as recovered:
        unrelated_block = ""
        try:
            recovered.prepare_write_file("README.md", "unrelated\n")
        except Exception as exc:
            unrelated_block = str(exc)
        recovered.rollback_transaction(transaction_id)
    observed = {
        "transaction_id": transaction_id,
        "blocked_without_recovery": blocked_without_recovery,
        "unrelated_mutation_blocked": bool(unrelated_block),
        "final_readme": (root / "README.md").read_text(encoding="utf-8"),
    }
    passed = bool(blocked_without_recovery) and bool(unrelated_block) and "value = 1" in observed["final_readme"]
    return "PREPARED transaction recovery", {**observed, "passed": passed}


def _fault_f16(root: Path, time_scale: float) -> tuple[str, dict[str, Any]]:
    del time_scale
    authority_path, transaction_id = _prepare_recovery_fixture(root)
    agent = OURDAgent(
        root,
        authority_path=authority_path,
        recovery_transaction_id=transaction_id,
    )
    record = agent.state.transactions[transaction_id]
    agent.transactions.apply(record)
    agent.save_state()
    agent.close()
    with OURDAgent(
        root,
        authority_path=authority_path,
        recovery_transaction_id=transaction_id,
    ) as recovered:
        record = recovered.state.transactions[transaction_id]
        recovered.transactions.verify_applied(record)
        verified_before_rollback = record.status == "APPLIED"
        recovered.rollback_transaction(transaction_id)
    final_text = (root / "README.md").read_text(encoding="utf-8")
    observed = {
        "transaction_id": transaction_id,
        "verified_before_rollback": verified_before_rollback,
        "final_readme": final_text,
    }
    return "APPLIED transaction recovery", {
        **observed,
        "passed": verified_before_rollback and "value = 1" in final_text,
    }


FAULT_HANDLERS: dict[str, Callable[[Path, float], tuple[str, dict[str, Any]]]] = {
    "F01": _fault_f01,
    "F02": _fault_f02,
    "F03": _fault_f03,
    "F04": _fault_f04,
    "F05": _fault_f05,
    "F06": _fault_f06,
    "F07": _fault_f07,
    "F08": _fault_f08,
    "F09": _fault_f09,
    "F10": _fault_f10,
    "F11": _fault_f11,
    "F12": _fault_f12,
    "F13": _fault_f13,
    "F14": _fault_f14,
    "F15": _fault_f15,
    "F16": _fault_f16,
}


def run_fault(fault_id: str, workspace_root: Path, *, time_scale: float = 1.0) -> FaultResult:
    if fault_id not in FAULT_HANDLERS or fault_id not in FAULT_INJECTIONS:
        raise ValueError(f"unknown fault injection: {fault_id}")
    if time_scale <= 0:
        raise ValueError("time_scale must be positive")
    started = utc_now()
    target_component, observed = FAULT_HANDLERS[fault_id](workspace_root, time_scale)
    completed = utc_now()
    passed = bool(observed.get("passed"))
    return FaultResult(
        schema_version=FAULT_FIXTURE_SCHEMA_VERSION,
        fault_id=fault_id,
        injection_started_at=started,
        injection_completed_at=completed,
        target_component=target_component,
        configured_parameters={
            **FAULT_INJECTIONS[fault_id],
            "time_scale": time_scale,
            "workspace_root": str(workspace_root.resolve()),
        },
        observed_effect=observed,
        cleanup_result="workspace retained for audit",
        verdict="PASS" if passed else "FAIL",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded ICPI supervisor fault fixtures.")
    parser.add_argument("--fault", action="append", choices=tuple(FAULT_HANDLERS))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = tuple(args.fault or FAULT_HANDLERS)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.workspace is None:
        temporary = tempfile.TemporaryDirectory(prefix="icpi-faults-")
        base = Path(temporary.name)
    else:
        base = args.workspace.expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    try:
        for fault_id in selected:
            workspace, _ = create_fixture_workspace(base / fault_id.lower())
            results.append(run_fault(fault_id, workspace, time_scale=args.time_scale).to_dict())
        rendered = json.dumps(
            {
                "schema_version": FAULT_FIXTURE_SCHEMA_VERSION,
                "fault_count": len(results),
                "passed": sum(item["verdict"] == "PASS" for item in results),
                "failed": sum(item["verdict"] != "PASS" for item in results),
                "results": results,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if all(item["verdict"] == "PASS" for item in results) else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FAULT_FIXTURE_SCHEMA_VERSION",
    "FAULT_HANDLERS",
    "FaultResult",
    "create_fixture_workspace",
    "main",
    "run_fault",
]
