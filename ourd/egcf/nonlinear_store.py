from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from ..persistence import WorkspaceLock, atomic_write_text
from .algebra.nonlinear_evidence import GovernedJetEvidence
from .algebra.nonlinear_search import CanonicalNonlinearRepresentativeForm
from .algebra.nonlinear_stability import SemanticStabilityAssessment
from .errors import EGCFError
from .ids import canonical_json, sha256_json, utc_now


NONLINEAR_STORE_VERSION = "saa-local-nonlinear-store-v1"
NONLINEAR_STORE_SCHEMA_VERSION = 1


def _digest_path(root: Path, signature: str) -> Path:
    if len(signature) != 64 or any(character not in "0123456789abcdef" for character in signature):
        raise EGCFError("nonlinear store identity must be a SHA-256 signature")
    return root / signature[:2] / f"{signature}.json"


def _write_immutable(path: Path, envelope: dict[str, Any]) -> bool:
    serialized = json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EGCFError(f"cannot read immutable nonlinear store object {path}: {exc}") from exc
        if canonical_json(existing) != canonical_json(envelope):
            raise EGCFError(f"immutable nonlinear object collision at {path}")
        return False
    atomic_write_text(path, serialized)
    return True


def _local_behavior_signature(form: CanonicalNonlinearRepresentativeForm) -> str:
    return sha256_json(
        {
            "schema_version": 1,
            "representation_version": form.representation_version,
            "parent_representative_behavior_signature": form.parent_representative_behavior_signature,
            "transformed_jet_coefficient_signature": form.transformed_jet.coefficient_signature,
            "transformed_jet_scope_signature": form.transformed_jet.scope_signature,
            "semantic_signature": form.semantic_signature,
        }
    )


