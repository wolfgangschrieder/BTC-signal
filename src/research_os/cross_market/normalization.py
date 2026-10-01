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
    version: str="rolling-normalization-v1"

def normalize_past_only(asset,timestamp,value,history,min_samples=20):
    past=[x for x in history if x.timestamp < timestamp and x.value is not None]
    values=[float(x.value) for x in past]
    if value is None or len(values)<min_samples:
        return RollingNormalization(asset,timestamp,value,None,None,len(values),False)
    mu=mean(values)
    variance=sum((x-mu)**2 for x in values)/len(values)
    sd=sqrt(variance)
    z=None if sd==0 else (value-mu)/sd
    rank=sum(x <= value for x in values)
    percentile=rank/len(values)
    return RollingNormalization(asset,timestamp,value,z,percentile,len(values),True)
