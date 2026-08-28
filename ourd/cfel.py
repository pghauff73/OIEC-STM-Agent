from __future__ import annotations

import hashlib
import json
import uuid
from typing import List

from .errors import PolicyError
from .models import CollisionRecord, RuntimeState, SCORE_SCALE
from .persistence import utc_now


def fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def record_collision(
    state: RuntimeState,
    *,
    action_id: str,
    expected: str,
    observed: str,
    objects: List[str],
    boundary: str,
    active_dimension: str,
    frozen_dimensions: List[str],
    evidence_ids: List[str],
    proposed_correction: str = "",
    falsifier: str = "",
    disposition: str = "recorded",
    collision_fingerprint: str = "",
    severity_bp: int = 0,
    attempt_key: str = "",
    boundary_signature: str = "",
    dimension_signature: str = "",
) -> CollisionRecord:
    severity_bp = int(severity_bp)
    if not 0 <= severity_bp <= SCORE_SCALE:
        raise PolicyError("collision severity must be 0..10000")
    collision_fingerprint = collision_fingerprint or fingerprint(
        {
            "action_id": action_id,
            "expected": expected,
            "observed": observed,
            "objects": objects,
            "boundary": boundary,
            "active_dimension": active_dimension,
        }
    )
    retry_identity = attempt_key or collision_fingerprint
    retry_count = state.failed_attempts.get(retry_identity, 0)
    if not attempt_key or severity_bp >= SCORE_SCALE // 2:
        retry_count += 1
        state.failed_attempts[retry_identity] = retry_count
    record = CollisionRecord(
        collision_id=str(uuid.uuid4()),
        timestamp=utc_now(),
        action_id=action_id,
        expected=expected,
        observed=observed,
        objects=objects,
        boundary=boundary,
        active_dimension=active_dimension,
        frozen_dimensions=frozen_dimensions,
        evidence_ids=evidence_ids,
        proposed_correction=proposed_correction,
        falsifier=falsifier,
        retry_count=retry_count,
        disposition=disposition,
        fingerprint=collision_fingerprint,
        severity_bp=severity_bp,
        attempt_key=attempt_key,
        boundary_signature=boundary_signature,
        dimension_signature=dimension_signature,
    )
    state.collisions.append(record)
    return record
