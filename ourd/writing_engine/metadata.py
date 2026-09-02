from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .models import BibliographicRecord, SourceDocument


def bibliographic_record_from_source(
    source: SourceDocument,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> BibliographicRecord:
    csl: dict[str, Any] = {
        "id": source.source_document_id,
        "type": "article" if source.doi else "document",
        "title": source.title,
        "author": tuple({"literal": author} for author in source.authors),
        "publisher": source.publisher,
        "edition": source.edition,
        "DOI": source.doi,
        "ISBN": source.isbn,
        "language": source.language,
    }
    if source.issued_date:
        csl["issued"] = {"raw": source.issued_date}
    provenance = {key: "source embedded metadata" for key, value in csl.items() if value}
    if overrides:
        for key, value in overrides.items():
            csl[str(key)] = value
            provenance[str(key)] = "user override"
    unresolved = tuple(
        key for key in ("title", "author", "issued") if not csl.get(key)
    )
    return BibliographicRecord(
        csl_item=tuple(csl.items()),
        source_document_ids=(source.source_document_id,),
        metadata_sources=("embedded",),
        field_provenance=tuple(provenance.items()),
        unresolved_fields=unresolved,
        verified_doi=False,
    )


def reconcile_crossref(
    record: BibliographicRecord,
    *,
    network_policy: str,
    timeout_seconds: float = 10.0,
) -> BibliographicRecord:
    csl = dict(record.csl_item)
    doi = str(csl.get("DOI") or "").strip()
    if not doi:
        return record
    if network_policy not in {"metadata-only", "explicit-retrieval"}:
        raise ValueError("Crossref reconciliation requires metadata network permission")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "oiec-stm-formal-write/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)["message"]
    conflicts = list(record.conflicts)
    provenance = dict(record.field_provenance)
    title = " ".join(payload.get("title") or ())
    if title and csl.get("title") and str(csl["title"]).strip() != title.strip():
        conflicts.append("title conflict between source metadata and Crossref")
    if title and not csl.get("title"):
        csl["title"] = title
        provenance["title"] = "Crossref"
    if payload.get("author") and not csl.get("author"):
        csl["author"] = tuple(
            {
                "family": author.get("family", ""),
                "given": author.get("given", ""),
            }
            for author in payload["author"]
        )
        provenance["author"] = "Crossref"
    return BibliographicRecord(
        csl_item=tuple(csl.items()),
        source_document_ids=record.source_document_ids,
        metadata_sources=tuple((*record.metadata_sources, "Crossref")),
        field_provenance=tuple(provenance.items()),
        conflicts=tuple(conflicts),
        unresolved_fields=tuple(key for key in ("title", "author", "issued") if not csl.get(key)),
        verified_doi=True,
    )


__all__ = ["bibliographic_record_from_source", "reconcile_crossref"]
