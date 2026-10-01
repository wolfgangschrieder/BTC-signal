from __future__ import annotations
from .models import CrossMarketObservation, CrossMarketSnapshot
from .state import classify

class CrossMarketFeatureEngine:
    version="cross-market-v1"

    def build(self, timestamp, observations, as_of=None):
        cutoff=as_of or timestamp
        latest={}
        for obs in observations:
            if not obs.is_pit_valid(cutoff) or obs.timestamp > timestamp:
                continue
            current=latest.get(obs.asset)
            if current is None or obs.timestamp > current.timestamp:
                latest[obs.asset]=obs
        values={}; availability={}; sources={}
        for asset,obs in latest.items():
            values[asset]=obs.value
            availability[asset]=True
            sources[asset]=obs.source
        snapshot=CrossMarketSnapshot(timestamp,values,availability,sources,self.version)
        return snapshot

def returns(snapshot, previous):
    out={}
    for asset,value in snapshot.values.items():
        prev=previous.values.get(asset) if previous else None
        out[f"{asset}_return"]=(value-prev)/abs(prev) if value is not None and prev not in (None,0) else None
    return out
