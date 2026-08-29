from __future__ import annotations

from typing import Any

from .algebra.semantic_units import SemanticConcept
from .errors import EGCFError
from .models import EvidenceArtifact
from .semantic_ontology import SemanticOntologyStore as _BaseSemanticOntologyStore


class SemanticOntologyStore(_BaseSemanticOntologyStore):
    """Grounded public SAA-9 ontology store with independent evidence resolution at admission."""

    def _verify_concept_evidence(self, concept: SemanticConcept) -> None:
        if not concept.evidence_ids:
            raise EGCFError("semantic ontology concept requires grounded evidence")
        for evidence_id in concept.evidence_ids:
            try:
                record = self.egcf_store.get(evidence_id)
            except Exception as exc:
                raise EGCFError(f"semantic concept evidence is not registered: {evidence_id}") from exc
            if not isinstance(record, EvidenceArtifact):
                raise EGCFError("semantic concept evidence ID does not reference EvidenceArtifact")
            if record.success is not True or record.simulated:
                raise EGCFError("semantic concept evidence must be successful and non-simulated")
            if not record.producer.startswith(("deterministic-", "human-")):
                raise EGCFError("semantic concept evidence requires deterministic or human grounding")
            if record.method in {"reported", "model-claimed", "model-generated-claim"}:
                raise EGCFError("reported/model-claimed evidence cannot ground canonical semantic concepts")

    def admit_concept(self, concept: SemanticConcept) -> str:
        self._verify_concept_evidence(concept)
        return super().admit_concept(concept)
