from __future__ import annotations

from typing import Mapping, Sequence

from .models import BibliographicRecord, CitationUse


def _author_label(csl: Mapping[str, object]) -> str:
    authors = csl.get("author")
    if isinstance(authors, (list, tuple)) and authors:
        first = authors[0]
        if isinstance(first, Mapping):
            return str(first.get("family") or first.get("literal") or "Anonymous")
    return "Anonymous"


def _year(csl: Mapping[str, object]) -> str:
    issued = csl.get("issued")
    if isinstance(issued, Mapping):
        raw = str(issued.get("raw") or "")
        return raw[:4] if raw[:4].isdigit() else "n.d."
    return "n.d."


def render_citation(
    records: Sequence[BibliographicRecord],
    locator: str,
    *,
    style: str = "author-date",
    numeric_index: int = 1,
) -> str:
    if not records:
        raise ValueError("citation rendering requires a bibliographic record")
    style_key = style.casefold()
    if style_key in {"numeric", "vancouver", "ieee"}:
        return f"[{numeric_index}]" + (f", {locator}" if locator else "")
    labels = []
    for record in records:
        csl = dict(record.csl_item)
        labels.append(f"{_author_label(csl)}, {_year(csl)}")
    return "(" + "; ".join(labels) + (f", {locator}" if locator else "") + ")"


def render_bibliography_entry(record: BibliographicRecord, *, style: str = "author-date") -> str:
    csl = dict(record.csl_item)
    author = _author_label(csl)
    year = _year(csl)
    title = str(csl.get("title") or "[Untitled]")
    publisher = str(csl.get("publisher") or "")
    doi = str(csl.get("DOI") or "")
    suffix = f" {publisher}." if publisher else ""
    if doi:
        suffix += f" doi:{doi}"
    return f"{author}. ({year}). {title}.{suffix}".strip()


def render_bibliography(records: Sequence[BibliographicRecord], *, style: str = "author-date") -> str:
    return "\n".join(
        render_bibliography_entry(record, style=style)
        for record in sorted(records, key=lambda item: render_bibliography_entry(item, style=style).casefold())
    )


__all__ = ["render_bibliography", "render_bibliography_entry", "render_citation"]
