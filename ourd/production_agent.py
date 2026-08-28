from __future__ import annotations

import json
import os
from typing import Any, Callable, List, Mapping, Optional, Sequence

from .agent import OURDAgent as BaseOURDAgent
from .cfel import fingerprint, record_collision
from .errors import AgentCancelledError, ContextBudgetError, ProviderError, StateError
from .loop_control import (
    LoopProgressController,
    TransitionAssessment,
    model_belief_record,
    semantic_step_signature,
)


class ProductionOURDAgent(BaseOURDAgent):
    """Production loop with explicit belief/verification and progress boundaries.

    Model outputs remain proposals. Only deterministic tool/evidence/state changes
    are projected into the verified state used to authorize continued autonomy.
    """

    def instructions(self) -> str:
        return (
            super().instructions()
            + "\n\n"
            + "EPISTEMIC BOUNDARY:\n"
            + "- Your prose, assumptions, hypotheses, confidence and plans are MODEL BELIEF/PROPOSAL, not verified facts.\n"
            + "- Only deterministic tool observations, grounded EvidenceArtifact records, authority/gate state, and transaction state are system-verified.\n"
            + "- Never describe a model inference as verified merely because it is plausible or repeated.\n"
            + "- You cannot self-certify progress. The runtime computes a ProgressCertificate from verified before/after state.\n"
            + "- Every nonterminal autonomous tool step must produce novel verified evidence or governed state progress.\n"
            + "- Equivalent observations are content-deduplicated; new UUIDs, call IDs, evidence IDs or wording do not create progress.\n"
            + "- If the controller reports CYCLE_STOP, stop. Do not rephrase the same attempt to evade the loop boundary."
        )

    def _persist_progress(self, assessment: TransitionAssessment) -> None:
        self.state.last_progress = assessment.certificate
        self.state.transition_index += 1
        self.trace(
            "progress_certificate",
            {
                **assessment.to_dict(),
                "epistemic_status": "SYSTEM_VERIFIED_PROGRESS",
                "transition_index": self.state.transition_index,
            },
        )
        self.save_state()

    def _stop_for_cycle(self, assessment: TransitionAssessment) -> None:
        severity = 10_000 if assessment.cycle_kind != "NO_VERIFIED_PROGRESS" else 5_000
        collision = record_collision(
            self.state,
            action_id=self.state.pending_action.action_id if self.state.pending_action else "",
            expected="every nonterminal autonomous transition produces system-verified progress",
            observed=assessment.reason,
            objects=["agent-loop", assessment.cycle_kind or "progress-gate"],
            boundary="autonomous progress and cycle control",
            active_dimension="verified_transition_progress",
            frozen_dimensions=["authority", "verified evidence", "system state"],
            evidence_ids=[],
            proposed_correction=(
                "obtain genuinely new evidence, change the bounded hypothesis/experiment, "
                "or stop and request human input"
            ),
            falsifier="a materially different verified-state transition",
            disposition="CYCLE_STOP",
            collision_fingerprint=fingerprint(
                {
                    "kind": assessment.cycle_kind,
                    "period": assessment.period,
                    "step": assessment.step_signature,
                    "before": assessment.before_signature,
                    "after": assessment.after_signature,
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
            },
        )
        input_items: List[Any] = [*history, {"role": "user", "content": task}]
        controller = LoopProgressController()

        for step in range(1, self.max_steps + 1):
            self._require_not_cancelled(cancel_check)
            print(f"[agent step {step}]", file=os.sys.stderr)
            tools = self.tool_specs()
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
                item
                for item in output_items
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
                        "progress_certificate": assessment.certificate.signature,
                        "note": (
                            "the system verified the transition/observations, not the truth of "
                            "unsupported model prose"
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


# Explicit alias for entry points that want production semantics while leaving
# the compatibility core class in ourd.agent untouched.
OURDAgent = ProductionOURDAgent
