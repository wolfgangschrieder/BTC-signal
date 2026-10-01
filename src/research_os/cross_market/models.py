from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

@dataclass(frozen=True)
class CrossMarketObservation:
    asset: str
    timestamp: datetime
    point_in_time_available_at: datetime
    value: float
    source: str
    unit: str="raw"
    payload: dict | None=None

    def __post_init__(self):
        if not self.asset.strip():
            raise ValueError("asset is required")
        if not isfinite(self.value):
            raise ValueError("value must be finite")
        if self.point_in_time_available_at < self.timestamp:
            raise ValueError("PIT availability cannot precede event time")

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.point_in_time_available_at <= decision_time

@dataclass(frozen=True)
class CrossMarketSnapshot:
    timestamp: datetime
    values: dict[str,float|None]
    availability: dict[str,bool]
    sources: dict[str,str]
    synchronized: bool = True
    max_event_time_skew_seconds: float = 0.0
    max_source_latency_skew_seconds: float = 0.0
    version: str="cross-market-v3"
