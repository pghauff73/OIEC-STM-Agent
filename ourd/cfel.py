from __future__ import annotations

import hashlib
import json
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
    occurrence = 1 + sum(
        existing.fingerprint == collision_fingerprint for existing in state.collisions
    )
    collision_id = f"collision:{fingerprint({'fingerprint': collision_fingerprint, 'retry_identity': retry_identity, 'retry_count': retry_count, 'occurrence': occurrence})}"
    record = CollisionRecord(
        collision_id=collision_id,
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
    if (
        severity_bp > 0
        and state.reasoning_problem is not None
        and state.reasoning_hypothesis_pool
    ):
        from .reasoning import apply_collision_update, build_hypothesis_set

        hypothesis_state = state.reasoning_hypothesis_state
        if hypothesis_state is None:
            maximum = max(1, len(state.reasoning_hypothesis_pool))
            if state.dimension_budget is not None:
                maximum = max(maximum, state.dimension_budget.max_active_hypotheses)
            hypothesis_state = build_hypothesis_set(
                tuple(state.reasoning_hypothesis_pool.values()),
                problem_id=state.reasoning_problem.problem_id,
                max_hypotheses=maximum,
                mutually_exclusive=state.reasoning_problem.mutually_exclusive_hypotheses,
            )
        revised, updates = apply_collision_update(
            hypothesis_state,
            objects=objects,
            falsifier=falsifier,
            evidence_ids=evidence_ids,
            collision_id=record.collision_id,
            severity_bp=severity_bp,
        )
        if revised.signature != hypothesis_state.signature:
            state.set_reasoning_hypothesis_state(revised)
            existing_updates = {
                item.update_id for item in state.reasoning_hypothesis_updates
            }
            state.reasoning_hypothesis_updates.extend(
                item for item in updates if item.update_id not in existing_updates
            )
            state.reasoning_candidates = None
            state.reasoning_topology = None
            state.last_reasoning_certificate = None
            state.reasoning_transition_index += 1
    return record
