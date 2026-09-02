from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..persistence import atomic_write_text
from ..workspace import Workspace
from .ingestion import ingest_source
from .models import (
    ExtractedSource,
    PageRecord,
    SourceDocument,
    TextBlock,
    TextLine,
    TextWord,
)


class SourceRegistry:
    def __init__(self, workspace: Workspace, state_dir: Path | None = None):
        self.workspace = workspace
        self.root = (state_dir or workspace.root / workspace.internal_name) / "writing" / "sources"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"

    def _index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"sources": {}, "paths": {}}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict[str, Any]) -> None:
        atomic_write_text(self.index_path, json.dumps(index, indent=2, sort_keys=True) + "\n")

    def register(
        self,
        path: str,
        *,
        allow_ocr: bool = False,
        ocr_language: str = "eng",
        license_or_access_note: str = "",
    ) -> ExtractedSource:
        extracted = ingest_source(
            self.workspace,
            path,
            allow_ocr=allow_ocr,
            ocr_language=ocr_language,
            license_or_access_note=license_or_access_note,
        )
        target = self.root / f"{extracted.extraction_signature}.json"
        atomic_write_text(target, json.dumps(asdict(extracted), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        index = self._index()
        source_id = extracted.document.source_document_id
        signatures = list(index["sources"].get(source_id, ()))
        if extracted.extraction_signature not in signatures:
            signatures.append(extracted.extraction_signature)
        index["sources"][source_id] = sorted(signatures)
        index["paths"][extracted.document.workspace_relative_path] = extracted.extraction_signature
        self._save_index(index)
        return extracted

    @staticmethod
    def _load_page(payload: dict[str, Any]) -> PageRecord:
        values = dict(payload)
        values["blocks"] = tuple(TextBlock(**item) for item in values.get("blocks", ()))
        values["lines"] = tuple(TextLine(**item) for item in values.get("lines", ()))
        values["words"] = tuple(TextWord(**item) for item in values.get("words", ()))
        return PageRecord(**values)

    def _load_signature(self, extraction_signature: str) -> ExtractedSource:
        payload = json.loads((self.root / f"{extraction_signature}.json").read_text(encoding="utf-8"))
        document_values = dict(payload["document"])
        document_values.pop("signature", None)
        document_values["authors"] = tuple(document_values.get("authors", ()))
        document_values["page_label_map"] = tuple(tuple(item) for item in document_values.get("page_label_map", ()))
        document_values["metadata_provenance"] = tuple(tuple(item) for item in document_values.get("metadata_provenance", ()))
        return ExtractedSource(
            document=SourceDocument(**document_values),
            document_text=payload["document_text"],
            pages=tuple(self._load_page(item) for item in payload.get("pages", ())),
            section_offsets=tuple(tuple(item) for item in payload.get("section_offsets", ())),
            paragraph_offsets=tuple(tuple(item) for item in payload.get("paragraph_offsets", ())),
        )

    def load(self, source_document_id: str) -> ExtractedSource:
        signatures = self._index()["sources"].get(source_document_id, ())
        if not signatures:
            raise KeyError(source_document_id)
        return self._load_signature(signatures[-1])

    def load_path(self, path: str) -> ExtractedSource:
        canonical = self.workspace.canonical(path)
        extraction_signature = self._index()["paths"].get(canonical)
        if not extraction_signature:
            raise KeyError(canonical)
        return self._load_signature(extraction_signature)

    def list_documents(self) -> tuple[SourceDocument, ...]:
        index = self._index()
        documents = []
        for source_id in sorted(index["sources"]):
            documents.append(self.load(source_id).document)
        return tuple(documents)

    def refresh(self, path: str, **kwargs: Any) -> ExtractedSource:
        return self.register(path, **kwargs)

    def retire_path(self, path: str) -> None:
        canonical = self.workspace.canonical(path)
        index = self._index()
        index["paths"].pop(canonical, None)
        self._save_index(index)


__all__ = ["SourceRegistry"]
