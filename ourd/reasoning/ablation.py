from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import stable_hash


REQUIRED_ABLATIONS = (
    "one_path_only",
    "without_hypothesis_state",
    "without_verifier",
    "without_falsifier",
    "without_diversity_filter",
    "without_synthesis_verification",
    "without_adaptive_compute",
    "full_sr",
)
SR_ABLATION_PIPELINE_PREFIX = (
    "super_reasoning_kernel_grounded_topology_v2_task_isolated"
)


@dataclass(frozen=True)
class AblationConfiguration:
    schema_version: int = 1
    ablation_id: str = "full_sr"
    path_count: int = 4
    proposer_batch_size: int = 1
    verifier_batch_size: int = 2
    falsifier_batch_size: int = 1
    hypothesis_state_enabled: bool = True
    verifier_enabled: bool = True
    falsifier_enabled: bool = True
    diversity_filter_enabled: bool = True
    synthesis_verification_enabled: bool = True
    adaptive_compute_enabled: bool = True
    signature: str = ""

    def __post_init__(self) -> None:
        if self.ablation_id not in REQUIRED_ABLATIONS:
            raise ValueError(f"invalid qualification ablation: {self.ablation_id}")
        if not 1 <= int(self.path_count) <= 16:
            raise ValueError("ablation path count must be 1..16")
        for name in (
            "proposer_batch_size",
            "verifier_batch_size",
            "falsifier_batch_size",
        ):
            if not 1 <= int(getattr(self, name)) <= 16:
                raise ValueError(f"{name.replace('_', ' ')} must be 1..16")
        material = asdict(self)
        material.pop("signature", None)
        expected = stable_hash(material)
        if self.signature and self.signature != expected:
            raise ValueError("ablation configuration signature mismatch")
        object.__setattr__(self, "signature", expected)

    @property
    def is_full_sr(self) -> bool:
        return self.ablation_id == "full_sr"


def standard_ablation_configurations() -> tuple[AblationConfiguration, ...]:
    return (
        AblationConfiguration(ablation_id="one_path_only", path_count=1),
        AblationConfiguration(
            ablation_id="without_hypothesis_state",
            path_count=4,
            hypothesis_state_enabled=False,
        ),
        AblationConfiguration(
            ablation_id="without_verifier",
            path_count=4,
            verifier_enabled=False,
        ),
        AblationConfiguration(
            ablation_id="without_falsifier",
            path_count=4,
            falsifier_enabled=False,
        ),
        AblationConfiguration(
            ablation_id="without_diversity_filter",
            path_count=4,
            diversity_filter_enabled=False,
        ),
        AblationConfiguration(
            ablation_id="without_synthesis_verification",
            path_count=4,
            synthesis_verification_enabled=False,
        ),
        AblationConfiguration(
            ablation_id="without_adaptive_compute",
            path_count=4,
            adaptive_compute_enabled=False,
        ),
        AblationConfiguration(ablation_id="full_sr", path_count=4),
    )


def ablation_pipeline(configuration: AblationConfiguration) -> str:
    return (
        f"{SR_ABLATION_PIPELINE_PREFIX}:"
        f"{configuration.ablation_id}:{configuration.signature}"
    )


__all__ = [
    "AblationConfiguration",
    "REQUIRED_ABLATIONS",
    "SR_ABLATION_PIPELINE_PREFIX",
    "ablation_pipeline",
    "standard_ablation_configurations",
]
