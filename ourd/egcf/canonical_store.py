from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Tuple

from ..persistence import atomic_write_text
from .algebra.representative_form import (
    CANONICAL_REPRESENTATIVE_VERSION,
    REPRESENTATIVE_BOUND_POLICY,
    STRUCTURAL_BINDING_POLICY,
    CanonicalRepresentativeAlgorithmForm,
)
from .algebra.semantic import (
    SemanticCandidateMeaning,
    SemanticRepresentationIssue,
    SemanticResolution,
)
from .errors import EGCFError
from .ids import canonical_json, parse_typed_id, sha256_json, typed_id, utc_now
from .models import EvidenceArtifact


CANONICAL_STORE_VERSION = "saa-canonical-algorithm-store-v1"
CANONICAL_STORE_SCHEMA_VERSION = 1
RELATION_TYPES = {
    "EQUIVALENT_TO",
    "NEAR_VARIANT_OF",
    "GENERALIZES",
    "SPECIALIZES",
    "DERIVED_FROM",
    "COMPOSED_FROM",
    "APPROXIMATES",
    "BOUNDS",
    "DECOUPLES",
    "REQUIRES",
    "LOWER_COST_THAN",
    "STRONGER_EVIDENCE_THAN",
}
EXACT_RELATION_BASES = {
    "EXACT_REPRESENTATIVE_BEHAVIOR_SIGNATURE",
    "EXACT_SAA6_DERIVATION",
    "EXACT_MATHEMATICAL_SIGNATURE_MATCH_SEMANTIC_DIFFERENCE",
    "EXACT_SEMANTIC_SIGNATURE_MATCH_MATHEMATICAL_DIFFERENCE",
}


def _fraction_payload(value: Any) -> list[int]:
    return [int(value.numerator), int(value.denominator)]


def _rational_matrix_payload(matrix: Sequence[Sequence[Any]]) -> list[list[dict[str, Any]]]:
    return [[channel.payload() for channel in row] for row in matrix]


def _canonical_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _require_sha256(value: str, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EGCFError(f"{label} must be an exact SHA-256 digest")
    return digest


def _canonical_id(behavior_signature: str) -> str:
    digest = _require_sha256(behavior_signature, "representative behavior signature")
    return f"canonical-algorithm:sha256:{digest}"


def _immutable_write(path: Path, envelope: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable canonical-store collision at {path}")
        return
    atomic_write_text(path, serialized)


@dataclass(frozen=True)
class CanonicalLookupResult:
    status: str
    exact_equivalent_ids: Tuple[str, ...]
    mathematical_match_ids: Tuple[str, ...]
    semantic_match_ids: Tuple[str, ...]
    source_bound_match_ids: Tuple[str, ...]

    @property
    def unique(self) -> bool:
        return not self.exact_equivalent_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exact_equivalent_ids": list(self.exact_equivalent_ids),
            "mathematical_match_ids": list(self.mathematical_match_ids),
            "semantic_match_ids": list(self.semantic_match_ids),
            "source_bound_match_ids": list(self.source_bound_match_ids),
            "unique": self.unique,
        }


@dataclass(frozen=True)
class CanonicalAdmissionResult:
    status: str
    canonical_id: str
    source_id: str
    store_generation: int
    lookup: CanonicalLookupResult
    relation_ids: Tuple[str, ...]

    @property
    def admitted_new(self) -> bool:
        return self.status == "ADMITTED_NEW_CANONICAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "canonical_id": self.canonical_id,
            "source_id": self.source_id,
            "store_generation": self.store_generation,
            "lookup": self.lookup.to_dict(),
            "relation_ids": list(self.relation_ids),
            "admitted_new": self.admitted_new,
        }


@dataclass(frozen=True)
class AlgorithmRelationRecord:
    relation_id: str
    relation_type: str
    source_ref: str
    source_kind: str
    target_ref: str
    target_kind: str
    basis: str
    basis_signature: str
    evidence_ids: Tuple[str, ...]
    store_generation: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "source_ref": self.source_ref,
            "source_kind": self.source_kind,
            "target_ref": self.target_ref,
            "target_kind": self.target_kind,
            "basis": self.basis,
            "basis_signature": self.basis_signature,
            "evidence_ids": list(self.evidence_ids),
            "store_generation": self.store_generation,
            "created_at": self.created_at,
        }


