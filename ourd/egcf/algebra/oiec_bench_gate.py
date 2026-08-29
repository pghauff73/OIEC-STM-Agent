from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ..errors import EGCFError
from ..ids import sha256_json
from ..models import EvidenceArtifact


OIEC_BENCH_GATE_VERSION = "saa-oiec-bench-gate-v1"
OIEC_BENCH_TRACKS = (
    "TRUTHGROUND",
    "MEANINGPATH",
    "SEMANTICREP",
    "MEANINGGROUND",
    "WORKGROUND",
    "PROGRESSCERT",
    "AGENTWORK",
)


def _bp(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
        raise EGCFError(f"{label} must be integer basis points in 0..10000")
    return int(value)


@dataclass(frozen=True)
class OIECBenchGatePolicy:
    minimum_track_scores: Tuple[Tuple[str, int], ...]
    minimum_independence_groups: int = 2

    def canonical(self) -> "OIECBenchGatePolicy":
        supplied = {str(name).strip().upper(): _bp(score, f"benchmark threshold {name}") for name, score in self.minimum_track_scores}
        if set(supplied) != set(OIEC_BENCH_TRACKS):
            raise EGCFError("SAA-12.2 benchmark policy must define every OIEC-Bench track exactly once")
        groups = int(self.minimum_independence_groups)
        if groups < 1 or groups > 16:
            raise EGCFError("SAA-12.2 minimum independence groups outside bounded range")
        return OIECBenchGatePolicy(tuple(sorted(supplied.items())), groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_track_scores": dict(self.minimum_track_scores),
            "minimum_independence_groups": self.minimum_independence_groups,
        }


@dataclass(frozen=True)
class OIECBenchProfile:
    candidate_ref: str
    benchmark_context_signature: str
    track_scores: Tuple[Tuple[str, int], ...]
    evidence_ids: Tuple[str, ...]
    profile_signature: str

    def scores_dict(self) -> dict[str, int]:
        return dict(self.track_scores)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "benchmark_context_signature": self.benchmark_context_signature,
            "track_scores": dict(self.track_scores),
            "evidence_ids": list(self.evidence_ids),
            "profile_signature": self.profile_signature,
        }


@dataclass(frozen=True)
class OIECBenchGateAssessment:
    candidate_ref: str
    profile_signature: str
    policy_signature: str
    evidence_requirement_coverage_bp: int
    independence_groups: Tuple[str, ...]
    threshold_failures: Tuple[str, ...]
    independent_review: bool
    status: str
    canonical_promotion_eligible: bool
    assessment_signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "profile_signature": self.profile_signature,
            "policy_signature": self.policy_signature,
            "evidence_requirement_coverage_bp": self.evidence_requirement_coverage_bp,
            "independence_groups": list(self.independence_groups),
            "threshold_failures": list(self.threshold_failures),
            "independent_review": self.independent_review,
            "status": self.status,
            "canonical_promotion_eligible": self.canonical_promotion_eligible,
            "assessment_signature": self.assessment_signature,
        }


def make_oiec_bench_profile(
    *,
    candidate_ref: str,
    benchmark_context_signature: str,
    track_scores: Mapping[str, int],
    evidence_ids: Sequence[str],
) -> OIECBenchProfile:
    candidate = str(candidate_ref).strip()
    if not candidate:
        raise EGCFError("SAA-12.2 benchmark profile requires candidate_ref")
    context = str(benchmark_context_signature).strip().lower()
    if len(context) != 64 or any(character not in "0123456789abcdef" for character in context):
        raise EGCFError("SAA-12.2 benchmark context must be SHA-256")
    canonical_scores = {str(name).strip().upper(): _bp(score, f"benchmark score {name}") for name, score in track_scores.items()}
    if set(canonical_scores) != set(OIEC_BENCH_TRACKS):
        raise EGCFError("SAA-12.2 benchmark profile must report every required track and no extras")
    evidence = tuple(sorted({str(value).strip() for value in evidence_ids if str(value).strip()}))
    if not evidence:
        raise EGCFError("SAA-12.2 benchmark profile requires evidence references")
    payload = {
        "version": OIEC_BENCH_GATE_VERSION,
        "candidate_ref": candidate,
        "benchmark_context_signature": context,
        "track_scores": dict(sorted(canonical_scores.items())),
        "evidence_ids": list(evidence),
    }
    return OIECBenchProfile(
        candidate_ref=candidate,
        benchmark_context_signature=context,
        track_scores=tuple(sorted(canonical_scores.items())),
        evidence_ids=evidence,
        profile_signature=sha256_json(payload),
    )


