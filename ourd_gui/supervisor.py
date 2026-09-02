from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ourd.persistence import atomic_write_text, redact

from .supervisor_lifecycle import SUPERVISOR_REPOSITORY_ENV, SUPERVISOR_SESSION_ENV


SUPERVISOR_SCHEMA_VERSION = 1
DEFAULT_HEARTBEAT_STALE_SECONDS = 5.0
SUPERVISOR_DEBUG_STDOUT_ENV = "OURD_SUPERVISOR_DEBUG_STDOUT"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"icpi-{timestamp}-{uuid.uuid4().hex[:10]}"


def _repository_from_args(arguments: Sequence[str]) -> Path:
    for index, argument in enumerate(arguments):
        if argument == "--repo" and index + 1 < len(arguments):
            return Path(arguments[index + 1]).expanduser().resolve()
        if argument.startswith("--repo="):
            return Path(argument.partition("=")[2]).expanduser().resolve()
    return Path.cwd().resolve()


def _redact_arguments(arguments: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for argument in arguments:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if argument in {"--api-key"}:
            redacted.append(argument)
            redact_next = True
            continue
        if argument.startswith("--api-key="):
            redacted.append("--api-key=<redacted>")
            continue
        redacted.append(argument)
    return redacted


def _debug_stdout_enabled(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _process_cmdline(pid: int) -> tuple[str, ...]:
    if pid <= 0:
        return ()
    try:
        content = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ()
    return tuple(
        part.decode("utf-8", errors="replace")
        for part in content.split(b"\0")
        if part
    )


def _process_identity(pid: int, expected_fragments: Sequence[str]) -> dict[str, Any]:
    command = _process_cmdline(pid)
    joined = " ".join(command)
    exists = bool(command)
    matched = exists and all(fragment in joined for fragment in expected_fragments)
    return {
        "pid": int(pid),
        "exists": exists,
        "matched": matched,
        "command": _redact_arguments(command),
        "expected_fragments": list(expected_fragments),
    }


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_supervisor_status(
    payload: Mapping[str, Any],
    *,
    heartbeat_stale_seconds: float = DEFAULT_HEARTBEAT_STALE_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = dict(payload)
    now_value = now or datetime.now(timezone.utc)
    updated = _parse_timestamp(observed.get("heartbeat_at") or observed.get("updated_at"))
    age_seconds = (
        max(0.0, (now_value - updated).total_seconds())
        if updated is not None
        else None
    )
    supervisor_identity = _process_identity(
        int(observed.get("supervisor_pid", 0) or 0),
        ("oiec_stm_sr_agenticpi.py", "--supervisor-mode"),
    )
    child_identity = _process_identity(
        int(observed.get("child_pid", 0) or 0),
        ("oiec_stm_sr_agenticpi.py",),
    )
    raw_state = str(observed.get("state", "UNKNOWN"))
    reasons: list[str] = []
    if raw_state in {"STARTING", "RUNNING", "RESTARTING", "STOPPING"}:
        if age_seconds is None or age_seconds > heartbeat_stale_seconds:
            reasons.append("heartbeat stale")
        if not supervisor_identity["matched"]:
            reasons.append("supervisor PID identity mismatch")
        if raw_state in {"RUNNING", "STOPPING"} and not child_identity["matched"]:
            reasons.append("child PID identity mismatch")
    classified_state = "STALE" if reasons else raw_state
    observed.update(
        {
            "raw_state": raw_state,
            "state": classified_state,
            "status_reasons": reasons,
            "heartbeat_age_seconds": age_seconds,
            "supervisor_identity": supervisor_identity,
            "child_identity": child_identity,
        }
    )
    return observed


def read_supervisor_status(
    repository_root: Path,
    *,
    heartbeat_stale_seconds: float = DEFAULT_HEARTBEAT_STALE_SECONDS,
) -> dict[str, Any]:
    path = repository_root.expanduser().resolve() / ".ourd-agent" / "supervisor" / "current.json"
    if not path.exists():
        return {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "state": "INACTIVE",
            "raw_state": "INACTIVE",
            "status_reasons": ["current status does not exist"],
            "path": str(path),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "state": "STALE",
            "raw_state": "INVALID",
            "status_reasons": [f"invalid current status: {type(exc).__name__}: {exc}"],
            "path": str(path),
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "state": "STALE",
            "raw_state": "INVALID",
            "status_reasons": ["current status is not an object"],
            "path": str(path),
        }
    return classify_supervisor_status(
        payload,
        heartbeat_stale_seconds=heartbeat_stale_seconds,
    )


class SupervisorRuntime:
    def __init__(
        self,
        repository_root: Path,
        session_id: str,
        *,
        debug_stdout: bool = False,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.session_id = session_id
        self.debug_stdout = debug_stdout
        self.root = self.repository_root / ".ourd-agent" / "supervisor"
        self.logs = self.root / "logs"
        self.incidents = self.root / "incidents"
        self.current_path = self.root / "current.json"
        self.events_path = self.root / "events.jsonl"
        self.log_path = self.logs / f"{session_id}.log"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.incidents.mkdir(parents=True, exist_ok=True)

    def debug_record(self, stream: str, payload: Mapping[str, Any]) -> None:
        if not self.debug_stdout:
            return
        record = {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "session_id": self.session_id,
            "debug_stream": stream,
            "payload": redact(dict(payload)),
        }
        print(json.dumps(record, sort_keys=True, ensure_ascii=False), flush=True)

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.debug_record("supervisor_event", record)

    def status(
        self,
        state: str,
        *,
        child_pid: int = 0,
        restart_count: int = 0,
        exit_code: int | None = None,
        message: str = "",
    ) -> None:
        timestamp = _utc_now()
        payload = {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "updated_at": timestamp,
            "heartbeat_at": timestamp,
            "session_id": self.session_id,
            "state": state,
            "supervisor_pid": os.getpid(),
            "child_pid": child_pid,
            "restart_count": restart_count,
            "exit_code": exit_code,
            "message": message,
            "log_path": str(self.log_path),
            "events_path": str(self.events_path),
        }
        atomic_write_text(
            self.current_path,
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        if state != "RUNNING":
            self.debug_record("supervisor_status", payload)

    def incident(
        self,
        *,
        child_pid: int,
        exit_code: int,
        restart_count: int,
        command: Sequence[str],
    ) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.incidents / f"{timestamp}-{self.session_id}-r{restart_count}.json"
        payload = {
            "schema_version": SUPERVISOR_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "session_id": self.session_id,
            "child_pid": child_pid,
            "exit_code": exit_code,
            "restart_count": restart_count,
            "command": _redact_arguments(command),
            "log_path": str(self.log_path),
        }
        atomic_write_text(
            path,
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        self.debug_record("supervisor_incident", payload)
        return path


def _terminate_process_group(process: subprocess.Popen[Any], grace_seconds: float = 8.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=max(0.1, grace_seconds))
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=2.0)


def supervise_command(
    command: Sequence[str],
    *,
    repository_root: Path,
    max_restarts: int = 2,
    poll_seconds: float = 1.0,
    environment: Mapping[str, str] | None = None,
    restart_delay_scale: float = 1.0,
    debug_stdout: bool = False,
) -> int:
    if not command:
        raise ValueError("supervisor command cannot be empty")
    if max_restarts < 0:
        raise ValueError("max_restarts must be non-negative")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    if restart_delay_scale < 0:
        raise ValueError("restart_delay_scale must be non-negative")

    session_id = _session_id()
    runtime = SupervisorRuntime(
        repository_root,
        session_id,
        debug_stdout=debug_stdout or _debug_stdout_enabled(os.getenv(SUPERVISOR_DEBUG_STDOUT_ENV)),
    )
    stop_requested = False

    def tee_child_output(
        process: subprocess.Popen[Any],
        log_handle: Any,
        *,
        restart_count: int,
    ) -> threading.Thread | None:
        stream = process.stdout
        if stream is None:
            return None

        def copy() -> None:
            try:
                for line in stream:
                    log_handle.write(line)
                    log_handle.flush()
                    runtime.debug_record(
                        "child_output",
                        {
                            "child_pid": process.pid,
                            "restart_count": restart_count,
                            "line": line.rstrip("\n"),
                        },
                    )
            finally:
                stream.close()

        thread = threading.Thread(
            target=copy,
            name=f"icpi-supervisor-child-output-{process.pid}",
            daemon=True,
        )
        thread.start()
        return thread

    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        nonlocal stop_requested
        stop_requested = True

    previous_handlers: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)

    restart_count = 0
    runtime.event(
        "SUPERVISOR_STARTED",
        {
            "supervisor_pid": os.getpid(),
            "command": _redact_arguments(command),
            "max_restarts": max_restarts,
        },
    )
    runtime.status("STARTING", restart_count=restart_count)

    try:
        with runtime.log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
            while True:
                log_handle.write(
                    f"[{_utc_now()}] supervisor launch restart_count={restart_count}\n"
                )
                child_environment = {
                    **os.environ,
                    **dict(environment or {}),
                    SUPERVISOR_SESSION_ENV: session_id,
                    SUPERVISOR_REPOSITORY_ENV: str(repository_root.resolve()),
                }
                if runtime.debug_stdout:
                    child_environment[SUPERVISOR_DEBUG_STDOUT_ENV] = "1"
                process = subprocess.Popen(
                    list(command),
                    cwd=repository_root,
                    stdout=subprocess.PIPE if runtime.debug_stdout else log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                    env=child_environment,
                )
                output_thread = tee_child_output(
                    process,
                    log_handle,
                    restart_count=restart_count,
                )
                runtime.event(
                    "CHILD_STARTED",
                    {"child_pid": process.pid, "restart_count": restart_count},
                )
                runtime.status(
                    "RUNNING",
                    child_pid=process.pid,
                    restart_count=restart_count,
                )

                while process.poll() is None and not stop_requested:
                    runtime.status(
                        "RUNNING",
                        child_pid=process.pid,
                        restart_count=restart_count,
                    )
                    time.sleep(poll_seconds)

                if stop_requested and process.poll() is None:
                    runtime.event("SHUTDOWN_REQUESTED", {"child_pid": process.pid})
                    runtime.status(
                        "STOPPING",
                        child_pid=process.pid,
                        restart_count=restart_count,
                    )
                    _terminate_process_group(process)

                exit_code = process.wait()
                if output_thread is not None:
                    output_thread.join(timeout=2.0)
                runtime.event(
                    "CHILD_EXITED",
                    {
                        "child_pid": process.pid,
                        "exit_code": exit_code,
                        "restart_count": restart_count,
                    },
                )
                if stop_requested or exit_code == 0:
                    runtime.status(
                        "STOPPED",
                        child_pid=process.pid,
                        restart_count=restart_count,
                        exit_code=exit_code,
                        message="shutdown requested" if stop_requested else "child exited cleanly",
                    )
                    runtime.event(
                        "SUPERVISOR_STOPPED",
                        {"exit_code": exit_code, "restart_count": restart_count},
                    )
                    return 0 if stop_requested else exit_code

                incident_path = runtime.incident(
                    child_pid=process.pid,
                    exit_code=exit_code,
                    restart_count=restart_count,
                    command=command,
                )
                runtime.event(
                    "INCIDENT_RECORDED",
                    {"path": str(incident_path), "exit_code": exit_code},
                )
                if restart_count >= max_restarts:
                    runtime.status(
                        "FAILED",
                        child_pid=process.pid,
                        restart_count=restart_count,
                        exit_code=exit_code,
                        message="restart circuit open",
                    )
                    runtime.event(
                        "CIRCUIT_OPEN",
                        {"exit_code": exit_code, "restart_count": restart_count},
                    )
                    return exit_code or 1

                restart_count += 1
                delay = min(2 ** (restart_count - 1), 8) * restart_delay_scale
                runtime.status(
                    "RESTARTING",
                    child_pid=process.pid,
                    restart_count=restart_count,
                    exit_code=exit_code,
                    message=f"restart in {delay} seconds",
                )
                runtime.event(
                    "RESTART_SCHEDULED",
                    {"delay_seconds": delay, "restart_count": restart_count},
                )
                time.sleep(delay)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def run_supervisor(
    child_arguments: Sequence[str],
    *,
    launcher_path: Path,
    max_restarts: int = 2,
    poll_seconds: float = 1.0,
    debug_stdout: bool = False,
) -> int:
    repository_root = _repository_from_args(child_arguments)
    command = [sys.executable, str(launcher_path.resolve()), *child_arguments]
    return supervise_command(
        command,
        repository_root=repository_root,
        max_restarts=max_restarts,
        poll_seconds=poll_seconds,
        debug_stdout=debug_stdout,
    )


__all__ = [
    "DEFAULT_HEARTBEAT_STALE_SECONDS",
    "SUPERVISOR_DEBUG_STDOUT_ENV",
    "SUPERVISOR_SCHEMA_VERSION",
    "SupervisorRuntime",
    "classify_supervisor_status",
    "read_supervisor_status",
    "run_supervisor",
    "supervise_command",
]
