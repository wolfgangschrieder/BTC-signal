from __future__ import annotations
from .models import CrossMarketObservation, CrossMarketSnapshot
from .state import classify

class CrossMarketFeatureEngine:
    version="cross-market-v3"

    def build(self,timestamp,observations,as_of=None,previous=None,max_skew_seconds:float=300.0,max_source_latency_skew_seconds:float=30.0):
        cutoff=as_of or timestamp
        latest={}
        for obs in observations:
            if obs.point_in_time_available_at > cutoff or obs.timestamp > timestamp:
                continue
            current=latest.get(obs.asset)
            if current is None or (obs.timestamp, obs.point_in_time_available_at, obs.source) > (
                current.timestamp, current.point_in_time_available_at, current.source
            ):
                latest[obs.asset]=obs

        values={asset: obs.value for asset, obs in latest.items()}
        sources={asset: obs.source for asset, obs in latest.items()}
        event_times=[obs.timestamp for obs in latest.values()]
        skew_seconds=max((max(event_times)-min(event_times)).total_seconds(),0.0) if event_times else 0.0
        source_latencies=[max((obs.point_in_time_available_at-obs.timestamp).total_seconds(),0.0) for obs in latest.values()]
        source_latency_skew=max(source_latencies)-min(source_latencies) if source_latencies else 0.0
        synchronized=(
            bool(event_times)
            and skew_seconds <= max_skew_seconds
            and source_latency_skew <= max_source_latency_skew_seconds
        )
        availability={asset: synchronized for asset in latest}

        snapshot=CrossMarketSnapshot(
            timestamp, values, availability, sources,
            synchronized, skew_seconds, source_latency_skew, self.version
        )
        if synchronized and previous is not None:
            extra_returns=returns(snapshot,previous)
            values.update(extra_returns)
            availability.update({key: value is not None for key,value in extra_returns.items()})
            snapshot=CrossMarketSnapshot(
                timestamp, values, availability, sources,
                synchronized, skew_seconds, source_latency_skew, self.version
            )
        return snapshot

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