def _ground_benchmark_evidence(store: Any, profile: OIECBenchProfile) -> tuple[Tuple[str, ...], int]:
    required = {f"oiec-bench:{track.casefold()}" for track in OIEC_BENCH_TRACKS}
    covered: set[str] = set()
    groups: set[str] = set()
    for evidence_id in profile.evidence_ids:
        try:
            record = store.get(evidence_id)
        except Exception as exc:
            raise EGCFError(f"SAA-12.2 benchmark evidence is not registered: {evidence_id}") from exc
        if not isinstance(record, EvidenceArtifact):
            raise EGCFError("SAA-12.2 benchmark evidence must reference EvidenceArtifact")
        if record.success is not True or record.simulated:
            raise EGCFError("SAA-12.2 benchmark evidence must be successful and non-simulated")
        if not record.producer.startswith(("deterministic-", "human-")) or record.method == "reported":
            raise EGCFError("SAA-12.2 benchmark evidence must be deterministic/human grounded")
        covered.update(str(value).strip().casefold() for value in record.requirement_ids)
        if record.independence_group:
            groups.add(record.independence_group)
    coverage = (10000 * len(required & covered)) // len(required)
    return tuple(sorted(groups)), coverage


def qualify_oiec_bench_gate(
    store: Any,
    profile: OIECBenchProfile,
    policy: OIECBenchGatePolicy,
    *,
    independent_review: bool,
) -> OIECBenchGateAssessment:
    if not isinstance(profile, OIECBenchProfile):
        raise EGCFError("SAA-12.2 qualification requires OIECBenchProfile")
    canonical_policy = policy.canonical()
    groups, coverage = _ground_benchmark_evidence(store, profile)
    scores = profile.scores_dict()
    thresholds = dict(canonical_policy.minimum_track_scores)
    failures = tuple(sorted(
        f"{track}:{scores[track]}<{thresholds[track]}"
        for track in OIEC_BENCH_TRACKS
        if scores[track] < thresholds[track]
    ))
    policy_signature = sha256_json({"version": OIEC_BENCH_GATE_VERSION, "policy": canonical_policy.to_dict()})
    if coverage != 10000:
        status = "OIEC_BENCH_EVIDENCE_INCOMPLETE"
    elif len(groups) < canonical_policy.minimum_independence_groups:
        status = "OIEC_BENCH_INDEPENDENCE_INSUFFICIENT"
    elif not independent_review:
        status = "OIEC_BENCH_REVIEW_REQUIRED"
    elif failures:
        status = "OIEC_BENCH_THRESHOLD_FAILURE"
    else:
        status = "OIEC_BENCH_PROMOTION_GATE_PASSED"
    eligible = status == "OIEC_BENCH_PROMOTION_GATE_PASSED"
    payload = {
        "version": OIEC_BENCH_GATE_VERSION,
        "candidate_ref": profile.candidate_ref,
        "profile_signature": profile.profile_signature,
        "policy_signature": policy_signature,
        "coverage": coverage,
        "groups": list(groups),
        "failures": list(failures),
        "independent_review": bool(independent_review),
        "status": status,
    }
    return OIECBenchGateAssessment(
        candidate_ref=profile.candidate_ref,
        profile_signature=profile.profile_signature,
        policy_signature=policy_signature,
        evidence_requirement_coverage_bp=coverage,
        independence_groups=groups,
        threshold_failures=failures,
        independent_review=bool(independent_review),
        status=status,
        canonical_promotion_eligible=eligible,
        assessment_signature=sha256_json(payload),
    )
