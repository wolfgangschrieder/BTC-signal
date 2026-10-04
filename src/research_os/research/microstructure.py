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
