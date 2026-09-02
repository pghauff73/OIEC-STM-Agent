from __future__ import annotations

from typing import Any, Mapping, Sequence

from .algebra.brain_feed import (
    BrainFeedBatchReceipt,
    BrainFeedDisposition,
    BrainFeedItem,
    make_brain_feed_batch_receipt,
    make_brain_feed_disposition,
)
from .algebra.failure_algebra import make_failure_observation
from .algebra.semantic_units import PhysicalDimensionVector, make_semantic_concept
from .brain_feed_store import BrainFeedStore
from .errors import EGCFError
from .ids import sha256_json, utc_now
from .knowledge_governance_store import KnowledgeGovernanceStore
from .models import EvidenceArtifact
from .semantic_ontology import SemanticOntologyStore


STAGED_CANDIDATE_KINDS = {
    "ALGORITHM_CANDIDATE",
    "REASONING_CANDIDATE",
    "EXPERIMENT_CANDIDATE",
    "DATASET",
    "CLAIM",
    "INVARIANT_CANDIDATE",
    "SOURCE_DOCUMENT",
}


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        raise EGCFError("brain-feed reference list must be an array")
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _grounded_evidence(store: Any, evidence_ids: Sequence[str]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    for evidence_id in evidence_ids:
        try:
            record = store.get(evidence_id)
        except Exception:
            reasons.append(f"EVIDENCE_NOT_REGISTERED:{evidence_id}")
            continue
        if not isinstance(record, EvidenceArtifact):
            reasons.append(f"NOT_EVIDENCE_ARTIFACT:{evidence_id}")
            continue
        if record.success is not True:
            reasons.append(f"EVIDENCE_NOT_SUCCESSFUL:{evidence_id}")
        if record.simulated:
            reasons.append(f"SIMULATED_EVIDENCE:{evidence_id}")
        if not record.producer.startswith(("deterministic-", "human-")):
            reasons.append(f"EVIDENCE_PRODUCER_NOT_GROUNDED:{evidence_id}")
        if record.method == "reported":
            reasons.append(f"REPORTED_ONLY_EVIDENCE:{evidence_id}")
    return not reasons and bool(evidence_ids), tuple(reasons)


def _resolved_evidence_ids(
    item: BrainFeedItem,
    resolved: Mapping[str, BrainFeedDisposition],
) -> tuple[str, ...]:
    direct = list(_strings(item.payload.get("evidence_ids", ())))
    for item_id in item.evidence_from:
        disposition = resolved.get(item_id)
        if disposition is None:
            continue
        direct.extend(ref for ref in disposition.target_refs if ref.startswith("egcf-evidence:sha256:"))
    return tuple(sorted(set(direct)))


def _measurement_evidence(
    item: BrainFeedItem,
    *,
    source_signature: str,
) -> tuple[EvidenceArtifact | None, tuple[str, ...]]:
    payload = item.payload
    required = ("subject_id", "producer", "method", "target", "oracle", "independence_group")
    missing = [name for name in required if not str(payload.get(name, "")).strip()]
    if missing:
        return None, tuple(f"MISSING_EVIDENCE_METADATA:{name}" for name in missing)
    producer = str(payload["producer"]).strip()
    method = str(payload["method"]).strip()
    simulated = bool(payload.get("simulated", False))
    success = payload.get("success", True)
    grounding_reasons: list[str] = []
    if not producer.startswith(("deterministic-", "human-")):
        grounding_reasons.append("PRODUCER_MUST_START_DETERMINISTIC_OR_HUMAN")
    if method == "reported":
        grounding_reasons.append("REPORTED_ONLY_MEASUREMENT_IS_NOT_GROUNDED")
    if simulated:
        grounding_reasons.append("SIMULATED_MEASUREMENT_CANNOT_BE_GROUNDED_REAL_EVIDENCE")
    if success is not True:
        grounding_reasons.append("MEASUREMENT_EVIDENCE_MUST_BE_SUCCESSFUL")
    if grounding_reasons:
        return None, tuple(grounding_reasons)
    content = payload.get("content", payload.get("value"))
    evidence_hash = str(payload.get("sha256", "")).strip().lower() or sha256_json(
        {
            "brain_feed_item_signature": item.item_signature,
            "content": content,
            "target": payload["target"],
            "oracle": payload["oracle"],
        }
    )
    return EvidenceArtifact(
        subject_id=str(payload["subject_id"]).strip(),
        claim_ids=list(_strings(payload.get("claim_ids", ()))),
        requirement_ids=list(_strings(payload.get("requirement_ids", ()))),
        category=str(payload.get("category", "measurement")).strip() or "measurement",
        producer=producer,
        method=method,
        source_snapshot_hash=str(payload.get("source_snapshot_hash", source_signature)).strip() or source_signature,
        target=str(payload["target"]).strip(),
        oracle=str(payload["oracle"]).strip(),
        environment=dict(payload.get("environment", {})),
        command_id=str(payload.get("command_id", "brain.feed@1")).strip(),
        algorithm_id=str(payload.get("algorithm_id", "")).strip(),
        created_at=str(payload.get("created_at", payload.get("observed_at", utc_now()))).strip(),
        sha256=evidence_hash,
        success=True,
        limitations=list(_strings(payload.get("limitations", ()))),
        independence_group=str(payload["independence_group"]).strip(),
        simulated=False,
        path=item.source_path,
        content=content,
    ), ()


def _candidate_validation(item: BrainFeedItem) -> tuple[bool, tuple[str, ...]]:
    payload = item.payload
    reasons: list[str] = []
    if item.kind == "ALGORITHM_CANDIDATE":
        if not str(payload.get("name", "")).strip():
            reasons.append("MISSING_ALGORITHM_NAME")
        if "inputs" not in payload:
            reasons.append("MISSING_ALGORITHM_INPUTS")
        if "outputs" not in payload:
            reasons.append("MISSING_ALGORITHM_OUTPUTS")
        if not any(key in payload for key in ("equation", "implementation", "procedure", "graph")):
            reasons.append("MISSING_ALGORITHM_REPRESENTATION")
    elif item.kind == "REASONING_CANDIDATE":
        if not str(payload.get("name", "")).strip():
            reasons.append("MISSING_REASONING_NAME")
        if not any(key in payload for key in ("operators", "procedure", "graph")):
            reasons.append("MISSING_REASONING_PROCEDURE")
    elif item.kind == "EXPERIMENT_CANDIDATE":
        if not str(payload.get("objective", "")).strip():
            reasons.append("MISSING_EXPERIMENT_OBJECTIVE")
        if not payload.get("metrics"):
            reasons.append("MISSING_EXPERIMENT_METRICS")
    elif item.kind == "DATASET":
        if not str(payload.get("name", "")).strip():
            reasons.append("MISSING_DATASET_NAME")
        if not any(key in payload for key in ("records", "path", "content_digest", "artifact_ref")):
            reasons.append("MISSING_DATASET_CONTENT_REFERENCE")
    elif item.kind == "CLAIM":
        if not str(payload.get("statement", "")).strip():
            reasons.append("MISSING_CLAIM_STATEMENT")
    elif item.kind == "INVARIANT_CANDIDATE":
        if not str(payload.get("statement", "")).strip():
            reasons.append("MISSING_INVARIANT_STATEMENT")
    elif item.kind == "SOURCE_DOCUMENT":
        if not any(key in payload for key in ("title", "path", "content_digest", "citation")):
            reasons.append("MISSING_SOURCE_DOCUMENT_IDENTITY")
    return not reasons, tuple(reasons)


class BrainFeedProcessor:
    """Routes a bounded batch into evidence, semantic/failure knowledge, or qualification staging."""

    def __init__(self, egcf_store: Any):
        self.egcf = egcf_store
        self.feed_store = BrainFeedStore(egcf_store)
        self.semantic_store = SemanticOntologyStore(egcf_store)
        self.governance_store = KnowledgeGovernanceStore(egcf_store)

    def _process_new(
        self,
        item: BrainFeedItem,
        *,
        item_ref: str,
        source_signature: str,
        resolved: Mapping[str, BrainFeedDisposition],
    ) -> BrainFeedDisposition:
        dependency_failures = [
            dependency
            for dependency in item.depends_on
            if resolved.get(dependency) is not None and resolved[dependency].quarantined
        ]
        if dependency_failures:
            return make_brain_feed_disposition(
                item,
                status="STAGED_DEPENDENCY_REQUIRED",
                route="brain-feed-staging",
                target_refs=(item_ref,),
                reasons=tuple(f"DEPENDENCY_QUARANTINED:{value}" for value in dependency_failures),
            )

        if item.kind in {"MEASUREMENT", "EVIDENCE"}:
            evidence, reasons = _measurement_evidence(item, source_signature=source_signature)
            if evidence is None:
                return make_brain_feed_disposition(
                    item,
                    status="STAGED_EVIDENCE_METADATA_REQUIRED",
                    route="brain-feed-staging",
                    target_refs=(item_ref,),
                    reasons=reasons,
                )
            evidence_id = self.egcf.register(evidence, event_type="saa_brain_feed_evidence_registered")
            return make_brain_feed_disposition(
                item,
                status="REGISTERED_EVIDENCE",
                route="egcf-evidence",
                target_refs=(evidence_id,),
                reasons=("GROUNDED_EVIDENCE_REGISTERED",),
            )

        if item.kind == "SEMANTIC_CONCEPT":
            evidence_ids = _resolved_evidence_ids(item, resolved)
            semantic_status = str(item.payload.get("semantic_status", "UNRESOLVED_SEMANTICS")).strip().upper()
            if semantic_status != "SEMANTICALLY_RESOLVED":
                return make_brain_feed_disposition(
                    item,
                    status="STAGED_SEMANTIC_RESOLUTION_REQUIRED",
                    route="brain-feed-staging",
                    target_refs=(item_ref,),
                    reasons=(f"SEMANTIC_STATUS:{semantic_status}",),
                )
            grounded, evidence_reasons = _grounded_evidence(self.egcf, evidence_ids)
            if not grounded:
                return make_brain_feed_disposition(
                    item,
                    status="STAGED_EVIDENCE_REQUIRED",
                    route="brain-feed-staging",
                    target_refs=(item_ref,),
                    reasons=evidence_reasons or ("SEMANTIC_CONCEPT_REQUIRES_GROUNDED_EVIDENCE",),
                )
            dimension_payload = item.payload.get("physical_dimension")
            dimension = None
            if dimension_payload is not None:
                if not isinstance(dimension_payload, Sequence) or isinstance(dimension_payload, (str, bytes)):
                    raise EGCFError("semantic physical_dimension must be an array of seven integers")
                dimension = PhysicalDimensionVector(tuple(int(value) for value in dimension_payload))
            concept = make_semantic_concept(
                name=str(item.payload.get("name", "")),
                meaning=str(item.payload.get("meaning", "")),
                domain=str(item.payload.get("domain", "")),
                quantity_kind=str(item.payload.get("quantity_kind", "")),
                aliases=_strings(item.payload.get("aliases", ())),
                physical_dimension=dimension,
                canonical_unit=item.payload.get("canonical_unit"),
                evidence_ids=evidence_ids,
                semantic_status=semantic_status,
            )
            concept_id = f"semantic-concept:sha256:{concept.concept_signature}"
            try:
                self.semantic_store.load_concept(concept_id)
            except Exception:
                concept_id = self.semantic_store.admit_concept(concept)
            return make_brain_feed_disposition(
                item,
                status="ADMITTED_SEMANTIC_CONCEPT",
                route="semantic-ontology",
                target_refs=(concept_id,),
                reasons=("MEANING_AND_EVIDENCE_RESOLVED",),
            )

        if item.kind == "FAILURE":
            evidence_ids = _resolved_evidence_ids(item, resolved)
            grounded, evidence_reasons = _grounded_evidence(self.egcf, evidence_ids)
            if not grounded:
                return make_brain_feed_disposition(
                    item,
                    status="STAGED_EVIDENCE_REQUIRED",
                    route="brain-feed-staging",
                    target_refs=(item_ref,),
                    reasons=evidence_reasons or ("FAILURE_REQUIRES_GROUNDED_EVIDENCE",),
                )
            observation = make_failure_observation(
                source_kind=str(item.payload.get("source_kind", "brain-feed")),
                component=str(item.payload.get("component", "")),
                failure_class=str(item.payload.get("failure_class", "")),
                mechanism=str(item.payload.get("mechanism", "")),
                semantic_roles=_strings(item.payload.get("semantic_roles", ())),
                violated_invariants=_strings(item.payload.get("violated_invariants", ())),
                boundary_signature=str(item.payload.get("boundary_signature", "")),
                context_signature=str(item.payload.get("context_signature", "")),
                evidence_ids=evidence_ids,
                provenance_id=str(item.payload.get("provenance_id", item_ref)),
            )
            pattern_ref, occurrence_ref, repeated = self.governance_store.register_failure_observation(observation)
            reasons = ["GROUNDED_FAILURE_REGISTERED"]
            if repeated:
                reasons.append("CANONICAL_FAILURE_PATTERN_ALREADY_KNOWN")
            return make_brain_feed_disposition(
                item,
                status="REGISTERED_FAILURE",
                route="failure-algebra",
                target_refs=(pattern_ref, occurrence_ref),
                reasons=tuple(reasons),
            )

        if item.kind in STAGED_CANDIDATE_KINDS:
            valid, validation_reasons = _candidate_validation(item)
            if not valid:
                return make_brain_feed_disposition(
                    item,
                    status="QUARANTINED",
                    route="brain-feed-quarantine",
                    target_refs=(item_ref,),
                    reasons=validation_reasons,
                )
            reasons = ["QUALIFICATION_REQUIRED", "NO_CANONICAL_ALGORITHM_ADMISSION_PERFORMED"]
            if item.kind in {"ALGORITHM_CANDIDATE", "REASONING_CANDIDATE"} and not item.payload.get("meanings"):
                reasons.append("SEMANTIC_MAPPING_REQUIRED")
            evidence_ids = _resolved_evidence_ids(item, resolved)
            if not evidence_ids:
                reasons.append("EVIDENCE_LINKAGE_REQUIRED")
            return make_brain_feed_disposition(
                item,
                status=f"STAGED_{item.kind}_QUALIFICATION_REQUIRED",
                route="brain-feed-staging",
                target_refs=(item_ref,),
                reasons=tuple(reasons),
            )

        raise EGCFError(f"unsupported brain-feed route for {item.kind}")

    def process_batch(
        self,
        items: Sequence[BrainFeedItem],
        *,
        batch_id: str,
        source_signature: str,
        source_label: str = "",
        strict: bool = False,
    ) -> tuple[BrainFeedBatchReceipt, str]:
        if not items:
            raise EGCFError("brain-feed batch contains no items")
        by_id: dict[str, BrainFeedItem] = {}
        for item in items:
            if item.item_id in by_id:
                raise EGCFError(f"duplicate brain-feed item id in batch: {item.item_id}")
            by_id[item.item_id] = item
        resolved: dict[str, BrainFeedDisposition] = {}
        pending = dict(by_id)

        for item in items:
            missing = [ref for ref in (*item.depends_on, *item.evidence_from) if ref not in by_id]
            if missing:
                item_ref = self.feed_store.register_item(item)
                disposition = make_brain_feed_disposition(
                    item,
                    status="QUARANTINED",
                    route="brain-feed-quarantine",
                    target_refs=(item_ref,),
                    reasons=tuple(f"MISSING_BATCH_REFERENCE:{ref}" for ref in missing),
                )
                self.feed_store.register_disposition(disposition)
                resolved[item.item_id] = disposition
                pending.pop(item.item_id, None)

        while pending:
            progressed = False
            for item_id, item in list(pending.items()):
                required = set(item.depends_on) | set(item.evidence_from)
                if not required.issubset(resolved):
                    continue
                item_ref = self.feed_store.register_item(item)
                previous_exact = self.feed_store.disposition_for_item_signature(item.item_signature)
                if previous_exact is not None:
                    payload = previous_exact["payload"]
                    disposition = make_brain_feed_disposition(
                        item,
                        status="DUPLICATE_EXACT_ITEM",
                        route="brain-feed-deduplication",
                        target_refs=tuple(payload.get("target_refs", ())),
                        reasons=("EXACT_ITEM_ALREADY_PROCESSED",),
                        duplicate_of_item_signature=item.item_signature,
                    )
                    resolved[item_id] = disposition
                    pending.pop(item_id)
                    progressed = True
                    continue
                previous_content = self.feed_store.disposition_for_content_signature(item.content_signature)
                if previous_content is not None:
                    payload = previous_content["payload"]
                    disposition = make_brain_feed_disposition(
                        item,
                        status="DUPLICATE_CONTENT",
                        route="brain-feed-deduplication",
                        target_refs=tuple(payload.get("target_refs", ())),
                        reasons=("EQUIVALENT_CONTENT_ALREADY_PROCESSED",),
                        duplicate_of_item_signature=str(payload.get("item_signature", "")),
                    )
                    self.feed_store.register_disposition(disposition)
                    resolved[item_id] = disposition
                    pending.pop(item_id)
                    progressed = True
                    continue
                try:
                    disposition = self._process_new(
                        item,
                        item_ref=item_ref,
                        source_signature=source_signature,
                        resolved=resolved,
                    )
                except (EGCFError, ValueError, TypeError, KeyError) as exc:
                    disposition = make_brain_feed_disposition(
                        item,
                        status="QUARANTINED",
                        route="brain-feed-quarantine",
                        target_refs=(item_ref,),
                        reasons=(f"{type(exc).__name__}:{exc}",),
                    )
                self.feed_store.register_disposition(disposition)
                resolved[item_id] = disposition
                pending.pop(item_id)
                progressed = True
            if not progressed:
                for item_id, item in list(pending.items()):
                    item_ref = self.feed_store.register_item(item)
                    disposition = make_brain_feed_disposition(
                        item,
                        status="QUARANTINED",
                        route="brain-feed-quarantine",
                        target_refs=(item_ref,),
                        reasons=("CYCLIC_OR_UNRESOLVED_BATCH_DEPENDENCY",),
                    )
                    self.feed_store.register_disposition(disposition)
                    resolved[item_id] = disposition
                    pending.pop(item_id)
                break

        dispositions = tuple(resolved[item.item_id] for item in items)
        receipt = make_brain_feed_batch_receipt(
            batch_id=batch_id,
            source_signature=source_signature,
            source_label=source_label,
            strict=strict,
            dispositions=dispositions,
        )
        batch_ref = self.feed_store.register_batch(receipt)
        return receipt, batch_ref
