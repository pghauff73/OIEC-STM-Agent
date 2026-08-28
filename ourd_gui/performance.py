from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class PerformanceSample:
    name: str
    duration_ms: float
    observed_at_monotonic: float
    metadata: Mapping[str, Any]


class PerformanceMonitor:
    def __init__(self, *, max_samples: int = 1_000) -> None:
        self.max_samples = max(1, int(max_samples))
        self._samples: deque[PerformanceSample] = deque(maxlen=self.max_samples)
        self._lock = threading.Lock()

    def record_ms(
        self,
        name: str,
        duration_ms: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        sample = PerformanceSample(
            name=str(name),
            duration_ms=max(0.0, float(duration_ms)),
            observed_at_monotonic=time.monotonic(),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._samples.append(sample)

    @contextmanager
    def measure(
        self,
        name: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_ms(name, (time.perf_counter() - started) * 1_000, metadata)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        grouped: dict[str, list[float]] = {}
        for sample in samples:
            grouped.setdefault(sample.name, []).append(sample.duration_ms)
        metrics: dict[str, Any] = {}
        for name, values in sorted(grouped.items()):
            ordered = sorted(values)
            p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95)))
            metrics[name] = {
                "count": len(values),
                "latest_ms": round(values[-1], 3),
                "average_ms": round(sum(values) / len(values), 3),
                "maximum_ms": round(max(values), 3),
                "p95_ms": round(ordered[p95_index], 3),
            }
        return {
            "sample_count": len(samples),
            "max_samples": self.max_samples,
            "metrics": metrics,
            "recent": [asdict(sample) for sample in samples[-20:]],
        }
