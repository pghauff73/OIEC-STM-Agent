from __future__ import annotations

import argparse
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Mapping, Optional, Sequence

from ourd.egcf.models import CommandDefinition, CompiledWorkflow, ExecutionPlan, FailureRecord
from ourd.errors import PolicyError
from ourd.interaction import (
    InteractionSessionSnapshot,
    PinnedContextSet,
    build_context_envelope,
    build_interaction_confirmation,
    build_interaction_confirmation_receipt,
    build_pinned_context_envelope,
    compare_context_envelopes,
    dispatch_interaction,
    pinned_context_freshness,
    require_fresh_pinned_context,
    route_interaction,
)
from ourd.providers import (
    ProviderConfig,
    QWEN38_Q2_K_MODEL_PATH,
    QWEN38_Q2_K_SHA256,
)
from ourd.workspace import Workspace

from .command_palette import CommandPaletteRegistry, PaletteCommand
from .commands import ApprovalRequest, CommandRequest, ExecutionRequest, ObjectiveRequest, ReplayRequest, safe_default_modifiers
from .controller import GuiController
from .events import AgentEvent, AgentEventType
from .formal_writing_controller import FormalWritingController
from .formal_writing_gui import confirm_governed_write
from .formal_writing_models import FormalWritingExecutionOptions, FormalWritingFormState
from .governance_models import build_capability_ladder, matching_approval
from .icpi_prompt import (
    command_suggestions,
    format_pinned_route_preview,
    projection_surface,
)
from .model_backend import model_backend_info
from .persistence import GuiPreferencesStore
from .qwen_bootstrap import (
    QWEN38_FAST_PRODUCT_ALIAS,
    QwenBootstrapError,
    QwenBootstrapResult,
    ensure_qwen38_fast,
)
from .selection_trace import SelectionTrace
from .supervisor_lifecycle import AppLifecycleRecorder
from .views.approvals import ApprovalDialog
from .views.command_palette import CommandPaletteDialog
from .views.shell import WorkbenchShell
from .widgets.status_badge import StatusBadge


EXACT_AGENTICPI_EXECUTABLE = "oiec-stm-sr-AgentICPI"


def _option_supplied(arguments: Sequence[str], name: str) -> bool:
    return any(argument == name or argument.startswith(f"{name}=") for argument in arguments)


def automatic_qwen_bootstrap_requested(
    *,
    arguments: Sequence[str],
    executable_name: str,
    explicit_setting: bool | None,
    environment: Mapping[str, str] | None = None,
) -> bool:
    if explicit_setting is not None:
        return explicit_setting
    if Path(executable_name).name != EXACT_AGENTICPI_EXECUTABLE:
        return False
    env = os.environ if environment is None else environment
    if any(
        _option_supplied(arguments, name)
        for name in ("--provider", "--model", "--runner-path", "--model-path")
    ):
        return False
    return not any(
        str(env.get(name, "")).strip()
        for name in ("OURD_PROVIDER", "OURD_MODEL", "OURD_LLAMA_RUNNER", "OURD_LLAMA_MODEL_PATH")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-sr-agent-icpi",
        description="Interactive governed OIEC-STM-SR-AgentICPI workbench",
    )
    parser.add_argument("--repo", default=".", help="Repository/workspace root")
    parser.add_argument("--authority", type=Path, help="External authority manifest")
    parser.add_argument(
        "--provider",
        default=os.getenv("OURD_PROVIDER", "llama_cpp_process"),
        choices=["llama_cpp_process"],
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OURD_MODEL", "qwen3.8-27b-direct"),
        help="Agent Chat model and backend metadata shown in the GUI",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OURD_BASE_URL", ""),
        help="Deprecated compatibility field; direct process mode does not use a URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OURD_API_KEY", ""),
        help="Deprecated compatibility field; direct process mode does not use API keys",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("OURD_REASONING_EFFORT", ""),
        choices=["", "none", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument(
        "--json-object-output",
        action="store_true",
        default=os.getenv("OURD_JSON_OBJECT_OUTPUT", "").strip().lower()
        in {"1", "true", "yes", "on"},
        help="Deprecated compatibility flag; direct process output is grammar-first JSON",
    )
    parser.add_argument(
        "--response-temperature-bp",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_TEMPERATURE_BP", "-1")),
    )
    parser.add_argument(
        "--response-top-p-bp",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_TOP_P_BP", "-1")),
    )
    parser.add_argument(
        "--response-seed",
        type=int,
        default=int(os.getenv("OURD_RESPONSE_SEED", "-1")),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=int(os.getenv("OURD_MAX_OUTPUT_TOKENS", "2048")),
    )
    parser.add_argument(
        "--context-budget",
        type=int,
        default=int(os.getenv("OURD_CONTEXT_BUDGET", "6000")),
        help="Agent Chat context budget shown in the backend panel",
    )
    parser.add_argument(
        "--runtime-context-tokens",
        type=int,
        default=int(os.getenv("OURD_RUNTIME_CONTEXT", "0")),
        help="Known provider runtime context; zero disables the combined runtime bound",
    )
    parser.add_argument(
        "--context-safety-margin",
        type=int,
        default=int(os.getenv("OURD_CONTEXT_SAFETY_MARGIN", "512")),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("OURD_TIMEOUT_SECONDS", "600")),
    )
    parser.add_argument(
        "--transport-retries",
        type=int,
        default=int(os.getenv("OURD_TRANSPORT_RETRIES", "0")),
    )
    parser.add_argument(
        "--max-reasoning-samples",
        type=int,
        default=int(os.getenv("OURD_MAX_REASONING_SAMPLES", "16")),
    )
    parser.add_argument("--runner-path", default=os.getenv("OURD_LLAMA_RUNNER", ""))
    parser.add_argument(
        "--model-path",
        default=os.getenv("OURD_LLAMA_MODEL_PATH", QWEN38_Q2_K_MODEL_PATH),
    )
    parser.add_argument(
        "--expected-model-sha256",
        default=os.getenv("OURD_LLAMA_MODEL_SHA256", QWEN38_Q2_K_SHA256),
    )
    parser.add_argument(
        "--llama-cpp-build-dir",
        default=os.getenv("OURD_LLAMA_CPP_BUILD_DIR", ""),
    )
    parser.add_argument(
        "--llama-cpp-root",
        default=os.getenv("OURD_LLAMA_CPP_ROOT", ""),
    )
    parser.add_argument(
        "--llama-grammar-dir",
        default=os.getenv("OURD_LLAMA_GRAMMAR_DIR", ""),
    )
    parser.add_argument(
        "--llama-context",
        type=int,
        default=int(os.getenv("OURD_LLAMA_CONTEXT", "8192")),
    )
    parser.add_argument(
        "--llama-gpu-layers",
        type=int,
        default=int(os.getenv("OURD_LLAMA_GPU_LAYERS", "-1")),
    )
    parser.add_argument(
        "--llama-threads",
        type=int,
        default=int(os.getenv("OURD_LLAMA_THREADS", "0")),
    )
    parser.add_argument(
        "--llama-seed",
        type=int,
        default=int(os.getenv("OURD_LLAMA_SEED", "1234")),
    )
    parser.add_argument(
        "--llama-temperature-bp",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TEMPERATURE_BP", "1000")),
    )
    parser.add_argument(
        "--llama-top-p-bp",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TOP_P_BP", "9500")),
    )
    parser.add_argument(
        "--llama-top-k",
        type=int,
        default=int(os.getenv("OURD_LLAMA_TOP_K", "40")),
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=80,
        help="Maximum governed model/tool steps per chat turn",
    )
    qwen_bootstrap = parser.add_mutually_exclusive_group()
    qwen_bootstrap.add_argument(
        "--auto-qwen",
        dest="auto_qwen",
        action="store_true",
        default=None,
        help="Apply the direct Qwen profile before opening ICPI; exact runner and GGUF paths are still required",
    )
    qwen_bootstrap.add_argument(
        "--no-auto-qwen",
        dest="auto_qwen",
        action="store_false",
        help="Disable automatic direct Qwen profile selection for this invocation",
    )
    parser.add_argument(
        "--qwen-model",
        default=os.getenv("OIEC_ICPI_QWEN_MODEL", QWEN38_FAST_PRODUCT_ALIAS),
        help=(
            "Required direct Qwen profile label for automatic selection; "
            f"{QWEN38_FAST_PRODUCT_ALIAS!r} maps to qwen3.8-27b-direct"
        ),
    )
    parser.add_argument(
        "--qwen-startup-timeout",
        type=float,
        default=float(os.getenv("OIEC_ICPI_QWEN_STARTUP_TIMEOUT", "30")),
        help="Deprecated compatibility timeout; direct process startup is handled by provider preflight",
    )
    parser.add_argument(
        "--qwen-warmup-timeout",
        type=float,
        default=float(os.getenv("OIEC_ICPI_QWEN_WARMUP_TIMEOUT", "180")),
        help="Deprecated compatibility timeout; direct process warmup is handled by provider preflight",
    )
    parser.add_argument(
        "--no-qwen-warmup",
        action="store_true",
        help="Deprecated compatibility flag; direct process preflight does not warm through a service",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Build and close the workbench without entering the event loop",
    )
    return parser


