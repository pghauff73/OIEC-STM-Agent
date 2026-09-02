from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence

from ourd.production_agent import ProductionOURDAgent as OURDAgent
from ourd.egcf.engine import EGCFEngine
from ourd.providers import ProviderConfig
from ourd.interaction import TurnExecutionPolicy
from ourd.workspace import Workspace

from .commands import (
    ApprovalRequest,
    CommandRequest,
    ExecutionRequest,
    ObjectiveRequest,
    ReplayRequest,
)


class CoreGateway:
    """Short-lived, policy-preserving access to the governed core."""

    def __init__(
        self,
        repository_root: Path,
        *,
        authority_path: Path | None = None,
        actor: str = "user",
        recovery_transaction_id: str = "",
        provider_config: ProviderConfig | None = None,
        max_agent_steps: int = 80,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.authority_path = authority_path
        self.actor = actor
        self.recovery_transaction_id = recovery_transaction_id
        self.provider_config = provider_config or ProviderConfig(model="qwen3.8-27b-direct")
        if not self.provider_config.visual_asset_root:
            self.provider_config.visual_asset_root = str(
                self.repository_root / ".ourd-agent" / "gui-assets"
            )
        self.max_agent_steps = max(1, int(max_agent_steps))
        Workspace(self.repository_root)

    def _engine(self) -> EGCFEngine:
        return EGCFEngine(
            self.repository_root,
            authority_path=self.authority_path,
            actor=self.actor,
            recovery_transaction_id=self.recovery_transaction_id,
        )

    def snapshot(self) -> str:
        return Workspace(self.repository_root).snapshot_hash()

    def run_objective(self, request: ObjectiveRequest) -> Dict[str, Any]:
        with self._engine() as engine:
            return engine.run_objective(
                request.objective,
                inputs=dict(request.inputs),
                modifiers=dict(request.modifiers),
            )

    def invoke(self, request: CommandRequest) -> Dict[str, Any]:
        with self._engine() as engine:
            return engine.invoke(
                request.command_id,
                dict(request.inputs),
                dict(request.modifiers),
            )

    def authorize(self, request: ApprovalRequest) -> Dict[str, Any]:
        with self._engine() as engine:
            approval_id = engine.authorize(
                request.plan_id,
                approver=request.approver,
                authority=request.authority,
                constraints=dict(request.constraints),
                expires_at=request.expires_at,
                use_limit=request.use_limit,
            )
        return {"ok": True, "approval_id": approval_id, "plan_id": request.plan_id}

    def execute(self, request: ExecutionRequest) -> Dict[str, Any]:
        with self._engine() as engine:
            return engine.execute_plan(
                request.plan_id,
                request.approval_id,
                pause_at_checkpoint=request.pause_at_checkpoint,
                resume=request.resume,
            )

    def replay(self, request: ReplayRequest) -> Dict[str, Any]:
        with self._engine() as engine:
            return engine.replay(request.plan_id, dict(request.modifiers))

    def provider_preflight(self) -> Dict[str, Any]:
        with OURDAgent(
            self.repository_root,
            authority_path=self.authority_path,
            recovery_transaction_id=self.recovery_transaction_id,
            provider_config=self.provider_config,
            max_steps=self.max_agent_steps,
        ) as agent:
            return agent.provider_preflight()

    def chat_turn(
        self,
        message: str,
        history: Sequence[Mapping[str, Any]],
        *,
        event_callback: Callable[[Mapping[str, Any]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        turn_execution_policy: TurnExecutionPolicy | None = None,
    ) -> str:
        with OURDAgent(
            self.repository_root,
            authority_path=self.authority_path,
            recovery_transaction_id=self.recovery_transaction_id,
            provider_config=self.provider_config,
            max_steps=self.max_agent_steps,
            event_callback=event_callback,
            turn_execution_policy=turn_execution_policy,
        ) as agent:
            return agent.run_task(
                message,
                conversation_history=history,
                cancel_check=cancel_check,
                turn_execution_policy=turn_execution_policy,
            )
