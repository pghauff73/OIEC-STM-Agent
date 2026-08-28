from __future__ import annotations

import html
import json

from ourd.egcf.models import AssuranceCase

from .redaction import safe_projection


def _payload(case: AssuranceCase) -> dict:
    return safe_projection(case)


def assurance_json(case: AssuranceCase) -> str:
    return json.dumps(
        {"object_id": case.object_id, "payload": _payload(case)},
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"


def assurance_markdown(case: AssuranceCase) -> str:
    payload = _payload(case)
    lines = [
        f"# Assurance Record: `{case.object_id}`",
        "",
        f"**Subject:** `{payload['subject_id']}`  ",
        f"**Conclusion:** `{payload['conclusion']}`  ",
        f"**Created:** `{payload['created_at']}`",
        "",
        "## Top Claim",
        "",
        str(payload["top_claim"]),
        "",
        "## Subclaims",
        "",
    ]
    lines.extend(
        f"- {'PASS' if item.get('status') else 'FAIL'}: {item.get('claim', '')}"
        for item in payload["subclaims"]
    )
    lines.extend(["", "## Gaps", ""])
    lines.extend(f"- {item}" for item in payload["gaps"] or ["None"])
    lines.extend(["", "## Conflicts", ""])
    lines.extend(f"- {item}" for item in payload["conflicts"] or ["None"])
    lines.extend(["", "## Supporting Evidence", ""])
    lines.extend(f"- `{item}`" for item in payload["supporting_evidence"] or ["None"])
    lines.extend(["", "## Uncertainties", ""])
    lines.extend(f"- {item}" for item in payload["uncertainties"] or ["None"])
    return "\n".join(lines) + "\n"


def assurance_html(case: AssuranceCase) -> str:
    markdown = assurance_markdown(case)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>OURD Assurance Record</title>"
        "<style>body{font:16px system-ui;max-width:980px;margin:2rem auto;padding:0 1rem;}"
        "pre{white-space:pre-wrap;background:#f4f4f4;padding:1rem;border-radius:8px;}</style>"
        "</head><body><h1>OURD Assurance Record</h1><pre>"
        + html.escape(markdown)
        + "</pre></body></html>\n"
    )
