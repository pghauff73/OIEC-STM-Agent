from __future__ import annotations

import json
import os
from typing import Any, Callable, List, Mapping, Optional, Sequence

from .agent import OURDAgent as BaseOURDAgent
from .cfel import fingerprint, record_collision
from .errors import AgentCancelledError, ContextBudgetError, PolicyError, ProviderError, StateError
from .hypotheses import (
    bounded_hypothesis_set,
    link_hypothesis_evidence as bind_hypothesis_evidence,
    public_hypothesis_projection,
)
from .loop_control import (
    LoopProgressController,
    TransitionAssessment,
    model_belief_record,
)


class ProductionOURDAgent(BaseOURDAgent):
    """Production loop with explicit belief/verification and progress boundaries."""

    def __init__(self, *args: Any, max_control_only_progress: int = 2, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_control_only_progress = max(0, min(int(max_control_only_progress), 16))

    def instructions(self) -> str:
        return (
            super().instructions()
            + "\n\n"
            + "EPISTEMIC BOUNDARY:\n"
            + "- Your prose, assumptions, hypotheses, confidence and plans are MODEL BELIEF/PROPOSAL, not verified facts.\n"
            + "- Only deterministic tool observations, grounded EvidenceArtifact records, authority/gate state, transaction state, and deterministic hypothesis bookkeeping are system-verified.\n"
            + "- A hypothesis proposition always remains UNVERIFIED_PROPOSITION unless an external verifier establishes it; linked evidence only changes its bounded evidence bookkeeping.\n"
            + "- Use propose_hypotheses to create a finite competing hypothesis pool; duplicate hypotheses are content-deduplicated and the active set is capped.\n"
            + "- Use link_hypothesis_evidence only with real evidence IDs returned by tools. The relation label is still MODEL_PROPOSED_RELATION_TO_VERIFIED_EVIDENCE.\n"
            + "- Never describe a model inference as verified merely because it is plausible, repeated, or evidence-linked.\n"
            + "- You cannot self-certify progress. The runtime computes a ProgressCertificate from verified before/after state.\n"
            + f"- At most {self.max_control_only_progress} consecutive control-only transitions are allowed; hypothesis/governance/action churn must then produce new evidence or hypothesis discrimination.\n"
            + "- Equivalent observations are content-deduplicated; new UUIDs, call IDs, evidence IDs or wording do not create progress.\n"
            + "- Bounded for-style iteration is allowed through system-owned cursors: advance list_files with next_offset and read_file with next_start_line until has_more is false.\n"
            + "- A loop cursor must advance monotonically. Repeating the same page, line range or unchanged observation is not a new iteration and will be stopped.\n"
            + "- If the controller reports CYCLE_STOP, stop. Do not rephrase the same attempt to evade the loop boundary."
        )

    def tool_specs(self) -> List[dict[str, Any]]:
        tools = list(super().tool_specs())
        string = {"type": "string"}
        strings = {"type": "array", "items": string}
        tools.extend(
            [
                {
                    "type": "function",
                    "name": "propose_hypotheses",
                    "description": (
                        "Add bounded competing model hypotheses. Hypothesis propositions remain "
                        "unverified; creating hypotheses is control-only progress."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hypotheses": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 16,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "proposition": string,
                                        "model_prior_bp": {
                                            "type": "integer",
                                            "minimum": 0,
                                            "maximum": 10000,
                                        },
                                        "assumptions": strings,
                                        "predictions": strings,
                                        "falsifiers": strings,
                                    },
                                    "required": [
                                        "proposition",
                                        "model_prior_bp",
                                        "assumptions",
                                        "predictions",
                                        "falsifiers",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["hypotheses"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
                {
                    "type": "function",
                    "name": "link_hypothesis_evidence",
                    "description": (
                        "Link one grounded evidence artifact to one hypothesis as supports, "
                        "conflicts, or falsifies. The relation remains model-proposed."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hypothesis_id": string,
                            "evidence_id": string,
                            "relation": {
                                "type": "string",
                                "enum": ["supports", "conflicts", "falsifies"],
                            },
                        },
                        "required": ["hypothesis_id", "evidence_id", "relation"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
                {
                    "type": "function",
                    "name": "list_hypotheses",
                    "description": "Read the bounded hypothesis pool and evidence-link state.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            ]
        )
        return tools

    def _active_hypothesis_bound(self) -> int:
        if self.state.dimension_budget is not None:
            return int(self.state.dimension_budget.max_active_hypotheses)
        return int(self.oiec.max_active_hypotheses)

    def propose_hypotheses(self, hypotheses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        updated, added = bounded_hypothesis_set(
            self.state.hypothesis_state,
            hypotheses,
            max_hypotheses=self._active_hypothesis_bound(),
        )
        self.state.hypothesis_state = updated
        self.trace(
            "hypothesis_state_updated",
            {
                "operation": "propose",
                "added_hypothesis_ids": list(added),
                "hypothesis_count": len(updated.hypotheses),
                "max_hypotheses": updated.max_hypotheses,
                "hypothesis_set_signature": updated.signature,
                "epistemic_status": "MODEL_HYPOTHESES_RECORDED_NOT_VERIFIED",
            },
        )
        self.save_state()
        return {
            "ok": True,
            "added_hypothesis_ids": list(added),
            "duplicate_count": len(hypotheses) - len(added),
            "hypothesis_state": public_hypothesis_projection(updated),
        }

    def link_hypothesis_evidence(
        self,
        hypothesis_id: str,
        evidence_id: str,
        relation: str,
    ) -> dict[str, Any]:
        if self.state.hypothesis_state is None:
            raise PolicyError("no hypothesis state exists; propose hypotheses first")
        updated, changed = bind_hypothesis_evidence(
            self.state.hypothesis_state,
            self.state.evidence_registry,
            hypothesis_id=hypothesis_id,
            evidence_id=evidence_id,
            relation=relation,
        )
        self.state.hypothesis_state = updated
        self.trace(
            "hypothesis_evidence_linked",
            {
                "hypothesis_id": hypothesis_id,
                "evidence_id": evidence_id,
                "relation": relation,
                "changed": changed,
                "hypothesis_set_signature": updated.signature,
                "relation_epistemic_status": "MODEL_PROPOSED_RELATION_TO_VERIFIED_EVIDENCE",
                "proposition_verification_status": "UNVERIFIED_PROPOSITION",
            },
        )
        self.save_state()
        return {
            "ok": True,
            "changed": changed,
            "hypothesis_state": public_hypothesis_projection(updated),
        }

    def list_hypotheses(self) -> dict[str, Any]:
        return {
            "ok": True,
            "hypothesis_state": public_hypothesis_projection(self.state.hypothesis_state),
        }

    def _persist_progress(self, assessment: TransitionAssessment) -> None:
        self.state.last_progress = assessment.certificate
        self.state.transition_index += 1
        self.state.control_only_progress_streak = assessment.control_only_streak
        self.trace(
            "progress_certificate",
            {
                **assessment.to_dict(),
                "epistemic_status": "SYSTEM_VERIFIED_PROGRESS",
                "transition_index": self.state.transition_index,
                "persisted_control_only_streak": self.state.control_only_progress_streak,
            },
        )
        self.save_state()

    def _stop_for_cycle(self, assessment: TransitionAssessment) -> None:
        if assessment.cycle_kind == "NO_VERIFIED_PROGRESS":
            severity = 5_000
        elif assessment.cycle_kind == "CONTROL_ONLY_BUDGET_EXHAUSTED":
            severity = 7_500
        else:
            severity = 10_000
        collision = record_collision(
            self.state,
            action_id=self.state.pending_action.action_id if self.state.pending_action else "",
            expected=(
                "every nonterminal autonomous transition produces system-verified epistemic "
                "progress or remains inside the bounded control-only allowance"
            ),
            observed=assessment.reason,
            objects=["agent-loop", assessment.cycle_kind or "progress-gate"],
            boundary="autonomous progress and cycle control",
            active_dimension="verified_transition_progress",
            frozen_dimensions=["authority", "verified evidence", "hypothesis state", "system state"],
            evidence_ids=[],
            proposed_correction=(
                "obtain genuinely new evidence, link discriminating grounded evidence to a "
                "bounded hypothesis, change the experiment, or stop and request human input"
            ),
            falsifier="a materially different verified-state transition with epistemic gain",
            disposition="CYCLE_STOP",
            collision_fingerprint=fingerprint(
                {
                    "kind": assessment.cycle_kind,
                    "period": assessment.period,
                    "step": assessment.step_signature,
                    "before": assessment.before_signature,
                    "after": assessment.after_signature,
                    "control_only_streak": assessment.control_only_streak,
                }
            ),
            severity_bp=severity,
        )
        self.trace(
            "cycle_stop",
            {
                "collision_id": collision.collision_id,
                "cycle_kind": assessment.cycle_kind,
                "period": assessment.period,
                "reason": assessment.reason,
                "control_only_streak": assessment.control_only_streak,
                "max_control_only_progress": assessment.max_control_only_progress,
                "progress_certificate": assessment.certificate.signature,
                "epistemic_status": "SYSTEM_VERIFIED_STOP",
            },
        )
        self.save_state()
        raise StateError(
            f"OIEC CYCLE_STOP [{assessment.cycle_kind or 'NO_PROGRESS'}]: "
            f"{assessment.reason}"
        )

    def run_task(
        self,
        task: str,
        *,
        conversation_history: Sequence[Mapping[str, Any]] = (),
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        self._require_not_cancelled(cancel_check)
        provider = self._provider()
        try:
            preflight = provider.preflight()
        except ProviderError as exc:
            record_collision(
                self.state,
                action_id=self.state.pending_action.action_id if self.state.pending_action else "",
                expected="provider preflight succeeds",
                observed=str(exc),
                objects=["provider", self.model],
                boundary="provider preflight",
                active_dimension="provider_configuration",
                frozen_dimensions=["authority", "workspace"],
                evidence_ids=[],
                disposition="blocked pending provider correction",
            )
            self.save_state()
            raise

        self.trace("provider_preflight", preflight)
        history = self._bounded_conversation_history(conversation_history)
        self.trace(
            "run_started",
            {
                "task": task,
                "provider": preflight,
                "history_message_count": len(history),
                "epistemic_policy": "model-belief-separated-from-system-verification",
                "mandatory_progress_certificates": True,
                "cycle_detection": True,
                "hypothesis_state": True,
                "max_active_hypotheses": self._active_hypothesis_bound(),
                "max_control_only_progress": self.max_control_only_progress,
                "initial_control_only_streak": self.state.control_only_progress_streak,
            },
        )
        input_items: List[Any] = [*history, {"role": "user", "content": task}]
        named_file_read = False
        controller = LoopProgressController(
            max_control_only_progress=self.max_control_only_progress,
            initial_control_only_streak=self.state.control_only_progress_streak,
        )

        for step in range(1, self.max_steps + 1):
            self._require_not_cancelled(cancel_check)
            print(f"[agent step {step}]", file=os.sys.stderr)
            tools = self._tools_for_model_context(named_file_read=named_file_read)
            instructions = self.instructions()
            self.trace(
                "model_request",
                {
                    "step": step,
                    "model": self.model,
                    "input_item_count": len(input_items),
                    "tool_count": len(tools),
                    "context_budget_tokens": self.provider_config.context_budget_tokens,
                    "max_output_tokens": self.provider_config.max_output_tokens,
                    "reasoning_effort": self.provider_config.reasoning_effort or "provider_default",
                    "max_transport_retries": self.provider_config.max_transport_retries,
                    "history_message_count": len(history),
                    "epistemic_status": "REQUESTING_MODEL_BELIEF",
                    "tool_context_mode": (
                        "named_file_read" if named_file_read else "full"
                    ),
                },
            )
            try:
                response = provider.create_response(
                    instructions=instructions,
                    input_items=input_items,
                    tools=tools,
                )
            except (ContextBudgetError, ProviderError) as exc:
                record_collision(
                    self.state,
                    action_id=self.state.pending_action.action_id if self.state.pending_action else "",
                    expected="provider returns a protocol-compatible response",
                    observed=str(exc),
                    objects=["provider", self.model],
                    boundary="model context or transport",
                    active_dimension="provider_request",
                    frozen_dimensions=["authority", "workspace", "tool schema"],
                    evidence_ids=[],
                    disposition="blocked pending bounded revised request",
                )
                self.save_state()
                raise

            self._require_not_cancelled(cancel_check)
            output_items = list(self._get(response, "output", []))
            raw_calls = [
                item for item in output_items
                if self._get(item, "type", "") == "function_call"
            ]
            parsed_calls: list[tuple[str, Mapping[str, Any]]] = []
            for call in raw_calls:
                name = self._get(call, "name", "")
                arguments = self._get(call, "arguments", "{}")
                try:
                    parsed_for_signature = json.loads(arguments)
                    if not isinstance(parsed_for_signature, dict):
                        parsed_for_signature = {"value": parsed_for_signature}
                except json.JSONDecodeError:
                    parsed_for_signature = {"raw_arguments": arguments}
                parsed_calls.append((name, parsed_for_signature))

            output_text = self._response_text(response, output_items)
            belief = model_belief_record(
                step=step,
                output_text=output_text,
                calls=parsed_calls,
            )
            self.trace("model_belief", belief)
            step_signature = belief["semantic_step_signature"]
            before = controller.project(self.state, self.ws.snapshot_hash())

            if not raw_calls:
                after = controller.project(self.state, self.ws.snapshot_hash())
                assessment = controller.assess(
                    before=before,
                    after=after,
                    step_signature=step_signature,
                    terminal=True,
                )
                self._persist_progress(assessment)
                self.trace(
                    "final",
                    {
                        "text": output_text,
                        "epistemic_status": "MODEL_OUTPUT_UNVERIFIED",
                        "verified_state_signature": after.signature,
                        "hypothesis_state_signature": (
                            self.state.hypothesis_state.signature
                            if self.state.hypothesis_state is not None
                            else ""
                        ),
                        "progress_certificate": assessment.certificate.signature,
                        "note": (
                            "the system verified the transition/observations, not the truth of "
                            "unsupported model prose or hypothesis propositions"
                        ),
                    },
                )
                self.save_state()
                return output_text

            input_items.extend(output_items)
            for call in raw_calls:
                self._require_not_cancelled(cancel_check)
                arguments = self._get(call, "arguments", "{}")
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    result = {"ok": False, "error": f"invalid tool JSON: {exc}"}
                    record_collision(
                        self.state,
                        action_id=self.state.pending_action.action_id if self.state.pending_action else "",
                        expected="model emits valid JSON tool arguments",
                        observed=str(exc),
                        objects=["provider", self._get(call, "name", "")],
                        boundary="tool protocol",
                        active_dimension="tool_arguments",
                        frozen_dimensions=["authority", "tool schema"],
                        evidence_ids=[],
                        disposition="blocked pending revised tool call",
                        collision_fingerprint=fingerprint(
                            {
                                "name": self._get(call, "name", ""),
                                "arguments": arguments,
                            }
                        ),
                    )
                    self.save_state()
                else:
                    result = self.dispatch(self._get(call, "name", ""), parsed)
                    if self._get(call, "name", "") == "read_file":
                        named_file_read = named_file_read or self._is_named_file_read(
                            task,
                            result,
                        )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": self._get(call, "call_id", ""),
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            after = controller.project(self.state, self.ws.snapshot_hash())
            assessment = controller.assess(
                before=before,
                after=after,
                step_signature=step_signature,
                terminal=False,
            )
            self._persist_progress(assessment)
            if not assessment.allowed:
                self._stop_for_cycle(assessment)

        raise RuntimeError(f"maximum agent steps exceeded ({self.max_steps})")


OURDAgent = ProductionOURDAgent
