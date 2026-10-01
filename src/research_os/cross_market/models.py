from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class CrossMarketObservation:
    asset: str
    timestamp: datetime
    point_in_time_available_at: datetime
    value: float
    source: str
    unit: str="raw"

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.point_in_time_available_at <= decision_time

@dataclass(frozen=True)
class CrossMarketSnapshot:
    timestamp: datetime
    values: dict[str,float|None]
    availability: dict[str,bool]
    sources: dict[str,str]
    version: str="cross-market-v1"