class NonlinearCanonicalStore:
    """Persistent local nonlinear knowledge that is intentionally separate from global SAA-6 identity."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.state_root = self.workspace_root / ".ourd-agent" / "egcf" / "nonlinear-canonical"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.local_root = self.state_root / "local" / "sha256"
        self.evidence_root = self.state_root / "evidence" / "sha256"
        self.regional_root = self.state_root / "regional" / "sha256"
        for path in (self.local_root, self.evidence_root, self.regional_root):
            path.mkdir(parents=True, exist_ok=True)
        self.lock = WorkspaceLock(self.state_root / "lock")
        self.lock.acquire()
        self.projection_path = self.state_root / "projection.sqlite3"
        self._ensure_projection()
        self._rebuild_if_needed()

    def close(self) -> None:
        self.lock.close()

    def __enter__(self) -> "NonlinearCanonicalStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.projection_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_projection(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS local_forms (
                    local_id TEXT PRIMARY KEY,
                    parent_signature TEXT NOT NULL,
                    local_behavior_signature TEXT NOT NULL UNIQUE,
                    semantic_signature TEXT NOT NULL,
                    source_jet_signature TEXT NOT NULL,
                    coefficient_signature TEXT NOT NULL,
                    scope_signature TEXT NOT NULL,
                    center_json TEXT NOT NULL,
                    radius_json TEXT NOT NULL,
                    jet_order INTEGER NOT NULL,
                    generation INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS local_parent_idx ON local_forms(parent_signature);
                CREATE INDEX IF NOT EXISTS local_semantic_idx ON local_forms(semantic_signature);
                CREATE INDEX IF NOT EXISTS local_source_jet_idx ON local_forms(source_jet_signature);
                CREATE INDEX IF NOT EXISTS local_coeff_idx ON local_forms(coefficient_signature);
                CREATE INDEX IF NOT EXISTS local_scope_idx ON local_forms(scope_signature);

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_signature TEXT PRIMARY KEY,
                    evidence_kind TEXT NOT NULL,
                    exact INTEGER NOT NULL,
                    canonical_local_eligible INTEGER NOT NULL,
                    source_snapshot_hash TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS local_evidence (
                    local_id TEXT NOT NULL,
                    evidence_signature TEXT NOT NULL,
                    PRIMARY KEY(local_id, evidence_signature)
                );
                CREATE INDEX IF NOT EXISTS local_evidence_sig_idx ON local_evidence(evidence_signature);

                CREATE TABLE IF NOT EXISTS regional_assessments (
                    assessment_signature TEXT PRIMARY KEY,
                    parent_signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    observation_count INTEGER NOT NULL,
                    regional_semantic_eligible INTEGER NOT NULL,
                    generation INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS regional_parent_idx ON regional_assessments(parent_signature);
                CREATE INDEX IF NOT EXISTS regional_status_idx ON regional_assessments(status);

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def _rebuild_if_needed(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("SELECT COUNT(*) FROM local_forms").fetchone()
        except sqlite3.DatabaseError:
            self.rebuild_projection()

    def _generation(self, table: str) -> int:
        if table not in {"local_forms", "regional_assessments"}:
            raise EGCFError("unsupported nonlinear store generation table")
        with self._connect() as connection:
            row = connection.execute(f"SELECT MAX(generation) FROM {table}").fetchone()
        return int(row[0] or 0)

    def _validate_local_admission(
        self,
        form: CanonicalNonlinearRepresentativeForm,
        evidence: GovernedJetEvidence,
    ) -> None:
        if not isinstance(form, CanonicalNonlinearRepresentativeForm):
            raise EGCFError("SAA-7.4 requires CanonicalNonlinearRepresentativeForm")
        if not form.local_canonical_eligible:
            raise EGCFError("SAA-7.4 refuses non-qualified local nonlinear forms")
        if form.global_equivalence_eligible:
            raise EGCFError("SAA-7.4 local store refuses objects claiming global nonlinear equivalence")
        if form.store_status != "ELIGIBLE_LOCAL_NONLINEAR_REPRESENTATIVE_FORM":
            raise EGCFError("SAA-7.4 form does not carry local nonlinear admission status")
        if _local_behavior_signature(form) != form.local_representative_behavior_signature:
            raise EGCFError("SAA-7.4 local nonlinear behavior signature failed revalidation")
        if not isinstance(evidence, GovernedJetEvidence):
            raise EGCFError("SAA-7.4 requires governed SAA-7.2 jet evidence")
        if not evidence.exact or not evidence.canonical_local_eligible or evidence.jet is None:
            raise EGCFError("SAA-7.4 exact canonical local admission requires exact qualified evidence")
        if evidence.parent_representative_behavior_signature != form.parent_representative_behavior_signature:
            raise EGCFError("SAA-7.4 evidence belongs to a different SAA-6 parent")
        if evidence.jet.local_behavior_signature != form.source_jet_signature:
            raise EGCFError("SAA-7.4 evidence does not ground the source jet used by the local form")
        if evidence.evidence_kind not in {"EXACT_SYMBOLIC_POLYNOMIAL", "EXACT_DERIVATIVE_TABLE"}:
            raise EGCFError("SAA-7.4 exact store admission does not accept this evidence kind")

    def admit_local(
        self,
        form: CanonicalNonlinearRepresentativeForm,
        evidence: GovernedJetEvidence,
    ) -> dict[str, Any]:
        self._validate_local_admission(form, evidence)
        local_signature = form.local_representative_behavior_signature
        local_id = f"local-nonlinear:sha256:{local_signature}"
        evidence_path = _digest_path(self.evidence_root, evidence.evidence_signature)
        now = utc_now()
        evidence_envelope = {
            "schema_version": NONLINEAR_STORE_SCHEMA_VERSION,
            "store_version": NONLINEAR_STORE_VERSION,
            "object_type": "nonlinear-evidence",
            "object_id": f"nonlinear-evidence:sha256:{evidence.evidence_signature}",
            "created_at": now,
            "payload": evidence.to_dict(),
        }
        _write_immutable(evidence_path, evidence_envelope)

        local_path = _digest_path(self.local_root, local_signature)
        existed = local_path.exists()
        generation = self._generation("local_forms") if existed else self._generation("local_forms") + 1
        local_envelope = {
            "schema_version": NONLINEAR_STORE_SCHEMA_VERSION,
            "store_version": NONLINEAR_STORE_VERSION,
            "object_type": "local-nonlinear-canonical-form",
            "object_id": local_id,
            "store_generation": generation,
            "created_at": now,
            "payload": form.to_dict(),
        }
        _write_immutable(local_path, local_envelope)

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO evidence(evidence_signature, evidence_kind, exact, canonical_local_eligible, "
                "source_snapshot_hash, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence.evidence_signature,
                    evidence.evidence_kind,
                    int(evidence.exact),
                    int(evidence.canonical_local_eligible),
                    evidence.source_snapshot_hash,
                    str(evidence_path.relative_to(self.state_root)),
                    now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO local_forms(local_id, parent_signature, local_behavior_signature, semantic_signature, "
                "source_jet_signature, coefficient_signature, scope_signature, center_json, radius_json, jet_order, "
                "generation, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    local_id,
                    form.parent_representative_behavior_signature,
                    local_signature,
                    form.semantic_signature,
                    form.source_jet_signature,
                    form.transformed_jet.coefficient_signature,
                    form.transformed_jet.scope_signature,
                    canonical_json([[value.numerator, value.denominator] for value in form.transformed_jet.center]),
                    canonical_json([[value.numerator, value.denominator] for value in form.transformed_jet.validity_radius]),
                    form.transformed_jet.order,
                    generation,
                    str(local_path.relative_to(self.state_root)),
                    now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO local_evidence(local_id, evidence_signature) VALUES (?, ?)",
                (local_id, evidence.evidence_signature),
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('local_generation', ?)",
                (str(max(generation, self._generation("local_forms"))),),
            )
        return {
            "status": "REUSED_LOCAL_NONLINEAR_FORM" if existed else "ADMITTED_NEW_LOCAL_NONLINEAR_FORM",
            "local_id": local_id,
            "local_behavior_signature": local_signature,
            "generation": generation,
            "evidence_signature": evidence.evidence_signature,
        }

    def admit_regional_stability(
        self,
        assessment: SemanticStabilityAssessment,
    ) -> dict[str, Any]:
        if not isinstance(assessment, SemanticStabilityAssessment):
            raise EGCFError("SAA-7.4 regional admission requires SemanticStabilityAssessment")
        if not assessment.regional_semantic_eligible:
            raise EGCFError("SAA-7.4 refuses unresolved or transition-bearing regional semantics")
        if assessment.status != "REGIONALLY_STABLE_SEMANTICS":
            raise EGCFError("SAA-7.4 only persists qualified regionally stable semantic claims")
        known = set(self.local_signatures(assessment.parent_representative_behavior_signature))
        if not set(assessment.local_behavior_signatures).issubset(known):
            raise EGCFError("SAA-7.4 regional assessment references local forms not admitted to this store")
        signature = assessment.assessment_signature
        path = _digest_path(self.regional_root, signature)
        existed = path.exists()
        generation = self._generation("regional_assessments") if existed else self._generation("regional_assessments") + 1
        now = utc_now()
        envelope = {
            "schema_version": NONLINEAR_STORE_SCHEMA_VERSION,
            "store_version": NONLINEAR_STORE_VERSION,
            "object_type": "regional-nonlinear-semantics",
            "object_id": f"regional-semantics:sha256:{signature}",
            "store_generation": generation,
            "created_at": now,
            "payload": assessment.to_dict(),
        }
        _write_immutable(path, envelope)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO regional_assessments(assessment_signature, parent_signature, status, "
                "observation_count, regional_semantic_eligible, generation, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signature,
                    assessment.parent_representative_behavior_signature,
                    assessment.status,
                    assessment.observation_count,
                    int(assessment.regional_semantic_eligible),
                    generation,
                    str(path.relative_to(self.state_root)),
                    now,
                ),
            )
        return {
            "status": "REUSED_REGIONAL_SEMANTIC_ASSESSMENT" if existed else "ADMITTED_REGIONAL_SEMANTIC_ASSESSMENT",
            "assessment_signature": signature,
            "generation": generation,
        }

    def local_signatures(self, parent_signature: str | None = None) -> list[str]:
        query = "SELECT local_behavior_signature FROM local_forms"
        parameters: tuple[Any, ...] = ()
        if parent_signature is not None:
            query += " WHERE parent_signature = ?"
            parameters = (parent_signature,)
        query += " ORDER BY local_behavior_signature"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [str(row[0]) for row in rows]

    def list_local(self, parent_signature: str | None = None) -> list[dict[str, Any]]:
        signatures = self.local_signatures(parent_signature)
        result: list[dict[str, Any]] = []
        for signature in signatures:
            path = _digest_path(self.local_root, signature)
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def evidence_for_local(self, local_behavior_signature: str) -> list[str]:
        local_id = f"local-nonlinear:sha256:{local_behavior_signature}"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT evidence_signature FROM local_evidence WHERE local_id = ? ORDER BY evidence_signature",
                (local_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def list_regional(self, parent_signature: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT assessment_signature FROM regional_assessments"
        parameters: tuple[Any, ...] = ()
        if parent_signature is not None:
            query += " WHERE parent_signature = ?"
            parameters = (parent_signature,)
        query += " ORDER BY assessment_signature"
        with self._connect() as connection:
            signatures = [str(row[0]) for row in connection.execute(query, parameters).fetchall()]
        return [
            json.loads(_digest_path(self.regional_root, signature).read_text(encoding="utf-8"))
            for signature in signatures
        ]

    def rebuild_projection(self) -> None:
        if self.projection_path.exists():
            self.projection_path.unlink()
        self._ensure_projection()
        with self._connect() as connection:
            for path in sorted(self.local_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                local_signature = str(payload["local_representative_behavior_signature"])
                jet = payload["transformed_jet"]
                connection.execute(
                    "INSERT INTO local_forms(local_id, parent_signature, local_behavior_signature, semantic_signature, "
                    "source_jet_signature, coefficient_signature, scope_signature, center_json, radius_json, jet_order, "
                    "generation, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope["object_id"],
                        payload["parent_representative_behavior_signature"],
                        local_signature,
                        payload["semantic_signature"],
                        payload["source_jet_signature"],
                        jet["coefficient_signature"],
                        jet["scope_signature"],
                        canonical_json(jet["center"]),
                        canonical_json(jet["validity_radius"]),
                        int(jet["order"]),
                        int(envelope.get("store_generation", 0)),
                        str(path.relative_to(self.state_root)),
                        envelope.get("created_at", ""),
                    ),
                )
            for path in sorted(self.evidence_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                signature = str(payload["evidence_signature"])
                connection.execute(
                    "INSERT INTO evidence(evidence_signature, evidence_kind, exact, canonical_local_eligible, "
                    "source_snapshot_hash, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        signature,
                        payload["evidence_kind"],
                        int(bool(payload["exact"])),
                        int(bool(payload["canonical_local_eligible"])),
                        payload["source_snapshot_hash"],
                        str(path.relative_to(self.state_root)),
                        envelope.get("created_at", ""),
                    ),
                )
            # Evidence links are intentionally recoverable from exact source-jet identity.
            evidence_rows = connection.execute(
                "SELECT evidence_signature, path FROM evidence WHERE exact = 1 AND canonical_local_eligible = 1"
            ).fetchall()
            for evidence_signature, evidence_path in evidence_rows:
                evidence_envelope = json.loads((self.state_root / evidence_path).read_text(encoding="utf-8"))
                jet_payload = evidence_envelope["payload"].get("jet")
                if not jet_payload:
                    continue
                source_jet_signature = jet_payload["local_behavior_signature"]
                local_rows = connection.execute(
                    "SELECT local_id FROM local_forms WHERE source_jet_signature = ?",
                    (source_jet_signature,),
                ).fetchall()
                for (local_id,) in local_rows:
                    connection.execute(
                        "INSERT OR IGNORE INTO local_evidence(local_id, evidence_signature) VALUES (?, ?)",
                        (local_id, evidence_signature),
                    )
            for path in sorted(self.regional_root.glob("*/*.json")):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope["payload"]
                connection.execute(
                    "INSERT INTO regional_assessments(assessment_signature, parent_signature, status, observation_count, "
                    "regional_semantic_eligible, generation, path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["assessment_signature"],
                        payload["parent_representative_behavior_signature"],
                        payload["status"],
                        int(payload["observation_count"]),
                        int(bool(payload["regional_semantic_eligible"])),
                        int(envelope.get("store_generation", 0)),
                        str(path.relative_to(self.state_root)),
                        envelope.get("created_at", ""),
                    ),
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('rebuilt_at', ?)",
                (utc_now(),),
            )
