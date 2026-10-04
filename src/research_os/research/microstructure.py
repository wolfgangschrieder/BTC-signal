from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean

@dataclass(frozen=True, slots=True)
class OFIObservation:
    exchange: str
    timestamp: object
    value: float
    history: tuple[float, ...]

@dataclass(frozen=True, slots=True)
class NormalizedOFI:
    exchange: str
    timestamp: object
    raw: float
    zscore: float | None
    percentile: float | None
    sample_size: int
    available: bool

@dataclass(frozen=True, slots=True)
class CrossExchangeOFI:
    timestamp: object
    components: tuple[NormalizedOFI, ...]
    aggregate: float | None
    available: bool
    version: str = "multi-exchange-ofi-v1"

def compute_order_flow_imbalance(previous_book, current_book, levels: int = 5) -> float | None:
    """Compute raw top-N OFI from two consecutive validated order-book states."""
    if levels < 1:
        raise ValueError("levels must be positive")
    if not getattr(previous_book, "valid", False) or not getattr(current_book, "valid", False):
        return None
    if getattr(previous_book, "symbol", None) != getattr(current_book, "symbol", None):
        return None
    previous_update_id = getattr(previous_book, "update_id", 0)
    current_update_id = getattr(current_book, "update_id", 0)
    if current_update_id <= previous_update_id:
        return None
    previous_time_ms = getattr(previous_book, "last_event_time_ms", 0)
    current_time_ms = getattr(current_book, "last_event_time_ms", 0)
    if previous_time_ms and current_time_ms and current_time_ms < previous_time_ms:
        return None
    prev_bids=list(getattr(previous_book, "bids", ()))[:levels]
    curr_bids=list(getattr(current_book, "bids", ()))[:levels]
    prev_asks=list(getattr(previous_book, "asks", ()))[:levels]
    curr_asks=list(getattr(current_book, "asks", ()))[:levels]
    if not prev_bids or not curr_bids or not prev_asks or not curr_asks:
        return None

    def side_map(items):
        return {float(x.price): float(x.size) for x in items}

    pb,cb,pa,ca=map(side_map,(prev_bids,curr_bids,prev_asks,curr_asks))
    bid_prices=set(pb)|set(cb)
    ask_prices=set(pa)|set(ca)
    best_prev_bid=float(prev_bids[0].price)
    best_curr_bid=float(curr_bids[0].price)
    best_prev_ask=float(prev_asks[0].price)
    best_curr_ask=float(curr_asks[0].price)

    bid=0.0
    for price in bid_prices:
        if price >= best_curr_bid:
            bid += cb.get(price,0.0)
        if price <= best_prev_bid:
            bid -= pb.get(price,0.0)

    ask=0.0
    for price in ask_prices:
        if price <= best_curr_ask:
            ask -= ca.get(price,0.0)
        if price >= best_prev_ask:
            ask += pa.get(price,0.0)
    return bid + ask

def normalize_ofi(exchange: str, timestamp, value: float, history, min_samples: int = 20, window_size: int = 252) -> NormalizedOFI:
    past=[float(x) for x in history][-window_size:]
    if len(past) < min_samples:
        return NormalizedOFI(exchange,timestamp,float(value),None,None,len(past),False)
    mu=mean(past)
    variance=sum((x-mu)**2 for x in past)/len(past)
    sd=sqrt(variance)
    z=None if sd == 0 else (float(value)-mu)/sd
    percentile=sum(x <= float(value) for x in past)/len(past)
    return NormalizedOFI(exchange,timestamp,float(value),z,percentile,len(past),z is not None)

def aggregate_cross_exchange(timestamp, observations, min_samples: int = 20, window_size: int = 252) -> CrossExchangeOFI:
    components=tuple(normalize_ofi(x.exchange,timestamp,x.value,x.history,min_samples,window_size) for x in observations)
    usable=[x for x in components if x.available and x.zscore is not None]
    aggregate=sum(x.zscore for x in usable)/len(usable) if usable else None
    return CrossExchangeOFI(timestamp,components,aggregate,bool(usable))
