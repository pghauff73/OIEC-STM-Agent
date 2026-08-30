from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json


BRAIN_FEED_VERSION = "saa-batch-brain-feed-v1"
BRAIN_FEED_SCHEMA_VERSION = 1
MAX_BRAIN_FEED_ITEMS = 4096
BRAIN_FEED_KINDS = {
    "MEASUREMENT",
    "EVIDENCE",
    "SEMANTIC_CONCEPT",
    "ALGORITHM_CANDIDATE",
    "REASONING_CANDIDATE",
    "EXPERIMENT_CANDIDATE",
    "FAILURE",
    "DATASET",
    "CLAIM",
    "INVARIANT_CANDIDATE",
    "SOURCE_DOCUMENT",
}

ADMITTED_STATUSES = {
    "REGISTERED_EVIDENCE",
    "ADMITTED_SEMANTIC_CONCEPT",
    "REGISTERED_FAILURE",
}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _refs(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value)}))


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EGCFError("brain-feed item payload must be a JSON object")
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True)
class BrainFeedItem:
    item_id: str
    kind: str
    payload: dict[str, Any]
    depends_on: Tuple[str, ...]
    evidence_from: Tuple[str, ...]
    source_path: str
    content_signature: str
    item_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "payload": self.payload,
            "depends_on": list(self.depends_on),
            "evidence_from": list(self.evidence_from),
            "source_path": self.source_path,
            "content_signature": self.content_signature,
            "item_signature": self.item_signature,
        }


@dataclass(frozen=True)
class BrainFeedDisposition:
    item_id: str
    item_signature: str
    content_signature: str
    kind: str
    status: str
    route: str
    target_refs: Tuple[str, ...]
    reasons: Tuple[str, ...]
    duplicate_of_item_signature: str
    canonical_algorithm_admission_attempted: bool
    disposition_signature: str

    @property
    def quarantined(self) -> bool:
        return self.status == "QUARANTINED"

    @property
    def staged(self) -> bool:
        return self.status.startswith("STAGED_")

    @property
    def admitted(self) -> bool:
        return self.status in ADMITTED_STATUSES

    @property
    def duplicate(self) -> bool:
        return self.status.startswith("DUPLICATE_")

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_signature": self.item_signature,
            "content_signature": self.content_signature,
            "kind": self.kind,
            "status": self.status,
            "route": self.route,
            "target_refs": list(self.target_refs),
            "reasons": list(self.reasons),
            "duplicate_of_item_signature": self.duplicate_of_item_signature,
            "canonical_algorithm_admission_attempted": self.canonical_algorithm_admission_attempted,
            "disposition_signature": self.disposition_signature,
            "quarantined": self.quarantined,
            "staged": self.staged,
            "admitted": self.admitted,
            "duplicate": self.duplicate,
        }


@dataclass(frozen=True)
class BrainFeedBatchReceipt:
    batch_id: str
    source_signature: str
    source_label: str
    strict: bool
    item_count: int
    admitted_count: int
    staged_count: int
    quarantined_count: int
    duplicate_count: int
    dispositions: Tuple[BrainFeedDisposition, ...]
    status: str
    canonical_algorithm_admissions: int
    batch_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_signature": self.source_signature,
            "source_label": self.source_label,
            "strict": self.strict,
            "item_count": self.item_count,
            "admitted_count": self.admitted_count,
            "staged_count": self.staged_count,
            "quarantined_count": self.quarantined_count,
            "duplicate_count": self.duplicate_count,
            "dispositions": [item.to_dict() for item in self.dispositions],
            "status": self.status,
            "canonical_algorithm_admissions": self.canonical_algorithm_admissions,
            "batch_signature": self.batch_signature,
        }


