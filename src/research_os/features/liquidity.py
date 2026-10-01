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
    def build(self, orderbook_state, reference_price, timestamp_ms=None, gap_bps=5.0, min_levels=2):
        if not orderbook_state.valid or reference_price<=0 or not isfinite(reference_price):
            return LiquidityState(timestamp_ms or orderbook_state.last_event_time_ms,False,(),(),None,None)
        bids=_cluster("bid",orderbook_state.bids,reference_price,gap_bps,min_levels)
        asks=_cluster("ask",orderbook_state.asks,reference_price,gap_bps,min_levels)
        return LiquidityState(
            timestamp_ms or orderbook_state.last_event_time_ms,True,
            tuple(bids),tuple(asks),bids[0] if bids else None,asks[0] if asks else None)
