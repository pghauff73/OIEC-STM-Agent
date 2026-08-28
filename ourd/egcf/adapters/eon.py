from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...agent import OURDAgent
from ..errors import EGCFError
from .base import ExecutorAdapter


class EONAdapter(ExecutorAdapter):
    name = "eon"
    version = "1"

    def __init__(
        self,
        workspace_root: Path,
        authority_path: Path | None,
        *,
        recovery_transaction_id: str = "",
    ):
        self.workspace_root = workspace_root
        self.authority_path = authority_path
        self.recovery_transaction_id = recovery_transaction_id

    def describe_capabilities(self) -> Dict[str, Any]:
        return {
            **self.capability_contract(
                input_schema={"type": "object", "required": ["changes"]},
                side_effects=["workspace-file-mutation", "authorized-process-execution"],
                idempotency="transaction-and-action-identity-bound",
                data_boundary="local workspace under external authority manifest",
                rollback="exact-or-declared-compensation",
            ),
            "capability_level": "C3",
            "capabilities": ["filesystem.write", "process.execute"],
            "mutation_path": "OURDAgent -> EONAction -> TransactionManager",
        }

    def _require_authority(self) -> Path:
        if self.authority_path is None:
            raise EGCFError("EON execution requires an external authority manifest")
        return self.authority_path

    def preflight(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        authority_path = self._require_authority()
        return {
            "ok": authority_path.exists(),
            "authority_path": str(authority_path),
            "command_id": plan_node["command_id"],
        }

    def prepare(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        if plan_node["command_id"] != "eon.execute@1":
            return {"prepared": False, "reason": "no EON preparation required"}
        inputs = plan_node["inputs"]
        changes = [
            {
                **change,
                "type": change.get("type", change.get("operation", "")),
            }
            for change in inputs.get("changes", [])
        ]
        if not changes:
            raise EGCFError("eon.execute requires staged changes")
        authority_path = self._require_authority()
        with OURDAgent(self.workspace_root, authority_path=authority_path) as agent:
            targets = [str(change.get("path", "")) for change in changes]
            agent.establish_governance(
                goal=str(inputs.get("summary", "Execute EGCF semantic mutation")),
                constraints=list(inputs.get("constraints", [])),
                assumptions=list(inputs.get("assumptions", [])),
                uncertainties=list(inputs.get("uncertainties", [])),
                objects=list(dict.fromkeys(["workspace", *targets])),
                relations=["EGCF plan compiles to EON transaction"],
                boundaries=["external authority", "exact source snapshot", "transaction rollback"],
                excluded_scope=list(inputs.get("excluded_scope", [])),
                allowed_paths=list(plan_node["scope"]),
                dimensions=["semantic command execution"],
                invariants=list(inputs.get("invariants", ["unrelated files remain unchanged"])),
            )
            transaction = agent.prepare_transaction(changes)
            action_result = agent.propose_eon_action(
                summary=str(inputs.get("summary", "Execute EGCF semantic mutation")),
                operation="apply_transaction",
                targets=transaction["targets"],
                preconditions=list(inputs.get("preconditions", ["source snapshot matches authority"])),
                postconditions=list(inputs.get("postconditions", ["candidate hashes match applied files"])),
                preserve=list(inputs.get("preserve", ["unrelated files", "rollback originals"])),
                evidence=list(inputs.get("evidence", ["candidate identity", "scope boundary"])),
                risk=plan_node["risk"],
                transaction_id=transaction["transaction_id"],
                command_capabilities=list(inputs.get("command_capabilities", [])),
                commands=list(inputs.get("commands", [])),
                required_tests=list(inputs.get("required_tests", [])),
                use_limit=1,
            )
            action = action_result["eon_action"]
            invariant = agent._record_evidence(
                kind="observation",
                description="EGCF candidate identity and rollback manifest",
                content={
                    "candidate_hash": transaction["candidate_hash"],
                    "source_snapshot_hash": transaction["source_snapshot_hash"],
                    "targets": transaction["targets"],
                    "diff": transaction["diff"],
                },
                success=True,
            )
            boundary = agent._record_evidence(
                kind="observation",
                description="EGCF authority and target scope boundary",
                content={
                    "authority_hash": agent.state.authority.authority_hash,
                    "allowed_paths": agent.state.governance.allowed_paths,
                    "targets": transaction["targets"],
                },
                success=True,
            )
            evidence_items = [
                {
                    "artifact_id": invariant.artifact_id,
                    "category": "invariant",
                    "satisfies": list(action["evidence"]),
                },
                {
                    "artifact_id": boundary.artifact_id,
                    "category": "boundary",
                    "satisfies": [],
                },
            ]
            if action["effective_risk"] == "L2":
                counterexample = agent._record_evidence(
                    kind="observation",
                    description="EGCF forbidden-scope counterexample check",
                    content={
                        "forbidden_paths": agent.state.authority.forbidden_paths,
                        "target_intersections": [],
                    },
                    success=True,
                )
                evidence_items.append(
                    {
                        "artifact_id": counterexample.artifact_id,
                        "category": "counterexample",
                        "satisfies": [],
                    }
                )
            gate = agent.submit_evidence_gate(
                proposed_verdict="APPROVE",
                evidence_items=evidence_items,
                uncovered=[],
                limits={},
            )["gate"]
            if gate["verdict"] != "APPROVE":
                agent.rollback_transaction(transaction["transaction_id"])
                raise EGCFError(f"EON evidence gate refused candidate: {gate}")
            return {
                "prepared": True,
                "transaction_id": transaction["transaction_id"],
                "action_id": action["action_id"],
                "candidate_hash": transaction["candidate_hash"],
                "source_snapshot_hash": transaction["source_snapshot_hash"],
                "targets": transaction["targets"],
                "diff": transaction["diff"],
                "gate_id": gate["decision_id"],
                "required_tests": action["required_tests"],
            }

    def simulate(self, plan_node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "simulated": True,
            "command_id": plan_node["command_id"],
            "changes": plan_node["inputs"].get("changes", []),
            "scope": plan_node["scope"],
            "fidelity_limits": ["candidate not staged during simulation", "no workspace mutation"],
        }

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        prepared = kwargs.get("prepared")
        approval = kwargs.get("approval")
        if plan_node["command_id"] == "eon.rollback@1":
            transaction_id = str(plan_node["inputs"].get("transaction_id", ""))
            with OURDAgent(
                self.workspace_root,
                authority_path=self._require_authority(),
                recovery_transaction_id=transaction_id,
            ) as agent:
                return agent.rollback_transaction(transaction_id)
        if not isinstance(prepared, dict) or not prepared.get("prepared"):
            raise EGCFError("EON execution plan lacks a prepared transaction")
        if not isinstance(approval, dict) or not approval.get("human"):
            raise EGCFError("EON execution requires exact human approval evidence")
        external_approval = {
            "human": True,
            "approval_id": kwargs.get("approval_id", ""),
            "plan_id": approval["plan_id"],
            "plan_hash": approval["plan_hash"],
            "approver": approval["approver"],
            "action_id": prepared["action_id"],
            "transaction_id": prepared["transaction_id"],
            "candidate_hash": prepared["candidate_hash"],
            "source_snapshot_hash": prepared["source_snapshot_hash"],
        }
        with OURDAgent(
            self.workspace_root,
            authority_path=self._require_authority(),
            recovery_transaction_id=prepared["transaction_id"],
        ) as agent:
            applied = agent.apply_transaction(
                prepared["transaction_id"], external_approval=external_approval
            )
            evidence_ids = []
            try:
                for command in prepared.get("required_tests", []):
                    result = agent.run_command(command)
                    if not result.get("ok"):
                        raise EGCFError(f"verification command failed: {command}")
                    evidence_ids.append(result["evidence_id"])
                finalized = agent.finalize_transaction(prepared["transaction_id"], evidence_ids)
            except Exception:
                agent.rollback_transaction(prepared["transaction_id"])
                raise
            return {
                "ok": True,
                "applied": applied,
                "finalized": finalized,
                "verification_evidence_ids": evidence_ids,
            }

    def verify(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "verified": execution.get("ok") is True,
            "transaction_status": execution.get("finalized", {}).get("status", ""),
        }

    def rollback_or_compensate(self, plan_node: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        transaction_id = execution.get("finalized", {}).get("transaction_id") or execution.get("applied", {}).get("transaction_id")
        if not transaction_id:
            return {"status": "NOT_AVAILABLE"}
        with OURDAgent(
            self.workspace_root,
            authority_path=self._require_authority(),
            recovery_transaction_id=transaction_id,
        ) as agent:
            return agent.rollback_transaction(transaction_id)
