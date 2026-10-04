from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean

@dataclass(frozen=True, slots=True)
class LeadLagResult:
    leader: str
    lagger: str
    lag_seconds: int
    correlation: float | None
    sample_size: int
    stable: bool
    version: str = "lead-lag-v1"

def _corr(a,b):
    n=min(len(a),len(b))
    if n < 2: return None
    a=list(a)[-n:]; b=list(b)[-n:]
    ma=mean(a); mb=mean(b)
    da=[x-ma for x in a]; db=[x-mb for x in b]
    den=sqrt(sum(x*x for x in da)*sum(x*x for x in db))
    return None if den == 0 else sum(x*y for x,y in zip(da,db))/den

def scan_lead_lag(leader, lagger, series_a, series_b, lags=(1,5,15,30,60,300), min_samples=30, stability_threshold=0.10):
    results=[]
    a=list(series_a); b=list(series_b)
    for lag in lags:
        steps=max(1,int(lag))
        if len(a) <= steps or len(b) <= steps:
            results.append(LeadLagResult(leader,lagger,lag,None,0,False)); continue
        n=min(len(a)-steps,len(b))
        corr=_corr(a[-(n+steps):-steps],b[-n:])
        stable=corr is not None and abs(corr)>=stability_threshold and n>=min_samples
        results.append(LeadLagResult(leader,lagger,lag,corr,n,stable))
    return tuple(results)