def make_brain_feed_item(
    *,
    item_id: str,
    kind: str,
    payload: Mapping[str, Any],
    depends_on: Sequence[str] = (),
    evidence_from: Sequence[str] = (),
    source_path: str = "",
) -> BrainFeedItem:
    identifier = _text(item_id)
    canonical_kind = str(kind).strip().upper()
    if not identifier:
        raise EGCFError("brain-feed item requires a non-empty id")
    if canonical_kind not in BRAIN_FEED_KINDS:
        raise EGCFError(f"unsupported brain-feed item kind: {canonical_kind}")
    material_payload = _payload(payload)
    dependencies = _refs(depends_on)
    evidence_links = _refs(evidence_from)
    content_material = {
        "version": BRAIN_FEED_VERSION,
        "kind": canonical_kind,
        "payload": material_payload,
        "depends_on": list(dependencies),
        "evidence_from": list(evidence_links),
    }
    content_signature = sha256_json(content_material)
    item_signature = sha256_json(
        {
            **content_material,
            "item_id": identifier,
        }
    )
    return BrainFeedItem(
        item_id=identifier,
        kind=canonical_kind,
        payload=material_payload,
        depends_on=dependencies,
        evidence_from=evidence_links,
        source_path=str(source_path).strip(),
        content_signature=content_signature,
        item_signature=item_signature,
    )


def make_brain_feed_disposition(
    item: BrainFeedItem,
    *,
    status: str,
    route: str,
    target_refs: Sequence[str] = (),
    reasons: Sequence[str] = (),
    duplicate_of_item_signature: str = "",
) -> BrainFeedDisposition:
    canonical_status = str(status).strip().upper()
    canonical_route = str(route).strip()
    targets = _refs(target_refs)
    reason_values = _refs(reasons)
    duplicate_of = str(duplicate_of_item_signature).strip()
    material = {
        "version": BRAIN_FEED_VERSION,
        "item_signature": item.item_signature,
        "status": canonical_status,
        "route": canonical_route,
        "target_refs": list(targets),
        "reasons": list(reason_values),
        "duplicate_of_item_signature": duplicate_of,
        "canonical_algorithm_admission_attempted": False,
    }
    return BrainFeedDisposition(
        item_id=item.item_id,
        item_signature=item.item_signature,
        content_signature=item.content_signature,
        kind=item.kind,
        status=canonical_status,
        route=canonical_route,
        target_refs=targets,
        reasons=reason_values,
        duplicate_of_item_signature=duplicate_of,
        canonical_algorithm_admission_attempted=False,
        disposition_signature=sha256_json(material),
    )


def make_brain_feed_batch_receipt(
    *,
    batch_id: str,
    source_signature: str,
    source_label: str,
    strict: bool,
    dispositions: Sequence[BrainFeedDisposition],
) -> BrainFeedBatchReceipt:
    identifier = _text(batch_id)
    source = str(source_signature).strip().lower()
    if not identifier:
        raise EGCFError("brain-feed batch requires a batch_id")
    if len(source) != 64 or any(character not in "0123456789abcdef" for character in source):
        raise EGCFError("brain-feed source_signature must be SHA-256")
    items = tuple(dispositions)
    admitted = sum(item.admitted for item in items)
    staged = sum(item.staged for item in items)
    quarantined = sum(item.quarantined for item in items)
    duplicates = sum(item.duplicate for item in items)
    status = "BRAIN_FEED_BATCH_ACCEPTED"
    if quarantined:
        status = "BRAIN_FEED_BATCH_PARTIAL_WITH_QUARANTINE"
    if strict and quarantined:
        status = "BRAIN_FEED_BATCH_STRICT_FAILURE"
    material = {
        "version": BRAIN_FEED_VERSION,
        "batch_id": identifier,
        "source_signature": source,
        "source_label": str(source_label).strip(),
        "strict": bool(strict),
        "disposition_signatures": [item.disposition_signature for item in items],
        "status": status,
        "canonical_algorithm_admissions": 0,
    }
    return BrainFeedBatchReceipt(
        batch_id=identifier,
        source_signature=source,
        source_label=str(source_label).strip(),
        strict=bool(strict),
        item_count=len(items),
        admitted_count=admitted,
        staged_count=staged,
        quarantined_count=quarantined,
        duplicate_count=duplicates,
        dispositions=items,
        status=status,
        canonical_algorithm_admissions=0,
        batch_signature=sha256_json(material),
    )
