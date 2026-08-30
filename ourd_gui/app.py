from __future__ import annotations

import argparse
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, Sequence

from ourd.egcf.models import CommandDefinition, CompiledWorkflow, ExecutionPlan, FailureRecord
from ourd.providers import ProviderConfig

from .command_palette import CommandPaletteRegistry, PaletteCommand
from .commands import ApprovalRequest, CommandRequest, ExecutionRequest, ObjectiveRequest, ReplayRequest, safe_default_modifiers
from .controller import GuiController
from .events import AgentEvent, AgentEventType
from .governance_models import build_capability_ladder, matching_approval
from .model_backend import model_backend_info
from .persistence import GuiPreferencesStore
from .selection_trace import SelectionTrace
from .views.approvals import ApprovalDialog
from .views.command_palette import CommandPaletteDialog
from .views.shell import WorkbenchShell
from .widgets.status_badge import StatusBadge


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oiec-stm-gui",
        description="Evidence-governed OIEC-STM-Agent workbench",
    )
    parser.add_argument("--repo", default=".", help="Repository/workspace root")
    parser.add_argument("--authority", type=Path, help="External authority manifest")
    parser.add_argument(
        "--model",
        default=os.getenv("OURD_MODEL", "gpt-5.6"),
        help="Agent Chat model and backend metadata shown in the GUI",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OURD_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        help="OpenAI-compatible model backend URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OURD_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        help="Agent Chat provider API key; local Ollama accepts an ignored placeholder",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("OURD_REASONING_EFFORT", ""),
        choices=["", "none", "low", "medium", "high", "xhigh"],
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
    parser.add_argument(
        "--max-steps",
        type=int,
        default=80,
        help="Maximum governed model/tool steps per chat turn",
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
        model: str = "gpt-5.6",
        base_url: str = "",
        context_budget: int = 6000,
        api_key: str = "",
        reasoning_effort: str = "",
        max_output_tokens: int = 2048,
        timeout_seconds: float = 600.0,
        transport_retries: int = 0,
        max_reasoning_samples: int = 16,
        max_steps: int = 80,
    ) -> None:
        initialization_started = time.perf_counter()
        super().__init__()
        self.repository_root = repository_root.resolve()
        self.preferences_store = GuiPreferencesStore(self.repository_root)
        self.preferences = self.preferences_store.load()
        self._apply_font_scale(self.preferences.font_scale)
        self.open_file = self.preferences.open_file
        self.model_backend = model_backend_info(
            model=model,
            base_url=base_url,
            context_tokens=context_budget,
        )
        self.title("OIEC-STM-Agent Workbench")
        self.geometry(self.preferences.window_geometry)
        self.minsize(900, 600)
        self.controller = GuiController(
            self.repository_root,
            authority_path=authority_path,
            provider_config=ProviderConfig(
                model=model,
                base_url=base_url,
                api_key=api_key,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max(1, max_output_tokens),
                context_budget_tokens=max(256, context_budget),
                timeout_seconds=max(1.0, timeout_seconds),
                max_transport_retries=max(0, min(transport_retries, 5)),
                max_reasoning_samples=max(1, min(max_reasoning_samples, 64)),
            ),
            max_agent_steps=max(1, max_steps),
        )
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
        )
        self.shell.pack(fill="both", expand=True)
        self.shell.render_state(self.controller.state)
        self._build_command_bar()
        self.palette = self._build_palette()
        self.bind_all("<Control-k>", self._open_palette)
        self.bind_all("<Control-l>", lambda event: self._show_chat())
        self.bind_all("<Alt-Left>", lambda event: self.controller.navigate_back())
        self.bind_all("<Alt-Right>", lambda event: self.controller.navigate_forward())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after_idle(self._restore_preferences)
        self.after(self.POLL_MS, self._poll)
        self.controller.performance.record_ms(
            "gui.initialize",
            (time.perf_counter() - initialization_started) * 1_000,
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
        ttk.Label(bar, text="Semantic Objective").pack(side="left", padx=(0, 4))
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
        self.controller.submit_chat_message(message)

    def _stop_chat(self) -> None:
        if not self.controller.stop_chat():
            self.shell.conversation.append("GUI", "No agent chat turn is running.")

    def _new_chat(self) -> None:
        self.controller.new_chat_context()

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
        _, failures = self.controller.drain_events()
        if failures:
            self.shell.conversation.append(
                "GUI",
                "; ".join(f"{type(item).__name__}: {item}" for item in failures),
            )
        if self.winfo_exists():
            self.after(self.POLL_MS, self._poll)

    def _close(self) -> None:
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
            self.controller.close()
            self.controller.drain_events()
        finally:
            self.destroy()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository_root = Path(args.repo).resolve()
    try:
        app = OURDWorkbench(
            repository_root,
            authority_path=args.authority,
            model=args.model,
            base_url=args.base_url,
            context_budget=args.context_budget,
            api_key=args.api_key,
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
            timeout_seconds=args.timeout_seconds,
            transport_retries=args.transport_retries,
            max_reasoning_samples=args.max_reasoning_samples,
            max_steps=args.max_steps,
        )
    except Exception as exc:
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