class OURDWorkbench(tk.Tk):
    POLL_MS = 50

    def __init__(
        self,
        repository_root: Path,
        *,
        authority_path: Path | None = None,
        provider_kind: str = "llama_cpp_process",
        model: str = "qwen3.8-27b-direct",
        base_url: str = "",
        context_budget: int = 6000,
        runtime_context_tokens: int = 0,
        context_safety_margin_tokens: int = 512,
        api_key: str = "",
        reasoning_effort: str = "",
        json_object_output: bool = False,
        response_temperature_bp: int = -1,
        response_top_p_bp: int = -1,
        response_seed: int = -1,
        max_output_tokens: int = 2048,
        timeout_seconds: float = 600.0,
        transport_retries: int = 0,
        max_reasoning_samples: int = 16,
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
        max_steps: int = 80,
        qwen_bootstrap_result: QwenBootstrapResult | None = None,
        lifecycle_recorder: AppLifecycleRecorder | None = None,
    ) -> None:
        initialization_started = time.perf_counter()
        super().__init__()
        self._closing = False
        self._restore_after_id: str | None = None
        self._poll_after_id: str | None = None
        self._heartbeat_after_id: str | None = None
        self.repository_root = repository_root.resolve()
        self.authority_path = authority_path.resolve() if authority_path is not None else None
        self.lifecycle_recorder = lifecycle_recorder or AppLifecycleRecorder.from_environment(
            self.repository_root
        )
        self.icpi_workspace = Workspace(self.repository_root)
        self.pinned_context = PinnedContextSet()
        self.pinned_context_envelope = None
        self.context_delta = None
        self.preferences_store = GuiPreferencesStore(self.repository_root)
        self.preferences = self.preferences_store.load()
        self._apply_font_scale(self.preferences.font_scale)
        self.open_file = self.preferences.open_file
        self.model_backend = model_backend_info(
            model=model,
            base_url=base_url,
            context_tokens=context_budget,
        )
        if qwen_bootstrap_result is not None:
            bootstrap = qwen_bootstrap_result
            backend_payload = self.model_backend.to_dict()
            backend_payload.update(
                {
                    "health": "ready" if bootstrap.resident else "verified",
                    "memory": (
                        f"model={bootstrap.model_size} bytes; "
                        f"vram={bootstrap.size_vram} bytes"
                    ),
                    "device_residency": (
                        "verified direct process runtime"
                        if bootstrap.resident
                        else "verified but not preloaded"
                    ),
                    "provenance": (
                        "automatic ICPI direct Qwen profile; "
                        f"alias={bootstrap.product_alias}; "
                        f"digest={bootstrap.model_digest}"
                    ),
                }
            )
            self.model_backend = type(self.model_backend)(**backend_payload)
        self.title("OIEC-STM-SR-AgentICPI Workbench")
        self.geometry(self.preferences.window_geometry)
        self.minsize(900, 600)
        self.controller = GuiController(
            self.repository_root,
            authority_path=authority_path,
            provider_config=ProviderConfig(
                model=model,
                provider_kind=provider_kind,
                base_url=base_url,
                api_key=api_key,
                reasoning_effort=reasoning_effort,
                json_object_output=json_object_output,
                response_temperature_bp=response_temperature_bp,
                response_top_p_bp=response_top_p_bp,
                response_seed=response_seed,
                max_output_tokens=max(1, max_output_tokens),
                context_budget_tokens=max(256, context_budget),
                runtime_context_tokens=max(0, runtime_context_tokens),
                context_safety_margin_tokens=max(0, context_safety_margin_tokens),
                timeout_seconds=max(1.0, timeout_seconds),
                max_transport_retries=max(0, min(transport_retries, 5)),
                max_reasoning_samples=max(1, min(max_reasoning_samples, 64)),
                runner_path=runner_path,
                model_path=model_path,
                expected_model_sha256=expected_model_sha256,
                llama_cpp_root=llama_cpp_root,
                llama_cpp_build_dir=llama_cpp_build_dir,
                llama_grammar_dir=llama_grammar_dir,
                llama_context_tokens=max(256, llama_context_tokens),
                llama_gpu_layers=llama_gpu_layers,
                llama_threads=max(0, llama_threads),
                llama_seed=llama_seed,
                llama_temperature_bp=llama_temperature_bp,
                llama_top_p_bp=llama_top_p_bp,
                llama_top_k=llama_top_k,
            ),
            max_agent_steps=max(1, max_steps),
        )
        self.formal_writing_controller = FormalWritingController(
            self.repository_root,
            authority_path=self.authority_path,
        )
        if qwen_bootstrap_result is not None:
            self.controller.record_qwen_bootstrap(qwen_bootstrap_result)
        self.controller.bus.subscribe(self._handle_event)
        self._build_toolbar()
        self.shell = WorkbenchShell(
            self,
            self.repository_root,
            self.controller.repository,
            on_task_selected=self._select_task,
            on_object_selected=self._select_object,
            on_file_selected=self._select_file,
            on_approve_plan=self._approve_plan,
            on_execute_plan=self._execute_plan,
            on_rollback_plan=self._rollback_plan,
            on_simulate_plan=self._replay_plan,
            on_edit_plan_scope=self._edit_plan_scope,
            on_create_regression=self._create_regression,
            on_semantic_command=self._submit_semantic_command,
            model_backend=self.model_backend,
            on_model_preflight=self._prepare_model_preflight,
            on_prepare_command=self._prefill,
            event_supplier=self.controller.journal.events,
            on_replay_cursor=self.controller.set_replay_cursor,
            on_plan_replay=self._replay_plan,
            on_assurance_export=self._export_assurance,
            on_evidence_export=self._export_evidence,
            performance_supplier=self.controller.performance_snapshot,
            on_chat_send=self._send_chat,
            on_chat_stop=self._stop_chat,
            on_new_chat=self._new_chat,
            on_chat_preview=self._preview_chat,
            on_chat_suggestions=command_suggestions,
            on_formal_writing_submit=self._submit_formal_writing,
            on_formal_writing_cancel=self._cancel_formal_writing,
            on_formal_writing_prepare=self._prepare_formal_writing,
            on_formal_writing_authority=self._set_formal_writing_authority,
            formal_writing_authority_path=self.authority_path,
        )
        self.shell.pack(fill="both", expand=True)
        self.shell.set_pinned_context(self.pinned_context)
        self.shell.set_context_delta(self.context_delta)
        self.shell.render_state(self.controller.state)
        self._build_command_bar()
        self.palette = self._build_palette()
        self.bind_all("<Control-k>", self._open_palette)
        self.bind_all("<Control-l>", lambda event: self._show_chat())
        self.bind_all("<Alt-Left>", lambda event: self.controller.navigate_back())
        self.bind_all("<Alt-Right>", lambda event: self.controller.navigate_forward())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._restore_after_id = self.after_idle(self._restore_preferences)
        self._poll_after_id = self.after(self.POLL_MS, self._poll)
        self._heartbeat_after_id = self.after(1_000, self._lifecycle_heartbeat)
        self.controller.performance.record_ms(
            "gui.initialize",
            (time.perf_counter() - initialization_started) * 1_000,
        )
        self.lifecycle_recorder.startup_ready(
            gui_session_id=self.controller.session_id,
            source_snapshot=self.controller.gateway.snapshot(),
            event_head=self.controller.state.event_head,
        )

    def _apply_font_scale(self, scale: float) -> None:
        scale = max(0.75, min(float(scale), 2.0))
        for name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkFixedFont",
            "TkMenuFont",
            "TkHeadingFont",
        ):
            try:
                font = tkfont.nametofont(name)
                font.configure(size=max(8, round(abs(font.cget("size")) * scale)))
            except tk.TclError:
                continue

    def _restore_preferences(self) -> None:
        self.shell.apply_preferences(self.preferences)
        if self.open_file:
            path = self.repository_root / self.open_file
            if path.is_file():
                self._select_file(self.open_file)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, padding=(6, 4))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text=f"Repository: {self.repository_root}").pack(side="left", padx=(0, 12))
        self.snapshot_label = ttk.Label(toolbar, text="Snapshot: loading")
        self.snapshot_label.pack(side="left", padx=(0, 12))
        ttk.Label(
            toolbar,
            text=f"Model: {self.model_backend.backend} / {self.model_backend.model}",
        ).pack(side="left", padx=(0, 12))
        self.capability_badge = StatusBadge(toolbar, "C0-C2", "qualified")
        self.capability_badge.pack(side="left", padx=3)
        self.worker_badge = StatusBadge(toolbar, "IDLE", "neutral")
        self.worker_badge.pack(side="right", padx=3)
        self.event_head_label = ttk.Label(toolbar, text="Event head: none")
        self.event_head_label.pack(side="right", padx=8)

    def _build_command_bar(self) -> None:
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Label(bar, text="ICPI Objective").pack(side="left", padx=(0, 4))
        self.prompt = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.prompt)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda event: self._submit())
        self.simulate = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Simulate", variable=self.simulate).pack(side="left", padx=6)
        ttk.Button(bar, text="Compile / Inspect", command=self._submit).pack(side="left")

    def _build_palette(self) -> CommandPaletteRegistry:
        commands = [
                PaletteCommand(
                    "gui.agent_chat",
                    "Open Agent Chat",
                    "Agent",
                    "Open the governed multi-turn OIEC-STM-Agent chat composer.",
                    self._show_chat,
                ),
                PaletteCommand(
                    "ourd.model",
                    "Model Scope",
                    "OURD",
                    "Prepare an OURD domain-model objective in the safe command bar.",
                    lambda: self._prefill("ourd model "),
                ),
                PaletteCommand(
                    "iurm.pairwise",
                    "Generate Pairwise Tests",
                    "IURM",
                    "Prepare an experimental pairwise-coverage objective.",
                    lambda: self._prefill("iurm pairwise "),
                ),
                PaletteCommand(
                    "ieps.gate",
                    "Run Evidence Gate",
                    "IEPS",
                    "Prepare an evidence-gate objective; execution remains dry-run by default.",
                    lambda: self._prefill("ieps gate "),
                ),
                PaletteCommand(
                    "eon.simulate",
                    "Simulate Current Action",
                    "EON",
                    "Enable simulation and open the governed EON inspector.",
                    self._prepare_simulation,
                ),
                PaletteCommand(
                    "cfel.classify",
                    "Classify Failure",
                    "CFEL",
                    "Open CFEL records and prepare a failure-classification objective.",
                    self._prepare_failure_classification,
                ),
                PaletteCommand(
                    "algorithm.trace",
                    "Show Selection Trace",
                    "Algorithm",
                    "Open the interactive qualified-algorithm selection trace.",
                    self.shell.show_selection,
                ),
                PaletteCommand(
                    "workflow.graph",
                    "Show Workflow DAG",
                    "Workflow",
                    "Open the compiled governed workflow graph.",
                    self.shell.show_workflow,
                ),
                PaletteCommand(
                    "ourd.graph",
                    "Show OURD Graph",
                    "OURD",
                    "Open canonical OURD graph output or labelled GUI task references.",
                    self.shell.show_ourd,
                ),
                PaletteCommand(
                    "iurm.dimensions",
                    "Show Dimension Explorer",
                    "IURM",
                    "Open dimensions, baselines, interactions, and MVD returned by the core.",
                    self.shell.show_iurm,
                ),
                PaletteCommand(
                    "trace.timeline",
                    "Show Event Trace",
                    "Trace",
                    "Open the append-only GUI/core event timeline.",
                    self.shell.show_trace,
                ),
                PaletteCommand(
                    "replay.events",
                    "Replay GUI Events",
                    "Replay",
                    "Inspect the append-only GUI event projection without re-executing the core.",
                    self.shell.show_replay,
                ),
                PaletteCommand(
                    "replay.compare",
                    "Compare Runs",
                    "Replay",
                    "Compare algorithms, evidence, files, failures, approvals, artifacts, and usage.",
                    self.shell.show_comparison,
                ),
                PaletteCommand(
                    "repository.explorer",
                    "Show Repository",
                    "Repository",
                    "Open the read-only repository explorer.",
                    self.shell.show_repository,
                ),
                PaletteCommand(
                    "artifact.latest",
                    "Open Artifacts",
                    "Artifact",
                    "Open the provenance-aware artifact workbench.",
                    self.shell.show_artifacts,
                ),
                PaletteCommand(
                    "assurance.records",
                    "Show Assurance Records",
                    "Assurance",
                    "Inspect and export completed assurance cases without changing canonical state.",
                    self.shell.show_assurance,
                ),
            ]
        definitions = [
            record
            for record in self.controller.repository.list(
                "command-definition",
                active_only=True,
            )
            if isinstance(record, CommandDefinition)
        ]
        definitions.sort(key=lambda item: item.command_id)
        for definition in definitions:
            level = definition.capability_query.get("level", "C0")
            commands.append(
                PaletteCommand(
                    f"semantic.{definition.command_id}",
                    definition.command_id,
                    "Semantic Command",
                    (
                        f"{level} / {definition.risk_policy} / {definition.approval_policy}. "
                        f"{definition.description or 'Checked-in semantic command.'}"
                    ),
                    lambda command_id=definition.command_id: self._prefill_terminal(
                        f"{command_id} {{}}"
                    ),
                )
            )
        return CommandPaletteRegistry(commands)

    def _open_palette(self, event: tk.Event | None = None) -> str:
        del event
        CommandPaletteDialog(self, self.palette)
        return "break"

    def _prefill(self, text: str) -> None:
        self.prompt.set(text)
        self.focus_force()

    def _prefill_terminal(self, text: str) -> None:
        self.shell.show_terminal()
        self.shell.terminal.command.set(text)

    def _prepare_simulation(self) -> None:
        self.simulate.set(True)
        self.shell.show_eon()

    def _prepare_failure_classification(self) -> None:
        self.shell.show_cfel()
        self._prefill("cfel classify ")

    def _prepare_model_preflight(self) -> None:
        self.shell.conversation.append(
            "GUI",
            "Agent Chat performs provider preflight at the start of each turn. Use the CLI --preflight option for a standalone health report.",
        )

    def _show_chat(self) -> str:
        self.shell.show_chat()
        return "break"

    def _send_chat(self, message: str) -> None:
        self.shell.show_chat()
        evidence_ids = self._known_evidence_ids()
        try:
            source_snapshot = self.controller.gateway.snapshot()
            if not message.strip().startswith("/"):
                require_fresh_pinned_context(
                    self.pinned_context,
                    self.pinned_context_envelope,
                    current_source_snapshot_hash=source_snapshot,
                )
            routed_message = self.pinned_context.apply_to(
                message,
                self.icpi_workspace,
            )
            route = route_interaction(
                routed_message,
                self.icpi_workspace,
                known_evidence_ids=evidence_ids,
            )
        except (PolicyError, ValueError) as exc:
            if self.pinned_context.paths:
                try:
                    observed_envelope = self._build_pinned_context_envelope(
                        self.pinned_context,
                        source_snapshot_hash=self.controller.gateway.snapshot(),
                    )
                    if observed_envelope is not None and self.pinned_context_envelope is not None:
                        self.context_delta = compare_context_envelopes(
                            self.pinned_context_envelope,
                            observed_envelope,
                        )
                        self.shell.set_context_envelope(self.pinned_context_envelope)
                        self.shell.set_context_delta(self.context_delta)
                        self.controller.record_pinned_context_transition(
                            route=None,
                            action="STALE_CONTEXT_BLOCK",
                            pinned_context=self.pinned_context,
                            context_envelope=self.pinned_context_envelope,
                            context_delta=self.context_delta,
                        )
                        self.shell.show_context()
                except (OSError, PolicyError, ValueError):
                    pass
            messagebox.showerror("ICPI request blocked", str(exc), parent=self)
            return
        freshness = pinned_context_freshness(
            self.pinned_context,
            self.pinned_context_envelope,
            current_source_snapshot_hash=source_snapshot,
        )
        directive = dispatch_interaction(
            route,
            InteractionSessionSnapshot(
                repository_root=str(self.repository_root),
                source_snapshot=source_snapshot,
                provider=self.controller.gateway.provider_config.provider_kind,
                model=self.controller.gateway.provider_config.model,
                authority_task_id="",
                mode="governed-gui",
                context_message_count=max(
                    0,
                    len(self.controller.state.chat_messages)
                    - self.controller.state.chat_context_start,
                ),
                pinned_context_count=len(self.pinned_context.paths),
                pinned_context_signature=self.pinned_context.signature,
                pinned_context_envelope_id=(
                    self.pinned_context_envelope.envelope_id
                    if self.pinned_context_envelope is not None
                    else ""
                ),
                pinned_context_source_snapshot=(
                    self.pinned_context_envelope.source_snapshot_hash
                    if self.pinned_context_envelope is not None
                    else ""
                ),
                pinned_context_freshness=freshness,
                active_operation=bool(self.controller._active_chat_operation_id),
            ),
        )
        if directive.action == "RUN_AGENT":
            try:
                envelope = build_context_envelope(
                    route,
                    self.icpi_workspace,
                    source_snapshot_hash=source_snapshot,
                    known_evidence_ids=evidence_ids,
                )
            except (OSError, PolicyError, ValueError) as exc:
                messagebox.showerror("ICPI context blocked", str(exc), parent=self)
                return
            confirmation = None
            confirmation_receipt = None
            if directive.requires_confirmation:
                try:
                    confirmation = build_interaction_confirmation(
                        directive,
                        context_envelope=envelope,
                        pinned_context=self.pinned_context,
                        pinned_context_envelope=self.pinned_context_envelope,
                    )
                except (PolicyError, ValueError) as exc:
                    messagebox.showerror("ICPI confirmation blocked", str(exc), parent=self)
                    return
                accepted = messagebox.askyesno(
                    confirmation.title,
                    confirmation.render_text(),
                    parent=self,
                    default=messagebox.NO,
                )
                confirmation_receipt = build_interaction_confirmation_receipt(
                    confirmation,
                    accepted=accepted,
                )
                self.controller.record_confirmation_receipt(confirmation_receipt)
                if not accepted:
                    self.controller.record_icpi_exchange(
                        message,
                        "ICPI interpretation cancelled; no model turn was started.",
                        route=route,
                        action="INTERPRETATION_CANCELLED",
                    )
                    return
            self.context_delta = compare_context_envelopes(envelope, envelope)
            self.shell.set_context_envelope(envelope)
            self.shell.set_context_delta(self.context_delta)
            try:
                self.controller.submit_chat_message(
                    message,
                    route=route,
                    model_input=envelope.model_input,
                    context_envelope=envelope,
                    pinned_context=self.pinned_context,
                    pinned_context_envelope=self.pinned_context_envelope,
                    confirmation=confirmation,
                    confirmation_receipt=confirmation_receipt,
                )
            except (PolicyError, RuntimeError, ValueError) as exc:
                messagebox.showerror("ICPI dispatch blocked", str(exc), parent=self)
            return
        if directive.action == "NEW_CONTEXT":
            self.controller.record_icpi_exchange(
                message,
                "Starting a new bounded model context.",
                route=route,
                action=directive.action,
            )
            self._new_chat()
            return
        if directive.action == "STOP":
            stopped = self.controller.stop_chat()
            self.controller.record_icpi_exchange(
                message,
                "Stop requested." if stopped else "No agent chat turn is running.",
                route=route,
                action=directive.action,
            )
            return
        if directive.action == "PROVIDER_PREFLIGHT":
            self.controller.submit_provider_preflight(route=route)
            return
        if directive.action == "EXIT":
            self.controller.record_icpi_exchange(
                message,
                "The GUI does not close from an unaudited prompt command. Use the window close control.",
                route=route,
                action=directive.action,
            )
            return
        self.controller.record_icpi_exchange(
            message,
            directive.message,
            route=route,
            action=directive.action,
        )
        self._apply_icpi_surface(directive)

    def _known_evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    evidence_id
                    for task in self.controller.state.tasks.values()
                    for evidence_id in task.evidence_ids
                }
            )
        )

    def _build_pinned_context_envelope(
        self,
        pinned_context: PinnedContextSet,
        *,
        source_snapshot_hash: str | None = None,
    ):
        return build_pinned_context_envelope(
            pinned_context,
            self.icpi_workspace,
            source_snapshot_hash=(
                source_snapshot_hash or self.controller.gateway.snapshot()
            ),
            known_evidence_ids=self._known_evidence_ids(),
        )

    def _preview_chat(self, message: str) -> str:
        return format_pinned_route_preview(
            message,
            self.icpi_workspace,
            self.pinned_context,
            known_evidence_ids=self._known_evidence_ids(),
        )

    def _apply_icpi_surface(self, directive) -> None:
        surface = projection_surface(directive.route.target)
        command = directive.route.command
        if directive.action == "ATTACH_CONTEXT" and command is not None:
            try:
                source_snapshot = self.controller.gateway.snapshot()
                require_fresh_pinned_context(
                    self.pinned_context,
                    self.pinned_context_envelope,
                    current_source_snapshot_hash=source_snapshot,
                )
                updated_context = self.pinned_context.add(
                    self.icpi_workspace,
                    command.arguments,
                )
                envelope = self._build_pinned_context_envelope(
                    updated_context,
                    source_snapshot_hash=source_snapshot,
                )
            except (OSError, PolicyError, ValueError) as exc:
                messagebox.showerror(
                    "ICPI attachment blocked",
                    str(exc),
                    parent=self,
                )
                return
            self.pinned_context = updated_context
            self.pinned_context_envelope = envelope
            self.context_delta = (
                compare_context_envelopes(envelope, envelope)
                if envelope is not None
                else None
            )
            self.shell.set_pinned_context(self.pinned_context)
            self.shell.set_context_envelope(envelope)
            self.shell.set_context_delta(self.context_delta)
            self.controller.record_pinned_context_transition(
                route=directive.route,
                action="ATTACH_CONTEXT",
                pinned_context=self.pinned_context,
                context_envelope=self.pinned_context_envelope,
                context_delta=self.context_delta,
            )
            self.shell.show_context()
            return
        if directive.action == "DETACH_CONTEXT" and command is not None:
            try:
                source_snapshot = self.controller.gateway.snapshot()
                options = dict(command.options)
                if options.get("all", "false").casefold() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }:
                    updated_context = self.pinned_context.clear()
                else:
                    updated_context = self.pinned_context.remove(
                        self.icpi_workspace,
                        command.arguments,
                    )
                if updated_context.paths:
                    require_fresh_pinned_context(
                        self.pinned_context,
                        self.pinned_context_envelope,
                        current_source_snapshot_hash=source_snapshot,
                    )
                envelope = self._build_pinned_context_envelope(
                    updated_context,
                    source_snapshot_hash=source_snapshot,
                )
            except (OSError, PolicyError, ValueError) as exc:
                messagebox.showerror(
                    "ICPI detach blocked",
                    str(exc),
                    parent=self,
                )
                return
            self.pinned_context = updated_context
            self.pinned_context_envelope = envelope
            self.context_delta = (
                compare_context_envelopes(envelope, envelope)
                if envelope is not None
                else None
            )
            self.shell.set_pinned_context(self.pinned_context)
            self.shell.set_context_envelope(envelope)
            self.shell.set_context_delta(self.context_delta)
            self.controller.record_pinned_context_transition(
                route=directive.route,
                action="DETACH_CONTEXT",
                pinned_context=self.pinned_context,
                context_envelope=self.pinned_context_envelope,
                context_delta=self.context_delta,
            )
            self.shell.show_context()
            return
        if command is not None and command.name == "context":
            if not self.pinned_context.paths:
                self.pinned_context_envelope = None
                self.context_delta = None
                self.shell.set_context_envelope(None)
                self.shell.set_context_delta(None)
                self.shell.show_context()
                return
            try:
                observed_envelope = self._build_pinned_context_envelope(
                    self.pinned_context,
                )
                assert observed_envelope is not None
                baseline_envelope = self.pinned_context_envelope or observed_envelope
                refresh_applied = directive.action == "REFRESH_CONTEXT"
                self.context_delta = compare_context_envelopes(
                    baseline_envelope,
                    observed_envelope,
                    refresh_applied=refresh_applied,
                )
                if refresh_applied:
                    self.pinned_context_envelope = observed_envelope
                displayed_envelope = self.pinned_context_envelope or observed_envelope
            except (OSError, PolicyError, ValueError) as exc:
                messagebox.showerror("ICPI context check blocked", str(exc), parent=self)
                return
            self.shell.set_context_envelope(displayed_envelope)
            self.shell.set_context_delta(self.context_delta)
            self.controller.record_pinned_context_transition(
                route=directive.route,
                action=("REFRESH_CONTEXT" if refresh_applied else "INSPECT_CONTEXT"),
                pinned_context=self.pinned_context,
                context_envelope=displayed_envelope,
                context_delta=self.context_delta,
            )
            self.shell.show_context()
            return
        if directive.action == "GOVERNANCE_REQUIRED":
            self.shell.show_eon()
            return
        if surface == "repository":
            self.shell.show_repository()
            if command is not None and command.arguments:
                relative = self.icpi_workspace.canonical(command.arguments[0])
                if self.icpi_workspace.resolve(relative).is_file():
                    self._select_file(relative)
        elif surface == "evidence":
            identifiers = command.arguments if command is not None else ()
            if not identifiers:
                task = self.controller.state.tasks.get(self.controller.state.selected_task_id)
                identifiers = task.evidence_ids if task is not None else ()
            self.shell.show_evidence(identifiers)
        elif surface == "reasoning":
            self.shell.show_reasoning()
        elif surface == "eon":
            self.shell.show_eon()
        elif surface == "artifacts":
            self.shell.show_artifacts()
        elif surface == "context":
            self.shell.show_context()

    def _stop_chat(self) -> None:
        if not self.controller.stop_chat():
            self.shell.conversation.append("GUI", "No agent chat turn is running.")

    def _new_chat(self) -> None:
        had_pinned_context = bool(self.pinned_context.paths)
        self.controller.new_chat_context()
        self.pinned_context = self.pinned_context.clear()
        self.pinned_context_envelope = None
        self.context_delta = None
        self.shell.set_pinned_context(self.pinned_context)
        self.shell.set_context_envelope(None)
        self.shell.set_context_delta(None)
        if had_pinned_context:
            self.controller.record_pinned_context_transition(
                route=None,
                action="NEW_CONTEXT",
                pinned_context=self.pinned_context,
            )

    def _submit_semantic_command(self, request: CommandRequest) -> None:
        self.shell.terminal.append(
            "USER",
            {"command_id": request.command_id, "inputs": request.inputs, "dry_run": True},
        )
        self.controller.submit_command(request)

    def _create_regression(self, failure: FailureRecord) -> None:
        self.shell.show_cfel()
        self._prefill(
            f"verify regression subject={failure.subject_id} "
            f"expected={failure.expected!r} observed={failure.observed!r} "
        )

    def _submit(self) -> None:
        objective = self.prompt.get().strip()
        if not objective:
            return
        modifiers = safe_default_modifiers()
        modifiers["simulate"] = self.simulate.get()
        self.shell.conversation.append("User", objective)
        self.controller.submit_objective(
            ObjectiveRequest(objective=objective, modifiers=modifiers)
        )
        self.prompt.set("")

    def _select_task(self, task_id: str) -> None:
        if task_id == self.controller.state.selected_task_id:
            return
        self.controller.select_task(task_id)

    def _select_object(self, object_id: str) -> None:
        if object_id:
            self.controller.select_object(object_id, self.controller.state.selected_task_id)

    def _select_file(self, relative_path: str) -> None:
        self.open_file = relative_path
        self.shell.show_file(relative_path)

    def _load_task_trace(self, task_id: str) -> None:
        task = self.controller.state.tasks.get(task_id)
        self.shell.set_task_context(task)
        if task is None or not task.selection_ids:
            self.shell.set_selection_trace(None)
            return
        self.controller.load_selection_trace(
            task.selection_ids[-1],
            task_id=task_id,
            invocation_id=task.invocation_ids[-1] if task.invocation_ids else "",
            compiled_workflow_id=(
                task.compiled_workflow_ids[-1] if task.compiled_workflow_ids else ""
            ),
        )

    def _approve_plan(self, plan_id: str) -> None:
        task_id = self.controller.state.selected_task_id
        try:
            plan = self.controller.repository.get(plan_id)
            compiled = self.controller.repository.get(plan.compiled_workflow_id)
        except Exception as exc:
            self.shell.conversation.append("Error", f"Cannot inspect approval: {exc}")
            return
        if not isinstance(plan, ExecutionPlan) or not isinstance(compiled, CompiledWorkflow):
            self.shell.conversation.append("Error", "Approval target is not a valid execution plan.")
            return
        current_snapshot = self.controller.repository.source_snapshot()
        if plan.source_snapshot_hash != current_snapshot:
            self.shell.conversation.append(
                "OURD",
                "Approval blocked: the execution plan source snapshot is stale. Recompile before approval.",
            )
            self._load_task_trace(task_id)
            return
        summary = {
            "plan_id": plan.object_id,
            "plan_hash": plan.object_id.partition(":sha256:")[2],
            "source_snapshot_hash": plan.source_snapshot_hash,
            "current_source_snapshot_hash": current_snapshot,
            "source_snapshot_current": True,
            "capability_level": compiled.capability_level,
            "risk": compiled.risk,
            "approval_policy": plan.approval_policy,
            "scope": compiled.command_context.get("scope", []),
            "evidence_ids": plan.evidence_ids,
            "rollback_graph": plan.rollback_graph,
            "nodes": compiled.nodes,
            "unresolved": compiled.unresolved,
            "constraints": {
                "expires_at": plan.expires_at,
                "single_use_default": True,
            },
        }

        def approve(approver: str, authority: str) -> None:
            self.controller.authorize(
                task_id,
                ApprovalRequest(
                    plan_id=plan_id,
                    approver=approver,
                    authority=authority,
                    constraints={
                        "scope": compiled.command_context.get("scope", []),
                        "source_snapshot_hash": plan.source_snapshot_hash,
                    },
                ),
            )

        ApprovalDialog(
            self,
            summary,
            on_approve=approve,
            on_reject=lambda: self.controller.reject_approval(task_id, plan_id),
            on_inspect_evidence=lambda: self.shell.show_evidence(plan.evidence_ids),
            on_inspect_rollback=self.shell.show_eon,
        )

    def _execute_plan(self, plan_id: str) -> None:
        task_id = self.controller.state.selected_task_id
        task = self.controller.state.tasks.get(task_id)
        if task is None:
            return
        try:
            plan = self.controller.repository.get(plan_id)
        except Exception as exc:
            self.shell.conversation.append("Error", f"Cannot inspect plan: {exc}")
            return
        if not isinstance(plan, ExecutionPlan):
            self.shell.conversation.append("Error", "Execution target is not a valid plan.")
            return
        current_snapshot = self.controller.repository.source_snapshot()
        if plan.source_snapshot_hash != current_snapshot:
            self.shell.conversation.append(
                "OURD",
                "Execution blocked: source state changed after plan creation. Recompile first.",
            )
            return
        approval = matching_approval(
            self.controller.repository,
            plan,
            task.approval_ids,
        )
        approval_id = approval.object_id if approval is not None else ""
        if plan.approval_policy in {"human", "quorum"} and not approval_id:
            self.shell.conversation.append(
                "OURD",
                "Execution is blocked until exact scoped approval is recorded.",
            )
            return
        self.controller.execute(
            task_id,
            ExecutionRequest(plan_id=plan_id, approval_id=approval_id),
        )

    def _rollback_plan(self, plan_id: str) -> None:
        self.shell.conversation.append(
            "OURD",
            "Rollback is available only through a recorded failed execution or a governed rollback command; no direct GUI rollback was issued.",
        )

    def _edit_plan_scope(self, plan_id: str) -> None:
        try:
            plan = self.controller.repository.get(plan_id)
            compiled = self.controller.repository.get(plan.compiled_workflow_id)
        except Exception as exc:
            self.shell.conversation.append("Error", f"Cannot inspect plan scope: {exc}")
            return
        if not isinstance(plan, ExecutionPlan) or not isinstance(compiled, CompiledWorkflow):
            self.shell.conversation.append("Error", "Scope target is not a valid plan.")
            return
        scope = compiled.command_context.get("scope", [])
        self._prefill(f"Refine scope {scope!r} for plan {plan.object_id}: ")
        self.shell.conversation.append(
            "OURD",
            "Scope editing creates a new objective and plan; the current immutable plan was not changed.",
        )

    def _replay_plan(self, plan_id: str) -> None:
        task_id = self.controller.state.selected_task_id
        if not task_id:
            return
        modifiers = safe_default_modifiers()
        modifiers["replay"] = plan_id
        self.shell.conversation.append(
            "OURD",
            "Governed plan replay requested in dry-run mode; historical execution is not reused as authority.",
        )
        self.controller.replay(
            task_id,
            ReplayRequest(plan_id=plan_id, modifiers=modifiers),
        )

    def _export_assurance(self, assurance_id: str, format_name: str) -> None:
        try:
            path = self.controller.export_assurance(assurance_id, format_name)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            self.shell.conversation.append(
                "Error", f"Assurance export failed: {type(exc).__name__}: {exc}"
            )
            return
        self.shell.conversation.append(
            "GUI",
            f"Exported non-authoritative assurance view to {path.relative_to(self.repository_root)}",
        )

    def _export_evidence(self, evidence_ids: tuple[str, ...], format_name: str) -> None:
        try:
            path = self.controller.export_evidence(evidence_ids, format_name)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            self.shell.conversation.append(
                "Error", f"Evidence export failed: {type(exc).__name__}: {exc}"
            )
            return
        self.shell.conversation.append(
            "GUI",
            f"Exported non-authoritative evidence view to {path.relative_to(self.repository_root)}",
        )

    def _handle_event(self, event: AgentEvent) -> None:
        render_started = time.perf_counter()
        self.shell.append_event(event)
        if event.event_type == AgentEventType.TASK_STARTED:
            if event.payload.get("message") != "agent chat turn":
                self.shell.conversation.append(
                    "OURD",
                    f"Started: {event.payload.get('title', '')}",
                )
        elif event.event_type == AgentEventType.TASK_FINISHED:
            is_chat = str(event.payload.get("message", "")).startswith("agent chat")
            if not is_chat:
                self.shell.conversation.append(
                    "OURD",
                    f"{event.payload.get('status', 'COMPLETED')}: {event.payload.get('message', '')}",
                )
            self._load_task_trace(event.task_id)
            self.shell.refresh_records()
            if not is_chat:
                self.shell.terminal.append(
                    "RESULT",
                    {
                        "task_id": event.task_id,
                        "status": event.payload.get("status", "COMPLETED"),
                        "message": event.payload.get("message", ""),
                        "result": event.payload.get("result", {}),
                    },
                )
        elif event.event_type in {
            AgentEventType.AGENT_STEP,
            AgentEventType.TOOL_REQUESTED,
            AgentEventType.TOOL_COMPLETED,
            AgentEventType.CHAT_ACTIVITY,
        } and event.source == "ourd-agent":
            self.shell.conversation.append_activity(event)
        elif event.event_type == AgentEventType.TASK_SELECTED:
            self._load_task_trace(event.task_id)
        elif event.event_type == AgentEventType.SELECTION_UPDATED:
            trace = event.payload.get("trace")
            if isinstance(trace, SelectionTrace):
                self.shell.set_selection_trace(trace)
        elif event.event_type == AgentEventType.OBJECT_SELECTED:
            object_id = str(event.payload.get("object_id", ""))
            if object_id:
                self.shell.show_object(object_id)
        elif event.event_type == AgentEventType.APPROVAL_RECORDED:
            self.shell.conversation.append(
                "OURD", "Scoped approval was recorded by the governed core."
            )
            self._load_task_trace(event.task_id)
        elif event.event_type == AgentEventType.APPROVAL_REJECTED:
            self.shell.conversation.append(
                "OURD", "Approval was rejected; no execution was started."
            )
        elif event.event_type == AgentEventType.UI_ERROR:
            self.shell.conversation.append("Error", str(event.payload.get("message", "")))
        self.shell.render_state(self.controller.state)
        self.snapshot_label.configure(text=f"Snapshot: {self.controller.state.source_snapshot[:12]}")
        self._refresh_capability_badge()
        self.worker_badge.set_status(
            "running" if self.controller.state.worker_status != "idle" else "neutral",
            self.controller.state.worker_status.upper(),
        )
        if self.controller.state.event_head:
            self.event_head_label.configure(
                text=f"Event head: {self.controller.state.event_head[:12]}"
            )
        self.controller.performance.record_ms(
            "gui.event_render",
            (time.perf_counter() - render_started) * 1_000,
            {"event_type": event.event_type.value},
        )

    def _refresh_capability_badge(self) -> None:
        plan = None
        task = self.controller.state.tasks.get(self.controller.state.selected_task_id)
        if task is not None and task.execution_plan_ids:
            try:
                candidate = self.controller.repository.get(task.execution_plan_ids[-1])
                if isinstance(candidate, ExecutionPlan):
                    plan = candidate
            except (OSError, ValueError, KeyError):
                plan = None
        ladder = build_capability_ladder(self.controller.repository, plan=plan)
        if plan is not None:
            try:
                compiled = self.controller.repository.get(plan.compiled_workflow_id)
            except (OSError, ValueError, KeyError):
                compiled = None
            requested = (
                compiled.capability_level
                if isinstance(compiled, CompiledWorkflow)
                else "C0"
            )
            level = next((item for item in ladder if item.level == requested), ladder[0])
        else:
            eligible = [item for item in ladder if item.status in {"available", "gated"}]
            level = eligible[-1] if eligible else ladder[0]
        status = {
            "available": "qualified",
            "gated": "gated",
            "blocked": "blocked",
        }.get(level.status, "neutral")
        self.capability_badge.set_status(status, f"{level.level} {level.status.upper()}")

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closing or not self.winfo_exists():
            return
        _, failures = self.controller.drain_events()
        if failures:
            self.shell.conversation.append(
                "GUI",
                "; ".join(f"{type(item).__name__}: {item}" for item in failures),
            )
        for event in self.formal_writing_controller.poll_events():
            self.shell.formal_writing.apply_event(event)
            if event.operation == "write" and event.event_type.value == "JOB_COMPLETED":
                self.shell.show_governance()
        if not self._closing and self.winfo_exists():
            self._poll_after_id = self.after(self.POLL_MS, self._poll)

    def _submit_formal_writing(
        self,
        operation: str,
        form: FormalWritingFormState,
        options: FormalWritingExecutionOptions,
    ) -> None:
        job_id = self.formal_writing_controller.submit(operation, form, options)
        self.shell.formal_writing.set_busy(True, message=f"Queued {job_id}")

    def _cancel_formal_writing(self) -> None:
        if self.formal_writing_controller.request_cancel():
            self.shell.formal_writing.status_var.set(
                "Cancellation requested; waiting for a safe phase boundary"
            )

    def _set_formal_writing_authority(self, authority_path: Path) -> None:
        self.authority_path = authority_path.resolve()
        self.formal_writing_controller.authority_path = self.authority_path
        self.shell.formal_writing.set_authority_path(self.authority_path)

    def _prepare_formal_writing(self, form: FormalWritingFormState) -> None:
        preview = self.formal_writing_controller.preview_governed_write(form)
        confirmed = confirm_governed_write(self, preview)
        if confirmed is None:
            self.shell.formal_writing.status_var.set("Governed write preparation cancelled")
            return
        job_id = self.formal_writing_controller.submit_governed_write(
            preview,
            confirmed_request_signature=confirmed,
        )
        self.shell.formal_writing.set_busy(True, message=f"Queued {job_id}")

    def _lifecycle_heartbeat(self) -> None:
        self._heartbeat_after_id = None
        if self._closing or not self.winfo_exists():
            return
        self.lifecycle_recorder.heartbeat(
            chat_status=self.controller.state.chat_status,
            pending_operations=len(self.controller._pending),
        )
        if not self._closing and self.winfo_exists():
            self._heartbeat_after_id = self.after(1_000, self._lifecycle_heartbeat)

    def _cancel_after_callback(self, attribute_name: str) -> None:
        callback_id = getattr(self, attribute_name, None)
        if not callback_id:
            return
        setattr(self, attribute_name, None)
        try:
            self.after_cancel(callback_id)
        except tk.TclError:
            pass

    def _cancel_scheduled_callbacks(self) -> None:
        self._cancel_after_callback("_restore_after_id")
        self._cancel_after_callback("_poll_after_id")
        self._cancel_after_callback("_heartbeat_after_id")

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._cancel_scheduled_callbacks()
        self.lifecycle_recorder.shutdown_requested(
            chat_status=self.controller.state.chat_status
        )
        try:
            geometry = self.geometry()
            layout = self.shell.preference_state()
            self.preferences_store.save(
                type(self.preferences)(
                    **{
                        **self.preferences.__dict__,
                        "window_geometry": geometry,
                        **layout,
                        "open_file": self.open_file,
                        "recent_repositories": tuple(
                            dict.fromkeys(
                                [str(self.repository_root), *self.preferences.recent_repositories]
                            )
                        )[:10],
                    }
                )
            )
            self.formal_writing_controller.shutdown(wait=False, timeout_seconds=1.0)
            self.controller.close()
            self.controller.drain_events()
            self.lifecycle_recorder.checkpoint(
                state_digest=self.controller.state.digest,
                event_head=self.controller.state.event_head,
            )
            self.lifecycle_recorder.shutdown_complete()
        except Exception as exc:
            self.lifecycle_recorder.failure("SHUTDOWN_FAILED", exc)
            raise
        finally:
            if self.winfo_exists():
                self.destroy()


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(raw_arguments)
    repository_root = Path(args.repo).resolve()
    lifecycle_recorder = AppLifecycleRecorder.from_environment(repository_root)
    lifecycle_recorder.startup_begin()
    try:
        bootstrap_result = None
        auto_qwen = automatic_qwen_bootstrap_requested(
            arguments=raw_arguments,
            executable_name=sys.argv[0],
            explicit_setting=args.auto_qwen,
        )
        if auto_qwen:
            explicit_model = _option_supplied(raw_arguments, "--model") or bool(
                os.getenv("OURD_MODEL", "").strip()
            )
            requested_model = args.model if explicit_model else args.qwen_model
            if not _option_supplied(raw_arguments, "--reasoning-effort") and not os.getenv(
                "OURD_REASONING_EFFORT", ""
            ):
                args.reasoning_effort = "none"
            if not _option_supplied(raw_arguments, "--context-budget") and not os.getenv(
                "OURD_CONTEXT_BUDGET", ""
            ):
                args.context_budget = 6000
            if not _option_supplied(raw_arguments, "--max-output-tokens") and not os.getenv(
                "OURD_MAX_OUTPUT_TOKENS", ""
            ):
                args.max_output_tokens = 1400
            if not _option_supplied(
                raw_arguments, "--runtime-context-tokens"
            ) and not os.getenv("OURD_RUNTIME_CONTEXT", ""):
                args.runtime_context_tokens = args.llama_context
            args.provider = "llama_cpp_process"
            args.model = "qwen3.8-27b-direct"
            bootstrap_result = ensure_qwen38_fast(
                requested_model=requested_model,
                runner_path=args.runner_path,
                model_path=args.model_path,
                expected_model_sha256=args.expected_model_sha256,
            )
            print(
                "ICPI direct Qwen profile ready: "
                f"alias={bootstrap_result.product_alias} model={bootstrap_result.resolved_model} "
                f"digest={bootstrap_result.model_digest or 'unverified'} "
                f"runner_configured={str(bool(args.runner_path)).lower()} "
                f"model_configured={str(bool(args.model_path)).lower()}",
                file=sys.stderr,
            )
        app = OURDWorkbench(
            repository_root,
            authority_path=args.authority,
            provider_kind=args.provider,
            model=args.model,
            base_url=args.base_url,
            context_budget=args.context_budget,
            runtime_context_tokens=args.runtime_context_tokens,
            context_safety_margin_tokens=args.context_safety_margin,
            api_key=args.api_key,
            reasoning_effort=args.reasoning_effort,
            json_object_output=args.json_object_output,
            response_temperature_bp=args.response_temperature_bp,
            response_top_p_bp=args.response_top_p_bp,
            response_seed=args.response_seed,
            max_output_tokens=args.max_output_tokens,
            timeout_seconds=args.timeout_seconds,
            transport_retries=args.transport_retries,
            max_reasoning_samples=args.max_reasoning_samples,
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
            max_steps=args.max_steps,
            qwen_bootstrap_result=bootstrap_result,
            lifecycle_recorder=lifecycle_recorder,
        )
    except Exception as exc:
        lifecycle_recorder.failure("STARTUP_FAILED", exc)
        print(f"OIEC-STM-Agent GUI startup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("OIEC-STM-Agent GUI", f"{type(exc).__name__}: {exc}")
            root.destroy()
        except Exception:
            pass
        return 2
    if args.smoke_test:
        app.update_idletasks()
        app.update()
        app._close()
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
