from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from collections.abc import Sequence

@dataclass(frozen=True)
class LiquidityCluster:
    side: str
    low_price: float
    high_price: float
    center_price: float
    total_size: float
    level_count: int
    size_percentile: float
    distance_bps: float
    persistent: bool = False
    first_seen_ms: int | None = None
    last_seen_ms: int | None = None
    lifetime_ms: int = 0

@dataclass(frozen=True)
class LiquidityState:
    timestamp_ms: int
    valid: bool
    bid_clusters: tuple[LiquidityCluster,...]
    ask_clusters: tuple[LiquidityCluster,...]
    strongest_bid: LiquidityCluster | None
    strongest_ask: LiquidityCluster | None
    version: str = "liquidity-v1"

def _cluster(side, levels, reference_price, gap_bps, min_levels):
    if not levels or reference_price <= 0:
        return []
    ordered=sorted(((float(x.price),float(x.size)) for x in levels if x.size>0), key=lambda x:x[0])
    groups=[]
    current=[]
    prev=None
    for price,size in ordered:
        if prev is None or abs(price-prev)/prev*10000 <= gap_bps:
            current.append((price,size))
        else:
            if len(current)>=min_levels: groups.append(current)
            current=[(price,size)]
        prev=price
    if len(current)>=min_levels: groups.append(current)
    totals=[sum(size for _,size in g) for g in groups]
    result=[]
    for group,total in zip(groups,totals):
        weights=sum(size for _,size in group)
        center=sum(price*size for price,size in group)/weights
        rank=sum(x<=total for x in totals)/len(totals) if totals else 0.0
        result.append(LiquidityCluster(
            side,min(p for p,_ in group),max(p for p,_ in group),center,total,
            len(group),rank,abs(center-reference_price)/reference_price*10000))
    return sorted(result,key=lambda x:x.total_size,reverse=True)

class LiquidityEngine:
    def __init__(self, persistence_gap_bps: float = 10.0, persistence_min_ms: int = 2000):
        self.persistence_gap_bps=persistence_gap_bps
        self.persistence_min_ms=persistence_min_ms
        self._history: dict[str,list[dict[str,int|float]]]={"bid":[],"ask":[]}

    def reset(self):
        self._history={"bid":[],"ask":[]}

    def _with_persistence(self, clusters, timestamp_ms):
        result=[]
        for cluster in clusters:
            history=self._history[cluster.side]
            match=None
            for item in history:
                distance=abs(cluster.center_price-float(item["center"]))/cluster.center_price*10000
                if distance <= self.persistence_gap_bps:
                    match=item; break
            if match is None:
                match={"center":cluster.center_price,"first":timestamp_ms,"last":timestamp_ms}
                history.append(match)
            else:
                match["center"]=cluster.center_price; match["last"]=timestamp_ms
            lifetime=max(0,int(match["last"])-int(match["first"]))
            result.append(LiquidityCluster(cluster.side,cluster.low_price,cluster.high_price,cluster.center_price,cluster.total_size,cluster.level_count,cluster.size_percentile,cluster.distance_bps,lifetime>=self.persistence_min_ms,int(match["first"]),int(match["last"]),lifetime))
        cutoff=timestamp_ms-self.persistence_min_ms*5
        for side in self._history:
            self._history[side]=[x for x in self._history[side] if int(x["last"])>=cutoff]
        return result

    def build(self, orderbook_state, reference_price, timestamp_ms=None, gap_bps=5.0, min_levels=2):
        if not orderbook_state.valid or reference_price<=0 or not isfinite(reference_price):
            return LiquidityState(timestamp_ms or orderbook_state.last_event_time_ms,False,(),(),None,None)
        ts=timestamp_ms or orderbook_state.last_event_time_ms
        bids=self._with_persistence(_cluster("bid",orderbook_state.bids,reference_price,gap_bps,min_levels),ts)
        asks=self._with_persistence(_cluster("ask",orderbook_state.asks,reference_price,gap_bps,min_levels),ts)
        return LiquidityState(ts,True,tuple(bids),tuple(asks),max(bids,key=lambda x:x.total_size,default=None),max(asks,key=lambda x:x.total_size,default=None))


def snapshot_features(state: LiquidityState) -> dict[str, float | None]:
    bid=state.strongest_bid; ask=state.strongest_ask
    return {
        "liquidity_strongest_bid_size": bid.total_size if bid else None,
        "liquidity_strongest_ask_size": ask.total_size if ask else None,
        "liquidity_strongest_bid_distance_bps": bid.distance_bps if bid else None,
        "liquidity_strongest_ask_distance_bps": ask.distance_bps if ask else None,
        "liquidity_bid_cluster_count": float(len(state.bid_clusters)) if state.valid else None,
        "liquidity_ask_cluster_count": float(len(state.ask_clusters)) if state.valid else None,
        "liquidity_strongest_bid_persistent": 1.0 if bid and bid.persistent else (0.0 if bid else None),
        "liquidity_strongest_ask_persistent": 1.0 if ask and ask.persistent else (0.0 if ask else None),
        "liquidity_strongest_bid_lifetime_ms": float(bid.lifetime_ms) if bid else None,
        "liquidity_strongest_ask_lifetime_ms": float(ask.lifetime_ms) if ask else None,
    }
