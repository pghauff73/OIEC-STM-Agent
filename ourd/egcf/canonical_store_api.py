from __future__ import annotations

import json
from typing import Any, Sequence

from ..persistence import atomic_write_text
from .canonical_store import CanonicalAlgorithmStore as _CanonicalAlgorithmStore
from .errors import EGCFError
from .ids import canonical_json


class CanonicalAlgorithmStore(_CanonicalAlgorithmStore):
    """Public SAA canonical store with rebuild-safe metadata and strict semantic evidence relevance."""

    def _persist_canonical(
        self,
        form: Any,
        canonical_id: str,
        source_id: str,
        generation: int,
        created_at: str,
    ) -> None:
        canonical_payload = self._canonical_payload(form)
        path = self._algorithm_path(canonical_id)
        envelope = {
            "schema_version": 1,
            "object_type": "canonical-algorithm",
            "object_id": canonical_id,
            "store_version": "saa-canonical-algorithm-store-v1",
            "store_generation": generation,
            "created_at": created_at,
            "anchor_source_id": source_id,
            "canonical_algorithm_signature": form.canonical_algorithm_signature,
            "payload": canonical_payload,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if canonical_json(existing) != canonical_json(envelope):
                raise EGCFError(f"immutable canonical-store collision at {path}")
        else:
            atomic_write_text(path, serialized)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_algorithms("
                "canonical_id, representative_behavior_signature, mathematical_signature, semantic_signature, "
                "canonical_algorithm_signature, representative_version, domain, output_count, input_count, "
                "store_generation, payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    canonical_id,
                    form.representative_behavior_signature,
                    form.mathematical_representative_signature,
                    form.semantic_representative_signature,
                    form.canonical_algorithm_signature,
                    form.representative_version,
                    form.domain,
                    form.output_count,
                    form.representative_input_count,
                    generation,
                    canonical_json(canonical_payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )

    def _verify_semantic_proof(
        self,
        form: Any,
        issues: Sequence[Any],
        candidates: Sequence[Any],
        resolutions: Sequence[Any],
    ) -> str:
        proof_signature = super()._verify_semantic_proof(
            form, issues, candidates, resolutions
        )
        if form.representative_input_count == 0:
            return proof_signature
        issue_by_id = {issue.issue_id: issue for issue in issues}
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        for resolution in resolutions:
            issue = issue_by_id.get(resolution.issue_id)
            candidate = candidate_by_id.get(resolution.candidate_id)
            if issue is None or candidate is None:
                raise EGCFError("semantic proof relevance cannot resolve issue/candidate")
            for evidence_id in resolution.evidence_ids:
                artifact = self._grounded_evidence(evidence_id)
                if artifact.category != "semantic-grounding":
                    raise EGCFError("canonical semantic evidence must use semantic-grounding category")
                if (
                    artifact.subject_id not in {issue.issue_id, candidate.candidate_id}
                    and issue.issue_id not in artifact.claim_ids
                ):
                    raise EGCFError(
                        "canonical semantic evidence is grounded but not relevant to the resolved meaning"
                    )
            for falsifier_result in resolution.falsifier_results:
                if falsifier_result.evidence_id:
                    artifact = self._grounded_evidence(falsifier_result.evidence_id)
                    if artifact.category != "semantic-grounding":
                        raise EGCFError("semantic falsifier evidence must use semantic-grounding category")
                    if (
                        artifact.subject_id not in {issue.issue_id, candidate.candidate_id}
                        and issue.issue_id not in artifact.claim_ids
                    ):
                        raise EGCFError("semantic falsifier evidence is unrelated to the semantic issue")
        return proof_signature
