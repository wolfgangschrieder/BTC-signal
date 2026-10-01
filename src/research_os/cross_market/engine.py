from __future__ import annotations
from .models import CrossMarketObservation, CrossMarketSnapshot
from .state import classify

class CrossMarketFeatureEngine:
    version="cross-market-v2"

    def build(self,timestamp,observations,as_of=None,previous=None,max_skew_seconds:float=300.0):
        cutoff=as_of or timestamp
        latest={}
        for obs in observations:
            if obs.point_in_time_available_at > cutoff or obs.timestamp > timestamp:
                continue
            current=latest.get(obs.asset)
            if current is None or obs.timestamp > current.timestamp:
                latest[obs.asset]=obs
        values={}; availability={}; sources={}
        event_times=[obs.timestamp for obs in latest.values()]
        skew_seconds=max((max(event_times)-min(event_times)).total_seconds(),0.0) if event_times else 0.0
        synchronized=bool(event_times) and skew_seconds <= max_skew_seconds
        if not synchronized:
            availability={asset:False for asset in latest}
        event_times=[obs.timestamp for obs in latest.values()]
        skew_seconds=max((max(event_times)-min(event_times)).total_seconds(),0.0) if event_times else 0.0
        synchronized=bool(event_times) and skew_seconds <= max_skew_seconds
        if not synchronized:
            availability={asset:False for asset in latest}
        for asset,obs in latest.items():
            values[asset]=obs.value
            availability[asset]=True
            sources[asset]=obs.source
        if synchronized and previous is not None:
            values.update(returns(CrossMarketSnapshot(timestamp,values,availability,sources,self.version),previous))
            availability.update({f"{asset}_return": value is not None for asset,value in
                                 {k:v for k,v in values.items() if k.endswith("_return")}.items()})
        return CrossMarketSnapshot(timestamp,values,availability,sources,synchronized,skew_seconds,self.version)

    def state(self,snapshot):
        return classify(snapshot)

def returns(snapshot,previous):
    out={}
    for asset,value in snapshot.values.items():
        if asset.endswith("_return"):
            continue
        prev=previous.values.get(asset) if previous else None
        out[f"{asset}_return"]=(value-prev)/abs(prev) if value is not None and prev not in (None,0) else None
    return out
