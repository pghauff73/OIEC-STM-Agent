from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Iterable

from ourd.egcf.models import ExecutionPlan, FailureRecord

from ..read_models import ReadOnlyEGCFRepository
from ..commands import CommandRequest
from ..events import AgentEvent
from ..model_backend import ModelBackendInfo
from ..selection_trace import SelectionTrace
from ..state import GuiState, GuiTask
from ..widgets.json_view import JsonView
from .algorithms import AlgorithmsView
from .assurance import AssuranceRecordView
from .artifacts import ArtifactWorkbenchView
from .cfel import CFELView
from .conversation import ConversationView
from .eon import EONInspectorView
from .evidence import EvidenceView
from .file_preview import FilePreviewView
from .governance import GovernanceView
from .iurm import IURMDimensionView
from .model_backend import ModelBackendView
from .performance import PerformanceView
from .ourd import OURDGraphView
from .repository import RepositoryView
from .replay import ReplayView
from .selection import SelectionTraceView
from .session_compare import SessionComparisonView
from .tasks import TaskListView
from .terminal import SemanticTerminalView
from .trace import TraceTimelineView
from .visual_workbench import VisualWorkbenchView
from .workflow import WorkflowView


class WorkbenchShell(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository_root: Path,
        repository: ReadOnlyEGCFRepository,
        *,
        on_task_selected: Callable[[str], None],
        on_object_selected: Callable[[str], None],
        on_file_selected: Callable[[str], None],
        on_approve_plan: Callable[[str], None] | None = None,
        on_execute_plan: Callable[[str], None] | None = None,
        on_rollback_plan: Callable[[str], None] | None = None,
        on_simulate_plan: Callable[[str], None] | None = None,
        on_edit_plan_scope: Callable[[str], None] | None = None,
        on_create_regression: Callable[[FailureRecord], None] | None = None,
        on_semantic_command: Callable[[CommandRequest], None] | None = None,
        model_backend: ModelBackendInfo | None = None,
        on_model_preflight: Callable[[], None] | None = None,
        on_prepare_command: Callable[[str], None] | None = None,
        event_supplier: Callable[[], Iterable[AgentEvent]] | None = None,
        on_replay_cursor: Callable[[int], None] | None = None,
        on_plan_replay: Callable[[str], None] | None = None,
        on_assurance_export: Callable[[str, str], None] | None = None,
        on_evidence_export: Callable[[tuple[str, ...], str], None] | None = None,
        performance_supplier: Callable[[], dict] | None = None,
        on_chat_send: Callable[[str], None] | None = None,
        on_chat_stop: Callable[[], None] | None = None,
        on_new_chat: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_object_selected = on_object_selected
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self.paned = paned

        left_tabs = ttk.Notebook(paned)
        self.tasks = TaskListView(left_tabs, on_task_selected)
        self.repository_view = RepositoryView(left_tabs, repository_root, on_file_selected)
        left_tabs.add(self.tasks, text="Tasks")
        left_tabs.add(self.repository_view, text="Repository")
        self.left_tabs = left_tabs

        center_tabs = ttk.Notebook(paned)
        self.selection = SelectionTraceView(
            center_tabs,
            on_object_selected=on_object_selected,
            on_show_evidence=self.show_evidence,
        )
        self.conversation = ConversationView(
            center_tabs,
            on_send=on_chat_send,
            on_stop=on_chat_stop,
            on_new_chat=on_new_chat,
        )
        self.workflow = WorkflowView(center_tabs, repository, on_object_selected)
        self.trace = TraceTimelineView(center_tabs, on_object_selected)
        self.ourd = OURDGraphView(
            center_tabs,
            on_object_selected=on_object_selected,
            on_prepare_command=on_prepare_command,
        )
        self.iurm = IURMDimensionView(center_tabs, on_prepare_command)
        self.terminal = SemanticTerminalView(
            center_tabs,
            repository,
            on_semantic_command or (lambda request: None),
        )
        self.visual = VisualWorkbenchView(
            center_tabs,
            repository_root,
            on_insert_chat_reference=self.conversation.insert_text,
            on_chat_send=on_chat_send,
        )
        self.replay = ReplayView(
            center_tabs,
            event_supplier or (lambda: ()),
            on_replay_cursor or (lambda cursor: None),
            on_plan_replay,
        )
        self.session_compare = SessionComparisonView(center_tabs, repository)
        center_tabs.add(self.conversation, text="Agent Chat")
        center_tabs.add(self.visual, text="Visual Workbench")
        center_tabs.add(self.selection, text="Selection Trace")
        center_tabs.add(self.workflow, text="Workflow")
        center_tabs.add(self.ourd, text="OURD")
        center_tabs.add(self.iurm, text="IURM")
        center_tabs.add(self.trace, text="Trace")
        center_tabs.add(self.terminal, text="Semantic Terminal")
        center_tabs.add(self.replay, text="Replay")
        center_tabs.add(self.session_compare, text="Compare Runs")
        self.center_tabs = center_tabs

        right_tabs = ttk.Notebook(paned)
        self.evidence = EvidenceView(
            right_tabs,
            repository,
            on_object_selected,
            on_evidence_export,
        )
        self.algorithms = AlgorithmsView(
            right_tabs,
            repository,
            on_object_selected,
            self.show_evidence,
        )
        self.governance = GovernanceView(right_tabs, repository, on_object_selected)
        self.eon = EONInspectorView(
            right_tabs,
            repository,
            on_approve=on_approve_plan,
            on_execute=on_execute_plan,
            on_show_evidence=self.show_evidence,
            on_rollback=on_rollback_plan,
            on_simulate=on_simulate_plan,
            on_edit_scope=on_edit_plan_scope,
        )
        self.cfel = CFELView(
            right_tabs,
            repository,
            on_object_selected,
            on_create_regression=on_create_regression,
        )
        self.artifacts = ArtifactWorkbenchView(right_tabs, repository, on_object_selected)
        self.assurance = AssuranceRecordView(
            right_tabs,
            repository,
            on_object_selected=on_object_selected,
            on_export=on_assurance_export,
        )
        self.model_backend = ModelBackendView(
            right_tabs,
            model_backend
            or ModelBackendInfo(
                provider="unknown",
                backend="not configured",
                model="unknown",
                base_url="",
                quantization="unknown",
                context_tokens=1,
                latency="not measured",
                memory="not measured",
                device_residency="not measured",
                health="not checked",
                provenance="none",
            ),
            on_model_preflight,
        )
        self.performance = PerformanceView(
            right_tabs,
            performance_supplier or (lambda: {}),
        )
        self.object_details = JsonView(right_tabs)
        self.file_preview = FilePreviewView(right_tabs, repository_root)
        right_tabs.add(self.evidence, text="Evidence")
        right_tabs.add(self.algorithms, text="Algorithms")
        right_tabs.add(self.governance, text="Governance")
        right_tabs.add(self.eon, text="EON")
        right_tabs.add(self.cfel, text="CFEL")
        right_tabs.add(self.artifacts, text="Artifacts")
        right_tabs.add(self.assurance, text="Assurance")
        right_tabs.add(self.model_backend, text="Model")
        right_tabs.add(self.performance, text="Performance")
        right_tabs.add(self.file_preview, text="File")
        right_tabs.add(self.object_details, text="Object")
        self.right_tabs = right_tabs

        paned.add(left_tabs, weight=2)
        paned.add(center_tabs, weight=5)
        paned.add(right_tabs, weight=3)

    def render_state(self, state: GuiState) -> None:
        self.tasks.set_tasks(state.tasks, state.selected_task_id)
        self.session_compare.set_state(state)
        self.conversation.set_state(
            state.chat_messages,
            status=state.chat_status,
            context_start=state.chat_context_start,
        )

    def set_task_context(self, task: GuiTask | None) -> None:
        if task is None:
            self.workflow.set_workflow("")
            self.eon.set_plan("")
            self.evidence.set_evidence_ids(())
            self.governance.set_plan(None)
            self.ourd.set_task(None)
            self.iurm.set_task(None)
            self.replay.set_task(None)
            return
        compiled_id = task.compiled_workflow_ids[-1] if task.compiled_workflow_ids else ""
        plan_id = task.execution_plan_ids[-1] if task.execution_plan_ids else ""
        self.workflow.set_workflow(compiled_id, plan_id)
        self.eon.set_plan(plan_id, task.approval_ids)
        self.evidence.set_evidence_ids(task.evidence_ids)
        plan = None
        if plan_id:
            candidate = self.repository.get(plan_id)
            if isinstance(candidate, ExecutionPlan):
                plan = candidate
        self.governance.set_plan(plan)
        self.ourd.set_task(task)
        self.iurm.set_task(task)
        self.replay.set_task(task)

    def set_selection_trace(self, trace: SelectionTrace | None) -> None:
        self.selection.set_trace(trace)

    def show_evidence(self, identifiers: Iterable[str]) -> None:
        self.evidence.set_evidence_ids(identifiers)
        self.right_tabs.select(self.evidence)

    def show_object(self, object_id: str) -> None:
        try:
            envelope = self.repository.get_envelope(object_id)
        except Exception as exc:
            envelope = {"object_id": object_id, "error": f"{type(exc).__name__}: {exc}"}
        self.object_details.set_value(envelope)
        self.right_tabs.select(self.object_details)

    def show_file(self, relative_path: str) -> None:
        self.file_preview.show_file(
            relative_path,
            allow_internal=self.repository_view.internal_state_enabled(),
        )
        self.right_tabs.select(self.file_preview)

    def append_event(self, event) -> None:
        self.trace.append(event)

    def refresh_records(self) -> None:
        self.algorithms.refresh()
        self.governance.refresh()
        self.cfel.refresh()
        self.artifacts.refresh()
        self.assurance.refresh()
        self.performance.refresh()
        self.visual.refresh_assets()

    def show_selection(self) -> None:
        self.center_tabs.select(self.selection)

    def show_workflow(self) -> None:
        self.center_tabs.select(self.workflow)

    def show_trace(self) -> None:
        self.center_tabs.select(self.trace)

    def show_ourd(self) -> None:
        self.center_tabs.select(self.ourd)

    def show_iurm(self) -> None:
        self.center_tabs.select(self.iurm)

    def show_replay(self) -> None:
        self.replay.refresh()
        self.center_tabs.select(self.replay)

    def show_comparison(self) -> None:
        self.center_tabs.select(self.session_compare)

    def show_terminal(self) -> None:
        self.center_tabs.select(self.terminal)

    def show_visual(self) -> None:
        self.visual.refresh_assets()
        self.center_tabs.select(self.visual)

    def show_chat(self) -> None:
        self.center_tabs.select(self.conversation)
        self.conversation.focus_composer()

    def show_repository(self) -> None:
        self.left_tabs.select(self.repository_view)

    def show_governance(self) -> None:
        self.right_tabs.select(self.governance)

    def show_eon(self) -> None:
        self.right_tabs.select(self.eon)

    def show_cfel(self) -> None:
        self.right_tabs.select(self.cfel)

    def show_artifacts(self) -> None:
        self.right_tabs.select(self.artifacts)

    def show_assurance(self) -> None:
        self.right_tabs.select(self.assurance)

    def apply_preferences(self, preferences) -> None:
        for notebook, index in (
            (self.left_tabs, preferences.selected_left_tab),
            (self.center_tabs, preferences.selected_center_tab),
            (self.right_tabs, preferences.selected_right_tab),
        ):
            if 0 <= index < notebook.index("end"):
                notebook.select(index)
        for index, position in enumerate(preferences.pane_positions):
            if index >= len(self.paned.panes()) - 1:
                break
            try:
                self.paned.sashpos(index, position)
            except tk.TclError:
                break
        filters = dict(preferences.filter_values)
        if "algorithms" in filters:
            self.algorithms.query.set(filters["algorithms"])
            self.algorithms.refresh()
        if "cfel" in filters:
            self.cfel.browser.query.set(filters["cfel"])
            self.cfel.refresh()
        self.repository_view.set_show_internal_state(preferences.show_internal_state)
        self.replay.set_reduced_motion(preferences.reduced_motion)

    def preference_state(self) -> dict[str, object]:
        positions = []
        for index in range(max(0, len(self.paned.panes()) - 1)):
            try:
                positions.append(int(self.paned.sashpos(index)))
            except tk.TclError:
                break
        return {
            "selected_left_tab": self.left_tabs.index("current"),
            "selected_center_tab": self.center_tabs.index("current"),
            "selected_right_tab": self.right_tabs.index("current"),
            "pane_positions": tuple(positions),
            "filter_values": (
                ("algorithms", self.algorithms.query.get()),
                ("cfel", self.cfel.browser.query.get()),
            ),
            "show_internal_state": self.repository_view.internal_state_enabled(),
        }