class CanonicalAlgorithmStore:
    """Persistent SAA-6.1..6.4 store layered over an EGCFStore.

    Canonical nodes are unique by SAA-6 representative_behavior_signature. Source
    representations and semantic qualification proofs are retained separately as
    immutable provenance and never create duplicate canonical knowledge.
    """

    def __init__(self, egcf_store: Any):
        required = ("state_root", "projection_path", "objects", "events", "get")
        if any(not hasattr(egcf_store, name) for name in required):
            raise EGCFError("CanonicalAlgorithmStore requires an EGCFStore instance")
        self.egcf_store = egcf_store
        self.state_root = Path(egcf_store.state_root)
        self.root = self.state_root / "canonical-algorithms"
        self.algorithm_root = self.root / "objects" / "sha256"
        self.source_root = self.root / "sources" / "sha256"
        self.relation_root = self.root / "relations" / "sha256"
        for path in (self.algorithm_root, self.source_root, self.relation_root):
            path.mkdir(parents=True, exist_ok=True)
        self.projection_path = Path(egcf_store.projection_path)
        self._ensure_projection()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.projection_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canonical_algorithms (
                    canonical_id TEXT PRIMARY KEY,
                    representative_behavior_signature TEXT NOT NULL UNIQUE,
                    mathematical_signature TEXT NOT NULL,
                    semantic_signature TEXT NOT NULL,
                    canonical_algorithm_signature TEXT NOT NULL,
                    representative_version TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    output_count INTEGER NOT NULL,
                    input_count INTEGER NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_algorithms_math_idx
                    ON canonical_algorithms(mathematical_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_semantic_idx
                    ON canonical_algorithms(semantic_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_outer_idx
                    ON canonical_algorithms(canonical_algorithm_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_shape_idx
                    ON canonical_algorithms(domain, output_count, input_count);

                CREATE TABLE IF NOT EXISTS canonical_algorithm_sources (
                    source_id TEXT PRIMARY KEY,
                    canonical_id TEXT NOT NULL,
                    canonical_algorithm_signature TEXT NOT NULL,
                    source_structural_hash TEXT NOT NULL,
                    source_mimo_signature TEXT NOT NULL,
                    source_normalization_signature TEXT NOT NULL,
                    representative_candidate_signature TEXT NOT NULL,
                    representative_search_audit_hash TEXT NOT NULL,
                    form_audit_hash TEXT NOT NULL,
                    proof_signature TEXT NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_sources_canonical_idx
                    ON canonical_algorithm_sources(canonical_id);
                CREATE INDEX IF NOT EXISTS canonical_sources_outer_idx
                    ON canonical_algorithm_sources(canonical_algorithm_signature);
                CREATE INDEX IF NOT EXISTS canonical_sources_structure_idx
                    ON canonical_algorithm_sources(source_structural_hash);

                CREATE TABLE IF NOT EXISTS canonical_algorithm_relations (
                    relation_id TEXT PRIMARY KEY,
                    relation_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    basis TEXT NOT NULL,
                    basis_signature TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_relations_type_idx
                    ON canonical_algorithm_relations(relation_type);
                CREATE INDEX IF NOT EXISTS canonical_relations_source_idx
                    ON canonical_algorithm_relations(source_ref);
                CREATE INDEX IF NOT EXISTS canonical_relations_target_idx
                    ON canonical_algorithm_relations(target_ref);

                CREATE TABLE IF NOT EXISTS canonical_store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            marker = connection.execute(
                "SELECT value FROM canonical_store_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if marker is None or marker[0] != str(CANONICAL_STORE_SCHEMA_VERSION):
            self.rebuild_projection()

    def _algorithm_path(self, canonical_id: str) -> Path:
        kind, digest = parse_typed_id(canonical_id)
        if kind != "canonical-algorithm":
            raise EGCFError("canonical algorithm ID has wrong type")
        return self.algorithm_root / digest[:2] / f"{digest}.json"

    def _typed_path(self, root: Path, object_id: str, expected_kind: str) -> Path:
        kind, digest = parse_typed_id(object_id)
        if kind != expected_kind:
            raise EGCFError(f"expected {expected_kind} object ID")
        return root / digest[:2] / f"{digest}.json"

    def _canonical_payload(self, form: CanonicalRepresentativeAlgorithmForm) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "store_version": CANONICAL_STORE_VERSION,
            "representative_version": form.representative_version,
            "domain": form.domain,
            "variable": form.variable,
            "output_count": form.output_count,
            "representative_input_count": form.representative_input_count,
            "normalized_sample_interval": (
                _fraction_payload(form.normalized_sample_interval)
                if form.normalized_sample_interval is not None
                else None
            ),
            "inputs": [
                {
                    "canonical_position": item.canonical_position,
                    "paired_output_index": item.paired_output_index,
                    "canonical_meaning": item.canonical_meaning,
                    "expected_output_indices": list(item.expected_output_indices),
                    "excluded_output_indices": list(item.excluded_output_indices),
                    "normalized_domain": [[0, 1], [1, 1]],
                }
                for item in form.inputs
            ],
            "normalized_channels": _rational_matrix_payload(form.normalized_channels),
            "mathematical_representative_signature": form.mathematical_representative_signature,
            "semantic_representative_signature": form.semantic_representative_signature,
            "representative_behavior_signature": form.representative_behavior_signature,
            "qualification": "EXACT_MATHEMATICS_AND_EVIDENCE_GROUNDED_RESOLVED_SEMANTICS",
        }

    def _verify_saa6_signatures(self, form: CanonicalRepresentativeAlgorithmForm) -> None:
        if not isinstance(form, CanonicalRepresentativeAlgorithmForm):
            raise EGCFError("canonical admission requires CanonicalRepresentativeAlgorithmForm")
        if form.representative_version != CANONICAL_REPRESENTATIVE_VERSION:
            raise EGCFError("unsupported SAA-6 representative version")
        if not form.canonical_admission_eligible:
            raise EGCFError("SAA-6 form is not canonical-admission eligible")
        if form.store_status != "ELIGIBLE_CANONICAL_REPRESENTATIVE_FORM":
            raise EGCFError("SAA-6 form has not reached store-eligible status")
        if form.structural_binding_policy != STRUCTURAL_BINDING_POLICY:
            raise EGCFError("unsupported SAA-6 structural binding policy")
        for label, value in (
            ("mathematical representative signature", form.mathematical_representative_signature),
            ("semantic representative signature", form.semantic_representative_signature),
            ("representative behavior signature", form.representative_behavior_signature),
            ("canonical algorithm signature", form.canonical_algorithm_signature),
            ("audit hash", form.audit_hash),
        ):
            _require_sha256(value, label)

        positions = tuple(item.canonical_position for item in form.inputs)
        if positions != tuple(range(form.representative_input_count)):
            raise EGCFError("SAA-6 canonical input positions must be contiguous")
        paired = tuple(item.paired_output_index for item in form.inputs)
        if len(set(paired)) != len(paired):
            raise EGCFError("SAA-6 paired outputs must be unique")

        for item in form.inputs:
            if item.canonical_meaning != _canonical_text(item.meaning):
                raise EGCFError("SAA-6 canonical meaning is inconsistent with resolved meaning")
            if not item.canonical_meaning:
                raise EGCFError("SAA-6 canonical meaning cannot be empty")
            boundary = item.boundary
            if boundary.bound_policy != REPRESENTATIVE_BOUND_POLICY:
                raise EGCFError("unsupported representative boundary policy")
            if boundary.raw_width != boundary.raw_maximum - boundary.raw_minimum:
                raise EGCFError("representative boundary width mismatch")
            if boundary.raw_width <= 0 or boundary.normalized_minimum != 0 or boundary.normalized_maximum != 1:
                raise EGCFError("representative boundary is not a positive exact [0,1] normalization")
            boundary_material = {
                "schema_version": 1,
                "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
                "candidate_input_index": boundary.candidate_input_index,
                "raw_minimum": _fraction_payload(boundary.raw_minimum),
                "raw_maximum": _fraction_payload(boundary.raw_maximum),
                "target": [[0, 1], [1, 1]],
                "bound_policy": REPRESENTATIVE_BOUND_POLICY,
                "source_normalization_signature": boundary.source_normalization_signature,
                "semantic_resolution_signature": boundary.semantic_resolution_signature,
            }
            if sha256_json(boundary_material) != boundary.boundary_signature:
                raise EGCFError("representative boundary signature mismatch")

        mathematical_payload = {
            "schema_version": 1,
            "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
            "claim_scope": "EXACT_MINIMAL_DECOUPLED_RENORMALIZED_REPRESENTATIVE_DYNAMICS",
            "domain": form.domain,
            "variable": form.variable,
            "output_count": form.output_count,
            "representative_input_count": form.representative_input_count,
            "normalized_sample_interval": (
                _fraction_payload(form.normalized_sample_interval)
                if form.normalized_sample_interval is not None
                else None
            ),
            "target_input_domain": [0, 1],
            "input_order_policy": "ORDER_BY_UNIQUE_PAIRED_OUTPUT",
            "normalized_channels": _rational_matrix_payload(form.normalized_channels),
        }
        mathematical_signature = sha256_json(mathematical_payload)
        if mathematical_signature != form.mathematical_representative_signature:
            raise EGCFError("SAA-6 mathematical representative signature mismatch")

        semantic_payload = {
            "schema_version": 1,
            "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
            "claim_scope": "RESOLVED_REPRESENTATIVE_INPUT_SEMANTICS",
            "inputs": [
                {
                    "canonical_position": item.canonical_position,
                    "paired_output_index": item.paired_output_index,
                    "meaning": item.canonical_meaning,
                    "expected_output_indices": list(item.expected_output_indices),
                    "excluded_output_indices": list(item.excluded_output_indices),
                }
                for item in form.inputs
            ],
        }
        semantic_signature = sha256_json(semantic_payload)
        if semantic_signature != form.semantic_representative_signature:
            raise EGCFError("SAA-6 semantic representative signature mismatch")

        behavior_signature = sha256_json(
            {
                "schema_version": 1,
                "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
                "claim_scope": "CANONICAL_REPRESENTATIVE_BEHAVIOR_AND_SEMANTICS",
                "mathematical_representative_signature": mathematical_signature,
                "semantic_representative_signature": semantic_signature,
            }
        )
        if behavior_signature != form.representative_behavior_signature:
            raise EGCFError("SAA-6 representative behavior signature mismatch")

        algorithm_signature = sha256_json(
            {
                "schema_version": 1,
                "representative_version": CANONICAL_REPRESENTATIVE_VERSION,
                "claim_scope": "CANONICAL_REPRESENTATIVE_ALGORITHM_WITH_CONSERVATIVE_SOURCE_STRUCTURE",
                "representative_behavior_signature": behavior_signature,
                "source_structural_hash": form.source_structural_hash,
                "source_structural_strength": form.source_structural_strength,
                "structural_binding_policy": STRUCTURAL_BINDING_POLICY,
            }
        )
        if algorithm_signature != form.canonical_algorithm_signature:
            raise EGCFError("SAA-6 canonical algorithm signature mismatch")

    def _grounded_evidence(self, evidence_id: str) -> EvidenceArtifact:
        try:
            record = self.egcf_store.get(evidence_id)
        except Exception as exc:
            raise EGCFError(f"canonical semantic evidence is not registered: {evidence_id}") from exc
        if not isinstance(record, EvidenceArtifact):
            raise EGCFError("canonical semantic evidence ID does not reference EvidenceArtifact")
        if record.success is not True or record.simulated:
            raise EGCFError("canonical semantic evidence must be successful and non-simulated")
        if not record.producer.startswith(("deterministic-", "human-")):
            raise EGCFError("canonical semantic evidence must come from deterministic or human grounding")
        if record.method == "reported":
            raise EGCFError("reported-only evidence cannot ground canonical semantics")
        return record

    def _verify_semantic_proof(
        self,
        form: CanonicalRepresentativeAlgorithmForm,
        issues: Sequence[SemanticRepresentationIssue],
        candidates: Sequence[SemanticCandidateMeaning],
        resolutions: Sequence[SemanticResolution],
    ) -> str:
        if form.representative_input_count == 0:
            if issues or candidates or resolutions:
                raise EGCFError("zero-input canonical form must not carry representative semantic issues")
            return sha256_json({"schema_version": 1, "proof": "ZERO_INPUT_VACUOUS_SEMANTICS"})

        issue_by_index: dict[int, SemanticRepresentationIssue] = {}
        for issue in issues:
            if issue.coordinate_kind != "REPRESENTATIVE_INPUT":
                raise EGCFError("canonical semantic proof must describe representative inputs")
            if issue.coordinate_index in issue_by_index:
                raise EGCFError("duplicate representative semantic issue")
            issue_by_index[issue.coordinate_index] = issue
        if set(issue_by_index) != set(range(form.representative_input_count)):
            raise EGCFError("canonical admission requires one semantic issue per representative input")

        candidate_by_issue: dict[str, SemanticCandidateMeaning] = {}
        for candidate in candidates:
            if candidate.issue_id in candidate_by_issue:
                raise EGCFError("duplicate semantic candidate for one issue")
            candidate_by_issue[candidate.issue_id] = candidate
        resolution_by_issue: dict[str, SemanticResolution] = {}
        for resolution in resolutions:
            if resolution.issue_id in resolution_by_issue:
                raise EGCFError("duplicate semantic resolution for one issue")
            resolution_by_issue[resolution.issue_id] = resolution

        proof_rows: list[dict[str, Any]] = []
        for form_input in form.inputs:
            issue = issue_by_index[form_input.candidate_input_index]
            candidate = candidate_by_issue.get(issue.issue_id)
            resolution = resolution_by_issue.get(issue.issue_id)
            if candidate is None or resolution is None:
                raise EGCFError("canonical admission is missing semantic candidate or resolution")
            if candidate.candidate_id != form_input.semantic_candidate_id:
                raise EGCFError("stored semantic candidate ID differs from SAA-6 form")
            if candidate.signature != form_input.semantic_candidate_signature:
                raise EGCFError("stored semantic candidate signature differs from SAA-6 form")
            if resolution.candidate_id != candidate.candidate_id:
                raise EGCFError("semantic resolution targets a different candidate")
            if resolution.resolution_signature != form_input.semantic_resolution_signature:
                raise EGCFError("semantic resolution signature differs from SAA-6 form")
            if resolution.status != "SEMANTICALLY_RESOLVED":
                raise EGCFError("canonical admission requires SEMANTICALLY_RESOLVED meaning")
            if not resolution.canonical_semantic_eligible or not resolution.independent_review:
                raise EGCFError("canonical semantic proof requires independent reviewed eligibility")
            if resolution.semantic_fit_bp != 10000:
                raise EGCFError("canonical semantic proof requires complete output-footprint fit")
            if _canonical_text(candidate.meaning) != form_input.canonical_meaning:
                raise EGCFError("semantic candidate meaning differs from SAA-6 canonical meaning")
            if candidate.expected_output_indices != form_input.expected_output_indices:
                raise EGCFError("semantic expected outputs differ from SAA-6 form")
            if candidate.excluded_output_indices != form_input.excluded_output_indices:
                raise EGCFError("semantic excluded outputs differ from SAA-6 form")
            if tuple(sorted(resolution.evidence_ids)) != tuple(sorted(form_input.semantic_evidence_ids)):
                raise EGCFError("semantic evidence IDs differ from SAA-6 form")
            if not resolution.evidence_ids:
                raise EGCFError("canonical semantics require grounded evidence")

            by_falsifier = {result.falsifier: result for result in resolution.falsifier_results}
            if any(
                falsifier not in by_falsifier or by_falsifier[falsifier].outcome != "SURVIVED"
                for falsifier in candidate.falsifiers
            ):
                raise EGCFError("all declared semantic falsifiers must have survived")
            grounded_ids = []
            for evidence_id in resolution.evidence_ids:
                self._grounded_evidence(evidence_id)
                grounded_ids.append(evidence_id)
            for falsifier in candidate.falsifiers:
                result = by_falsifier[falsifier]
                if result.evidence_id:
                    self._grounded_evidence(result.evidence_id)

            proof_rows.append(
                {
                    "coordinate": form_input.canonical_position,
                    "issue_signature": issue.signature,
                    "candidate_signature": candidate.signature,
                    "resolution_signature": resolution.resolution_signature,
                    "evidence_ids": sorted(grounded_ids),
                    "falsifiers": [result.to_dict() for result in resolution.falsifier_results],
                    "independent_review": True,
                }
            )
        return sha256_json(
            {
                "schema_version": 1,
                "store_version": CANONICAL_STORE_VERSION,
                "representative_behavior_signature": form.representative_behavior_signature,
                "semantic_proof": proof_rows,
            }
        )

    def lookup(self, form: CanonicalRepresentativeAlgorithmForm) -> CanonicalLookupResult:
        self._ensure_projection()
        self._verify_saa6_signatures(form)
        with self._connect() as connection:
            exact = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT canonical_id FROM canonical_algorithms "
                    "WHERE representative_behavior_signature = ? ORDER BY canonical_id",
                    (form.representative_behavior_signature,),
                ).fetchall()
            )
            math_matches = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT canonical_id FROM canonical_algorithms WHERE mathematical_signature = ? "
                    "AND representative_behavior_signature != ? ORDER BY canonical_id",
                    (form.mathematical_representative_signature, form.representative_behavior_signature),
                ).fetchall()
            )
            semantic_matches = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT canonical_id FROM canonical_algorithms WHERE semantic_signature = ? "
                    "AND representative_behavior_signature != ? ORDER BY canonical_id",
                    (form.semantic_representative_signature, form.representative_behavior_signature),
                ).fetchall()
            )
            outer_matches = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT canonical_id FROM canonical_algorithms WHERE canonical_algorithm_signature = ? "
                    "ORDER BY canonical_id",
                    (form.canonical_algorithm_signature,),
                ).fetchall()
            )
        if exact:
            status = "REPRESENTATIVE_EQUIVALENT_ALREADY_STORED"
        elif math_matches and semantic_matches:
            status = "MULTIPLE_CANONICAL_NEIGHBOR_MATCHES"
        elif math_matches:
            status = "MATHEMATICAL_MATCH_SEMANTIC_DIFFERENCE"
        elif semantic_matches:
            status = "SEMANTIC_MATCH_MATHEMATICAL_DIFFERENCE"
        else:
            status = "UNIQUE_CANONICAL_CANDIDATE"
        return CanonicalLookupResult(
            status=status,
            exact_equivalent_ids=exact,
            mathematical_match_ids=math_matches,
            semantic_match_ids=semantic_matches,
            source_bound_match_ids=outer_matches,
        )

    def current_generation(self) -> int:
        self._ensure_projection()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(store_generation), 0) FROM canonical_algorithms"
            ).fetchone()
        return int(row[0] if row else 0)

    def _source_payload(
        self,
        form: CanonicalRepresentativeAlgorithmForm,
        canonical_id: str,
        proof_signature: str,
        generation: int,
        created_at: str,
    ) -> tuple[str, dict[str, Any]]:
        identity = {
            "canonical_id": canonical_id,
            "canonical_algorithm_signature": form.canonical_algorithm_signature,
            "source_structural_hash": form.source_structural_hash,
            "source_mimo_signature": form.source_mimo_signature,
            "source_normalization_signature": form.source_normalization_signature,
            "representative_candidate_signature": form.representative_candidate_signature,
            "representative_search_audit_hash": form.representative_search_audit_hash,
            "form_audit_hash": form.audit_hash,
            "proof_signature": proof_signature,
        }
        source_id = typed_id("algorithm-source", identity)
        payload = {
            "schema_version": 1,
            "store_version": CANONICAL_STORE_VERSION,
            **identity,
            "store_generation": generation,
            "created_at": created_at,
            "form": form.to_dict(),
        }
        return source_id, payload

    def _persist_source(self, source_id: str, payload: Mapping[str, Any]) -> None:
        path = self._typed_path(self.source_root, source_id, "algorithm-source")
        envelope = {
            "schema_version": 1,
            "object_type": "algorithm-source",
            "object_id": source_id,
            "payload": dict(payload),
        }
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_algorithm_sources("
                "source_id, canonical_id, canonical_algorithm_signature, source_structural_hash, "
                "source_mimo_signature, source_normalization_signature, representative_candidate_signature, "
                "representative_search_audit_hash, form_audit_hash, proof_signature, store_generation, "
                "payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    payload["canonical_id"],
                    payload["canonical_algorithm_signature"],
                    payload["source_structural_hash"],
                    payload["source_mimo_signature"],
                    payload["source_normalization_signature"],
                    payload["representative_candidate_signature"],
                    payload["representative_search_audit_hash"],
                    payload["form_audit_hash"],
                    payload["proof_signature"],
                    payload["store_generation"],
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    payload["created_at"],
                ),
            )

    def _persist_canonical(
        self,
        form: CanonicalRepresentativeAlgorithmForm,
        canonical_id: str,
        source_id: str,
        generation: int,
        created_at: str,
    ) -> None:
        canonical_payload = self._canonical_payload(form)
        path = self._algorithm_path(canonical_id)
        envelope = {
            "schema_version": 1,
            "object_type": "canonical-algorithm",
            "object_id": canonical_id,
            "store_version": CANONICAL_STORE_VERSION,
            "store_generation": generation,
            "created_at": created_at,
            "anchor_source_id": source_id,
            "payload": canonical_payload,
        }
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_algorithms("
                "canonical_id, representative_behavior_signature, mathematical_signature, semantic_signature, "
                "canonical_algorithm_signature, representative_version, domain, output_count, input_count, "
                "store_generation, payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    canonical_id,
                    form.representative_behavior_signature,
                    form.mathematical_representative_signature,
                    form.semantic_representative_signature,
                    form.canonical_algorithm_signature,
                    form.representative_version,
                    form.domain,
                    form.output_count,
                    form.representative_input_count,
                    generation,
                    canonical_json(canonical_payload),
                    str(path.relative_to(self.state_root)),
                    created_at,
                ),
            )

    def _verify_relation_evidence(self, evidence_ids: Sequence[str]) -> Tuple[str, ...]:
        result = tuple(dict.fromkeys(str(value).strip() for value in evidence_ids if str(value).strip()))
        for evidence_id in result:
            self._grounded_evidence(evidence_id)
        return result

    def _relation(
        self,
        *,
        relation_type: str,
        source_ref: str,
        source_kind: str,
        target_ref: str,
        target_kind: str,
        basis: str,
        basis_signature: str,
        evidence_ids: Sequence[str],
        generation: int,
    ) -> AlgorithmRelationRecord:
        relation = str(relation_type).strip().upper()
        if relation not in RELATION_TYPES:
            raise EGCFError(f"unsupported canonical algorithm relation: {relation_type!r}")
        basis_text = " ".join(str(basis).strip().split())
        if not basis_text:
            raise EGCFError("algorithm relation requires a non-empty basis")
        basis_digest = _require_sha256(basis_signature, "relation basis signature")
        evidence = tuple(dict.fromkeys(evidence_ids))
        identity_source = source_ref
        identity_target = target_ref
        if relation == "NEAR_VARIANT_OF" and identity_target < identity_source:
            identity_source, identity_target = identity_target, identity_source
            source_kind, target_kind = target_kind, source_kind
        identity = {
            "relation_type": relation,
            "source_ref": identity_source,
            "source_kind": source_kind,
            "target_ref": identity_target,
            "target_kind": target_kind,
            "basis": basis_text,
            "basis_signature": basis_digest,
            "evidence_ids": list(sorted(evidence)),
        }
        relation_id = typed_id("algorithm-relation", identity)
        return AlgorithmRelationRecord(
            relation_id=relation_id,
            relation_type=relation,
            source_ref=identity_source,
            source_kind=source_kind,
            target_ref=identity_target,
            target_kind=target_kind,
            basis=basis_text,
            basis_signature=basis_digest,
            evidence_ids=tuple(sorted(evidence)),
            store_generation=generation,
            created_at=utc_now(),
        )

    def _persist_relation(self, relation: AlgorithmRelationRecord) -> str:
        path = self._typed_path(self.relation_root, relation.relation_id, "algorithm-relation")
        payload = relation.to_dict()
        envelope = {
            "schema_version": 1,
            "object_type": "algorithm-relation",
            "object_id": relation.relation_id,
            "payload": payload,
        }
        _immutable_write(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_algorithm_relations("
                "relation_id, relation_type, source_ref, source_kind, target_ref, target_kind, basis, "
                "basis_signature, evidence_json, store_generation, payload_json, path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    relation.relation_id,
                    relation.relation_type,
                    relation.source_ref,
                    relation.source_kind,
                    relation.target_ref,
                    relation.target_kind,
                    relation.basis,
                    relation.basis_signature,
                    canonical_json(list(relation.evidence_ids)),
                    relation.store_generation,
                    canonical_json(payload),
                    str(path.relative_to(self.state_root)),
                    relation.created_at,
                ),
            )
        return relation.relation_id

    def _append_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        event = self.egcf_store.events.append(event_type, dict(payload))
        indexer = getattr(self.egcf_store, "_index_event", None)
        if callable(indexer):
            indexer(event)

    def admit(
        self,
        form: CanonicalRepresentativeAlgorithmForm,
        *,
        semantic_issues: Sequence[SemanticRepresentationIssue] = (),
        semantic_candidates: Sequence[SemanticCandidateMeaning] = (),
        semantic_resolutions: Sequence[SemanticResolution] = (),
    ) -> CanonicalAdmissionResult:
        self._ensure_projection()
        self._verify_saa6_signatures(form)
        proof_signature = self._verify_semantic_proof(
            form, semantic_issues, semantic_candidates, semantic_resolutions
        )
        lookup = self.lookup(form)
        created_at = utc_now()

        if lookup.exact_equivalent_ids:
            canonical_id = lookup.exact_equivalent_ids[0]
            generation = self._generation_for(canonical_id)
            source_id, source_payload = self._source_payload(
                form, canonical_id, proof_signature, generation, created_at
            )
            self._persist_source(source_id, source_payload)
            relation = self._relation(
                relation_type="EQUIVALENT_TO",
                source_ref=source_id,
                source_kind="SOURCE_REPRESENTATION",
                target_ref=canonical_id,
                target_kind="CANONICAL_ALGORITHM",
                basis="EXACT_REPRESENTATIVE_BEHAVIOR_SIGNATURE",
                basis_signature=form.representative_behavior_signature,
                evidence_ids=(),
                generation=generation,
            )
            relation_id = self._persist_relation(relation)
            self._append_event(
                "saa_canonical_equivalence_reused",
                {
                    "canonical_id": canonical_id,
                    "source_id": source_id,
                    "relation_id": relation_id,
                    "representative_behavior_signature": form.representative_behavior_signature,
                },
            )
            return CanonicalAdmissionResult(
                status="REUSED_EQUIVALENT_CANONICAL",
                canonical_id=canonical_id,
                source_id=source_id,
                store_generation=generation,
                lookup=lookup,
                relation_ids=(relation_id,),
            )

        generation = self.current_generation() + 1
        canonical_id = _canonical_id(form.representative_behavior_signature)
        source_id, source_payload = self._source_payload(
            form, canonical_id, proof_signature, generation, created_at
        )
        self._persist_canonical(form, canonical_id, source_id, generation, created_at)
        self._persist_source(source_id, source_payload)
        relation_ids: list[str] = []

        derived_relation = self._relation(
            relation_type="DERIVED_FROM",
            source_ref=canonical_id,
            source_kind="CANONICAL_ALGORITHM",
            target_ref=source_id,
            target_kind="SOURCE_REPRESENTATION",
            basis="EXACT_SAA6_DERIVATION",
            basis_signature=form.audit_hash,
            evidence_ids=(),
            generation=generation,
        )
        relation_ids.append(self._persist_relation(derived_relation))

        for neighbor_id in lookup.mathematical_match_ids:
            relation = self._relation(
                relation_type="NEAR_VARIANT_OF",
                source_ref=canonical_id,
                source_kind="CANONICAL_ALGORITHM",
                target_ref=neighbor_id,
                target_kind="CANONICAL_ALGORITHM",
                basis="EXACT_MATHEMATICAL_SIGNATURE_MATCH_SEMANTIC_DIFFERENCE",
                basis_signature=form.mathematical_representative_signature,
                evidence_ids=(),
                generation=generation,
            )
            relation_ids.append(self._persist_relation(relation))
        for neighbor_id in lookup.semantic_match_ids:
            relation = self._relation(
                relation_type="NEAR_VARIANT_OF",
                source_ref=canonical_id,
                source_kind="CANONICAL_ALGORITHM",
                target_ref=neighbor_id,
                target_kind="CANONICAL_ALGORITHM",
                basis="EXACT_SEMANTIC_SIGNATURE_MATCH_MATHEMATICAL_DIFFERENCE",
                basis_signature=form.semantic_representative_signature,
                evidence_ids=(),
                generation=generation,
            )
            relation_ids.append(self._persist_relation(relation))

        self._append_event(
            "saa_canonical_algorithm_admitted",
            {
                "canonical_id": canonical_id,
                "source_id": source_id,
                "store_generation": generation,
                "representative_behavior_signature": form.representative_behavior_signature,
                "mathematical_signature": form.mathematical_representative_signature,
                "semantic_signature": form.semantic_representative_signature,
                "relation_ids": relation_ids,
            },
        )
        return CanonicalAdmissionResult(
            status="ADMITTED_NEW_CANONICAL",
            canonical_id=canonical_id,
            source_id=source_id,
            store_generation=generation,
            lookup=lookup,
            relation_ids=tuple(relation_ids),
        )

    def _generation_for(self, canonical_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT store_generation FROM canonical_algorithms WHERE canonical_id = ?",
                (canonical_id,),
            ).fetchone()
        if row is None:
            raise EGCFError(f"unknown canonical algorithm: {canonical_id}")
        return int(row[0])

    def get(self, canonical_id: str) -> dict[str, Any]:
        self._ensure_projection()
        path = self._algorithm_path(canonical_id)
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read canonical algorithm {canonical_id}: {exc}") from exc
        if envelope.get("object_id") != canonical_id:
            raise EGCFError("canonical algorithm object identity mismatch")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise EGCFError("canonical algorithm payload is invalid")
        if payload.get("representative_behavior_signature") != parse_typed_id(canonical_id)[1]:
            raise EGCFError("canonical algorithm behavior signature does not match object ID")
        return envelope

    def list(self) -> list[dict[str, Any]]:
        self._ensure_projection()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT canonical_id, representative_behavior_signature, mathematical_signature, "
                "semantic_signature, canonical_algorithm_signature, representative_version, domain, "
                "output_count, input_count, store_generation, payload_json, path, created_at "
                "FROM canonical_algorithms ORDER BY store_generation, canonical_id"
            ).fetchall()
        return [
            {
                "canonical_id": row[0],
                "representative_behavior_signature": row[1],
                "mathematical_signature": row[2],
                "semantic_signature": row[3],
                "canonical_algorithm_signature": row[4],
                "representative_version": row[5],
                "domain": row[6],
                "output_count": row[7],
                "input_count": row[8],
                "store_generation": row[9],
                "payload": json.loads(row[10]),
                "path": row[11],
                "created_at": row[12],
            }
            for row in rows
        ]

    def sources(self, canonical_id: str | None = None) -> list[dict[str, Any]]:
        self._ensure_projection()
        query = "SELECT payload_json FROM canonical_algorithm_sources"
        parameters: tuple[Any, ...] = ()
        if canonical_id is not None:
            query += " WHERE canonical_id = ?"
            parameters = (canonical_id,)
        query += " ORDER BY source_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [json.loads(row[0]) for row in rows]

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        *,
        basis: str,
        evidence_ids: Sequence[str],
    ) -> str:
        self._ensure_projection()
        relation = str(relation_type).strip().upper()
        if relation in {"EQUIVALENT_TO", "NEAR_VARIANT_OF", "DERIVED_FROM"}:
            raise EGCFError(
                f"{relation} is derived by SAA canonicalization and cannot be manually asserted"
            )
        self.get(source_id)
        self.get(target_id)
        evidence = self._verify_relation_evidence(evidence_ids)
        if not evidence:
            raise EGCFError("non-derived algorithm relations require grounded evidence")
        basis_signature = sha256_json(
            {
                "schema_version": 1,
                "store_version": CANONICAL_STORE_VERSION,
                "relation_type": relation,
                "source_id": source_id,
                "target_id": target_id,
                "basis": " ".join(str(basis).strip().split()),
                "evidence_ids": list(sorted(evidence)),
            }
        )
        record = self._relation(
            relation_type=relation,
            source_ref=source_id,
            source_kind="CANONICAL_ALGORITHM",
            target_ref=target_id,
            target_kind="CANONICAL_ALGORITHM",
            basis=basis,
            basis_signature=basis_signature,
            evidence_ids=evidence,
            generation=self.current_generation(),
        )
        relation_id = self._persist_relation(record)
        self._append_event(
            "saa_algorithm_relation_registered",
            {"relation_id": relation_id, **record.to_dict()},
        )
        return relation_id

    def relations(
        self,
        ref: str | None = None,
        *,
        relation_type: str | None = None,
    ) -> list[AlgorithmRelationRecord]:
        self._ensure_projection()
        clauses: list[str] = []
        parameters: list[Any] = []
        if ref is not None:
            clauses.append("(source_ref = ? OR target_ref = ?)")
            parameters.extend([ref, ref])
        if relation_type is not None:
            relation = str(relation_type).strip().upper()
            if relation not in RELATION_TYPES:
                raise EGCFError(f"unsupported canonical algorithm relation: {relation_type!r}")
            clauses.append("relation_type = ?")
            parameters.append(relation)
        query = "SELECT payload_json FROM canonical_algorithm_relations"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY relation_type, relation_id"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row[0])
            result.append(
                AlgorithmRelationRecord(
                    relation_id=payload["relation_id"],
                    relation_type=payload["relation_type"],
                    source_ref=payload["source_ref"],
                    source_kind=payload["source_kind"],
                    target_ref=payload["target_ref"],
                    target_kind=payload["target_kind"],
                    basis=payload["basis"],
                    basis_signature=payload["basis_signature"],
                    evidence_ids=tuple(payload["evidence_ids"]),
                    store_generation=int(payload["store_generation"]),
                    created_at=payload["created_at"],
                )
            )
        return result

    def neighbors(self, canonical_id: str) -> list[dict[str, Any]]:
        self.get(canonical_id)
        result = []
        for relation in self.relations(canonical_id):
            other = relation.target_ref if relation.source_ref == canonical_id else relation.source_ref
            result.append(
                {
                    "neighbor_ref": other,
                    "relation_type": relation.relation_type,
                    "relation_id": relation.relation_id,
                    "basis": relation.basis,
                    "evidence_ids": list(relation.evidence_ids),
                }
            )
        return result

    def rebuild_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS canonical_algorithms (
                    canonical_id TEXT PRIMARY KEY,
                    representative_behavior_signature TEXT NOT NULL UNIQUE,
                    mathematical_signature TEXT NOT NULL,
                    semantic_signature TEXT NOT NULL,
                    canonical_algorithm_signature TEXT NOT NULL,
                    representative_version TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    output_count INTEGER NOT NULL,
                    input_count INTEGER NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_algorithms_math_idx ON canonical_algorithms(mathematical_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_semantic_idx ON canonical_algorithms(semantic_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_outer_idx ON canonical_algorithms(canonical_algorithm_signature);
                CREATE INDEX IF NOT EXISTS canonical_algorithms_shape_idx ON canonical_algorithms(domain, output_count, input_count);
                CREATE TABLE IF NOT EXISTS canonical_algorithm_sources (
                    source_id TEXT PRIMARY KEY,
                    canonical_id TEXT NOT NULL,
                    canonical_algorithm_signature TEXT NOT NULL,
                    source_structural_hash TEXT NOT NULL,
                    source_mimo_signature TEXT NOT NULL,
                    source_normalization_signature TEXT NOT NULL,
                    representative_candidate_signature TEXT NOT NULL,
                    representative_search_audit_hash TEXT NOT NULL,
                    form_audit_hash TEXT NOT NULL,
                    proof_signature TEXT NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_sources_canonical_idx ON canonical_algorithm_sources(canonical_id);
                CREATE INDEX IF NOT EXISTS canonical_sources_outer_idx ON canonical_algorithm_sources(canonical_algorithm_signature);
                CREATE INDEX IF NOT EXISTS canonical_sources_structure_idx ON canonical_algorithm_sources(source_structural_hash);
                CREATE TABLE IF NOT EXISTS canonical_algorithm_relations (
                    relation_id TEXT PRIMARY KEY,
                    relation_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    basis TEXT NOT NULL,
                    basis_signature TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    store_generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS canonical_relations_type_idx ON canonical_algorithm_relations(relation_type);
                CREATE INDEX IF NOT EXISTS canonical_relations_source_idx ON canonical_algorithm_relations(source_ref);
                CREATE INDEX IF NOT EXISTS canonical_relations_target_idx ON canonical_algorithm_relations(target_ref);
                CREATE TABLE IF NOT EXISTS canonical_store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                DELETE FROM canonical_algorithms;
                DELETE FROM canonical_algorithm_sources;
                DELETE FROM canonical_algorithm_relations;
                DELETE FROM canonical_store_metadata;
                """
            )
            for path in sorted(self.algorithm_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                canonical_id = envelope["object_id"]
                if payload["representative_behavior_signature"] != parse_typed_id(canonical_id)[1]:
                    raise EGCFError(f"invalid canonical algorithm entry: {path}")
                connection.execute(
                    "INSERT INTO canonical_algorithms(canonical_id, representative_behavior_signature, "
                    "mathematical_signature, semantic_signature, canonical_algorithm_signature, representative_version, "
                    "domain, output_count, input_count, store_generation, payload_json, path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        canonical_id,
                        payload["representative_behavior_signature"],
                        payload["mathematical_representative_signature"],
                        payload["semantic_representative_signature"],
                        envelope.get("canonical_algorithm_signature", payload.get("canonical_algorithm_signature", "")),
                        payload["representative_version"],
                        payload["domain"],
                        payload["output_count"],
                        payload["representative_input_count"],
                        envelope["store_generation"],
                        canonical_json(payload),
                        str(path.relative_to(self.state_root)),
                        envelope["created_at"],
                    ),
                )
            for path in sorted(self.source_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO canonical_algorithm_sources(source_id, canonical_id, canonical_algorithm_signature, "
                    "source_structural_hash, source_mimo_signature, source_normalization_signature, "
                    "representative_candidate_signature, representative_search_audit_hash, form_audit_hash, proof_signature, "
                    "store_generation, payload_json, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope["object_id"], payload["canonical_id"], payload["canonical_algorithm_signature"],
                        payload["source_structural_hash"], payload["source_mimo_signature"],
                        payload["source_normalization_signature"], payload["representative_candidate_signature"],
                        payload["representative_search_audit_hash"], payload["form_audit_hash"], payload["proof_signature"],
                        payload["store_generation"], canonical_json(payload), str(path.relative_to(self.state_root)),
                        payload["created_at"],
                    ),
                )
            for path in sorted(self.relation_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO canonical_algorithm_relations(relation_id, relation_type, source_ref, source_kind, "
                    "target_ref, target_kind, basis, basis_signature, evidence_json, store_generation, payload_json, path, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["relation_id"], payload["relation_type"], payload["source_ref"], payload["source_kind"],
                        payload["target_ref"], payload["target_kind"], payload["basis"], payload["basis_signature"],
                        canonical_json(payload["evidence_ids"]), payload["store_generation"], canonical_json(payload),
                        str(path.relative_to(self.state_root)), payload["created_at"],
                    ),
                )
            connection.execute(
                "INSERT INTO canonical_store_metadata(key, value) VALUES ('schema_version', ?)",
                (str(CANONICAL_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO canonical_store_metadata(key, value) VALUES ('rebuilt_at', ?)",
                (utc_now(),),
            )
