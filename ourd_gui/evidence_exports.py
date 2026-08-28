from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable

from .governance_models import build_evidence_dashboard
from .read_models import ReadOnlyEGCFRepository
from .redaction import safe_projection


def _export_payload(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> dict:
    requested_ids = tuple(dict.fromkeys(str(item) for item in identifiers if item))
    dashboard = build_evidence_dashboard(repository, requested_ids)
    records = []
    for identifier in dashboard.evidence_ids:
        try:
            envelope = repository.get_envelope(identifier)
        except (OSError, ValueError, KeyError) as exc:
            records.append(
                {
                    "object_id": identifier,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        records.append(safe_projection(envelope))
    return {
        "schema_version": 1,
        "authoritative": False,
        "export_kind": "evidence-dashboard-view",
        "current_source_snapshot_hash": repository.source_snapshot(),
        "requested_ids": list(requested_ids),
        "dashboard": safe_projection(asdict(dashboard)),
        "records": records,
    }


def evidence_json(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> str:
    return json.dumps(
        _export_payload(repository, identifiers),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"


def evidence_markdown(
    repository: ReadOnlyEGCFRepository,
    identifiers: Iterable[str],
) -> str:
    payload = _export_payload(repository, identifiers)
    dashboard = payload["dashboard"]
    lines = [
        "# Evidence Dashboard Export",
        "",
        "**Authority:** non-authoritative GUI view  ",
        f"**Current source snapshot:** `{payload['current_source_snapshot_hash']}`  ",
        f"**Verdict:** `{dashboard['verdict']}`",
        "",
        "## Coverage",
        "",
    ]
    for dimension in dashboard["dimensions"]:
        coverage = dimension["coverage"]
        rendered = "unknown" if coverage is None else f"{float(coverage) * 100:.1f}%"
        lines.append(
            f"- `{dimension['code']}` {dimension['name']}: {rendered} "
            f"({dimension['covered']}/{dimension['total']})"
        )
    for heading, key in (
        ("Blocking Gaps", "blocking_gaps"),
        ("Known Unknowns", "known_unknowns"),
        ("Conflicts", "conflicts"),
    ):
        lines.extend(["", f"## {heading}", ""])
        lines.extend(f"- {item}" for item in dashboard[key] or ["None"])
    lines.extend(["", "## Evidence Records", ""])
    for record in payload["records"]:
        object_id = record.get("object_id", "unknown")
        if "error" in record:
            lines.append(f"- `{object_id}`: unresolved - {record['error']}")
            continue
        record_payload = record.get("payload", {})
        lines.append(
            f"- `{object_id}`: category `{record_payload.get('category', 'unknown')}`, "
            f"source snapshot `{record_payload.get('source_snapshot_hash', 'unknown')}`, "
            f"content hash `{record_payload.get('sha256', 'unknown')}`"
        )
        for limitation in record_payload.get("limitations", []):
            lines.append(f"  - Limitation: {limitation}")
    return "\n".join(lines) + "\n"
