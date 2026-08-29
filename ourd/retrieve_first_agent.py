from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from .egcf.algebra.unified_retrieval import UnifiedProblemRequirements
from .errors import PolicyError
from .production_agent import ProductionOURDAgent
from .retrieve_first import RetrieveFirstController, RetrieveFirstReceipt


class RetrieveFirstProductionOURDAgent(ProductionOURDAgent):
    """Production OIEC agent with explicit SAA-10.1 retrieve-before-generate policy."""

    def __init__(
        self,
        *args: Any,
        retrieve_first_controller: RetrieveFirstController,
        **kwargs: Any,
    ) -> None:
        if not isinstance(retrieve_first_controller, RetrieveFirstController):
            raise PolicyError("retrieve-first production agent requires RetrieveFirstController")
        self.retrieve_first_controller = retrieve_first_controller
        self._retrieve_first_receipt: RetrieveFirstReceipt | None = None
        super().__init__(*args, **kwargs)

    @property
    def retrieve_first_receipt(self) -> RetrieveFirstReceipt | None:
        return self._retrieve_first_receipt

    def instructions(self) -> str:
        receipt_text = "none"
        if self._retrieve_first_receipt is not None:
            receipt_text = json.dumps(self._retrieve_first_receipt.to_dict(), sort_keys=True)
        return (
            super().instructions()
            + "\n\nRETRIEVE-FIRST POLICY (SAA-10.1):\n"
            + "- A deterministic retrieval receipt is required before production reasoning begins.\n"
            + "- Reuse qualified known mathematical/reasoning algorithms when the receipt identifies a complete fit.\n"
            + "- If only a partial fit exists, reuse the qualified component and adapt/generate only the explicit missing scope.\n"
            + "- Novel algorithm generation is permitted only after the required canonical stores were actually searched and the receipt confirms a gap.\n"
            + "- Retrieved algorithms remain bounded by their evidence, semantic, authority, domain and termination contracts.\n"
            + "- Do not reinterpret linguistic similarity as semantic equivalence; only qualified ontology alignments permit substitution.\n"
            + f"- Current system-verified retrieve-first receipt: {receipt_text}"
        )

    def run_task(
        self,
        task: str,
        *,
        retrieval_requirements: UnifiedProblemRequirements | None = None,
        conversation_history: Sequence[Mapping[str, Any]] = (),
        cancel_check: Optional[Any] = None,
    ) -> str:
        if retrieval_requirements is None:
            raise PolicyError(
                "SAA-10.1 retrieve-first production policy requires explicit UnifiedProblemRequirements; "
                "the runtime will not infer a canonical retrieval contract from free-form prose"
            )
        receipt = self.retrieve_first_controller.evaluate(retrieval_requirements)
        self._retrieve_first_receipt = receipt
        self.trace(
            "retrieve_first_preflight",
            {
                **receipt.to_dict(),
                "epistemic_status": "SYSTEM_VERIFIED_RETRIEVAL_POLICY",
                "problem_id": retrieval_requirements.problem_id,
            },
        )
        if not receipt.required_search_completed:
            raise PolicyError(
                f"retrieve-first blocked: {receipt.status}; required canonical search was not completed"
            )
        return super().run_task(
            task,
            conversation_history=conversation_history,
            cancel_check=cancel_check,
        )


OURDAgent = RetrieveFirstProductionOURDAgent
