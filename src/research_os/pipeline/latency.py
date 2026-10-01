from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from time import perf_counter
from typing import Iterator
from contextlib import contextmanager

@dataclass
class LatencyHistogram:
    samples_ms: list[float] = field(default_factory=list)
    max_samples: int = 10_000
    def observe(self, value_ms: float) -> None:
        if value_ms < 0:
            return
        self.samples_ms.append(value_ms)
        if len(self.samples_ms) > self.max_samples:
            del self.samples_ms[:len(self.samples_ms)-self.max_samples]
    def percentile(self, q: float) -> float | None:
        if not self.samples_ms:
            return None
        if not 0 <= q <= 1:
            raise ValueError("q must be between 0 and 1")
        xs=sorted(self.samples_ms)
        index=min(len(xs)-1, int(round(q*(len(xs)-1))))
        return xs[index]
    def summary(self) -> dict[str,float|int|None]:
        return {
            "count": len(self.samples_ms),
            "min_ms": min(self.samples_ms),
            "p50_ms": self.percentile(.50),
            "p95_ms": self.percentile(.95),
            "p99_ms": self.percentile(.99),
            "max_ms": max(self.samples_ms),
        }

@dataclass
class LatencyTelemetry:
    stages: dict[str,LatencyHistogram] = field(default_factory=lambda: defaultdict(LatencyHistogram))
    def observe(self, stage: str, elapsed_ms: float) -> None:
        self.stages[stage].observe(elapsed_ms)
    @contextmanager
    def timer(self, stage: str) -> Iterator[None]:
        start=perf_counter()
        try:
            yield
        finally:
            self.observe(stage,(perf_counter()-start)*1000.0)
    def report(self) -> dict[str,dict[str,float|int|None]]:
        return {name:hist.summary() for name,hist in self.stages.items()}
