from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean

@dataclass(frozen=True)
class RollingNormalization:
    asset: str
    timestamp: object
    value: float | None
    zscore: float | None
    percentile: float | None
    sample_size: int
    available: bool
    window_size: int
    version: str="rolling-normalization-v2"

def normalize_past_only(asset,timestamp,value,history,min_samples=20,window_size=252):
    if window_size < min_samples or min_samples < 1:
        raise ValueError("window_size must be >= min_samples >= 1")
    past=sorted(
        (x for x in history if x.timestamp < timestamp and x.value is not None),
        key=lambda x:x.timestamp
    )[-window_size:]
    values=[float(x.value) for x in past]
    if value is None or len(values)<min_samples:
        return RollingNormalization(asset,timestamp,value,None,None,len(values),False,window_size)
    current=float(value)
    mu=mean(values)
    variance=sum((x-mu)**2 for x in values)/len(values)
    sd=sqrt(variance)
    z=None if sd==0 else (current-mu)/sd
    percentile=sum(x<=current for x in values)/len(values)
    return RollingNormalization(asset,timestamp,current,z,percentile,len(values),True,window_size)
