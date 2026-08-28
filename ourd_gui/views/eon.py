from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ourd.egcf.models import CompiledWorkflow, ExecutionPlan

from ..governance_models import matching_approval
from ..read_models import ReadOnlyEGCFRepository
from ..widgets.json_view import JsonView
from ..widgets.diff_view import DiffView
from ..widgets.status_badge import StatusBadge


def eon_control_state(
    compiled: CompiledWorkflow,
    *,
    snapshot_current: bool,
    approval_available: bool,
) -> dict[str, bool]:
    dry_run = bool(compiled.command_context.get("dry_run", False))
    critical_block = compiled.capability_level in {"C4", "C5"}
    human_approval = compiled.approval_policy in {"human", "quorum"}
    return {
        "simulate": snapshot_current,
        "edit_scope": True,
        "approve": not dry_run and snapshot_current and human_approval and not critical_block,
        "execute": (
            not dry_run
            and snapshot_current
            and not critical_block
            and (not human_approval or approval_available)
        ),
        "critical_block": critical_block,
    }


class EONInspectorView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        repository: ReadOnlyEGCFRepository,
        *,
        on_approve: Callable[[str], None] | None = None,
        on_execute: Callable[[str], None] | None = None,
        on_show_evidence: Callable[[tuple[str, ...]], None] | None = None,
        on_rollback: Callable[[str], None] | None = None,
        on_simulate: Callable[[str], None] | None = None,
        on_edit_scope: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.repository = repository
        self.on_approve = on_approve
        self.on_execute = on_execute
        self.on_show_evidence = on_show_evidence
        self.on_rollback = on_rollback
        self.on_simulate = on_simulate
        self.on_edit_scope = on_edit_scope
        self.plan: ExecutionPlan | None = None
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.capability = StatusBadge(toolbar, "NO PLAN", "neutral")
        self.capability.pack(side="left", padx=4, pady=4)
        self.approve_button = ttk.Button(toolbar, text="Approve Scoped", command=self._approve)
        self.approve_button.pack(side="left", padx=2)
        self.execute_button = ttk.Button(toolbar, text="Execute", command=self._execute)
        self.execute_button.pack(side="left", padx=2)
        self.simulate_button = ttk.Button(toolbar, text="Simulate", command=self._simulate)
        self.simulate_button.pack(side="left", padx=2)
        self.edit_scope_button = ttk.Button(toolbar, text="Edit Scope", command=self._edit_scope)
        self.edit_scope_button.pack(side="left", padx=2)
        ttk.Button(toolbar, text="Show Evidence", command=self._show_evidence).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Rollback", command=self._rollback).pack(side="left", padx=2)
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.details = JsonView(tabs)
        self.diff = DiffView(tabs)
        tabs.add(self.details, text="Action")
        tabs.add(self.diff, text="Candidate Diff")
        self._set_buttons(approve=False, execute=False)

    def _set_buttons(
        self,
        *,
        approve: bool,
        execute: bool,
        simulate: bool = False,
        edit_scope: bool = False,
    ) -> None:
        self.approve_button.configure(state="normal" if approve else "disabled")
        self.execute_button.configure(state="normal" if execute else "disabled")
        self.simulate_button.configure(state="normal" if simulate else "disabled")
        self.edit_scope_button.configure(state="normal" if edit_scope else "disabled")

    def set_plan(self, plan_id: str, approval_ids: tuple[str, ...] = ()) -> None:
        if not plan_id:
            self.plan = None
            self.capability.set_status("neutral", "NO PLAN")
            self.details.set_value({})
            self.diff.set_diff("")
            self._set_buttons(approve=False, execute=False)
            return
        plan = self.repository.get(plan_id)
        if not isinstance(plan, ExecutionPlan):
            raise TypeError(f"not an execution plan: {plan_id}")
        compiled = self.repository.get(plan.compiled_workflow_id)
        if not isinstance(compiled, CompiledWorkflow):
            raise TypeError("execution plan references invalid workflow")
        self.plan = plan
        approval = matching_approval(self.repository, plan, approval_ids)
        current_snapshot = self.repository.source_snapshot()
        snapshot_current = plan.source_snapshot_hash == current_snapshot
        controls = eon_control_state(
            compiled,
            snapshot_current=snapshot_current,
            approval_available=approval is not None,
        )
        self.capability.set_status(
            "blocked"
            if controls["critical_block"] or compiled.approval_policy in {"human", "quorum"}
            else "qualified",
            f"{compiled.capability_level} / {compiled.risk}",
        )
        self.details.set_value(
            {
                "action": compiled.workflow_id,
                "preconditions": [item for node in compiled.nodes for item in node.get("preconditions", [])],
                "targets": [
                    target
                    for node in compiled.nodes
                    for target in node.get("targets", node.get("inputs", {}).get("targets", []))
                ],
                "operations": [node.get("command_id") for node in compiled.nodes],
                "postconditions": [item for node in compiled.nodes for item in node.get("postconditions", [])],
                "preserve": [item for node in compiled.nodes for item in node.get("invariants", [])],
                "evidence": list(plan.evidence_ids),
                "risk": compiled.risk,
                "capability": compiled.capability_level,
                "approval_policy": plan.approval_policy,
                "rollback": plan.rollback_graph,
                "scope": compiled.command_context.get("scope", []),
                "source_snapshot_hash": plan.source_snapshot_hash,
                "current_source_snapshot_hash": current_snapshot,
                "source_snapshot_current": snapshot_current,
                "matching_approval_id": approval.object_id if approval is not None else "",
                "critical_capability_blocked": controls["critical_block"],
                "plan": asdict(plan),
            }
        )
        diffs = []
        for rollback in plan.rollback_graph.values():
            if not isinstance(rollback, dict):
                continue
            prepared = rollback.get("prepared", {})
            if isinstance(prepared, dict) and prepared.get("diff"):
                diffs.append(str(prepared["diff"]))
        self.diff.set_diff("\n".join(diffs))
        self._set_buttons(
            approve=controls["approve"] and self.on_approve is not None,
            execute=controls["execute"] and self.on_execute is not None,
            simulate=controls["simulate"] and self.on_simulate is not None,
            edit_scope=controls["edit_scope"] and self.on_edit_scope is not None,
        )

    def _approve(self) -> None:
        if self.plan is not None and self.on_approve is not None:
            self.on_approve(self.plan.object_id)

    def _execute(self) -> None:
        if self.plan is not None and self.on_execute is not None:
            self.on_execute(self.plan.object_id)

    def _show_evidence(self) -> None:
        if self.plan is not None and self.on_show_evidence is not None:
            self.on_show_evidence(tuple(self.plan.evidence_ids))

    def _rollback(self) -> None:
        if self.plan is not None and self.on_rollback is not None:
            self.on_rollback(self.plan.object_id)

    def _simulate(self) -> None:
        if self.plan is not None and self.on_simulate is not None:
            self.on_simulate(self.plan.object_id)

    def _edit_scope(self) -> None:
        if self.plan is not None and self.on_edit_scope is not None:
            self.on_edit_scope(self.plan.object_id)
