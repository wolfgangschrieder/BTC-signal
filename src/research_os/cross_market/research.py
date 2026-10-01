from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from .models import CrossMarketObservation
from .normalization import normalize_past_only, RollingNormalization

@dataclass(frozen=True)
class CrossMarketResearchSnapshot:
    timestamp: datetime
    observations: dict[str,CrossMarketObservation]
    normalized: dict[str,RollingNormalization]
    version: str="cross-market-research-v1"

class CrossMarketResearchEngine:
    def build(self,timestamp,observations,as_of=None,min_samples=20):
        cutoff=as_of or timestamp
        eligible=[o for o in observations
                  if o.timestamp <= timestamp and o.point_in_time_available_at <= cutoff]
        latest={}
        for obs in eligible:
            old=latest.get(obs.asset)
            if old is None or obs.timestamp > old.timestamp:
                latest[obs.asset]=obs
        normalized={}
        for asset,current in latest.items():
            history=[o for o in observations
                     if o.asset==asset
                     and o.timestamp < current.timestamp
                     and o.point_in_time_available_at <= cutoff]
            normalized[asset]=normalize_past_only(
                asset,current.timestamp,current.value,history,min_samples
            )
        return CrossMarketResearchSnapshot(timestamp,latest,normalized)
