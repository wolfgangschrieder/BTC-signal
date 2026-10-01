from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean, median

@dataclass(frozen=True)
class DerivativesStatistics:
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_return_rate: float | None
    mean_mfe: float | None
    mean_mae: float | None
    standard_error: float | None
    ci95_low: float | None
    ci95_high: float | None

def summarize(outcomes) -> DerivativesStatistics:
    values=[float(x.return_pct) for x in outcomes if x.return_pct is not None]
    if not values:
        return DerivativesStatistics(0,None,None,None,None,None,None,None,None)
    n=len(values); mu=mean(values)
    variance=sum((x-mu)**2 for x in values)/(n-1) if n>1 else 0.0
    se=sqrt(variance/n) if n>1 else None
    margin=1.96*se if se is not None else None
    return DerivativesStatistics(
        n,mu,median(values),sum(x>0 for x in values)/n,
        mean(float(x.mfe_pct) for x in outcomes if x.mfe_pct is not None),
        mean(float(x.mae_pct) for x in outcomes if x.mae_pct is not None),
        se,None if margin is None else mu-margin,None if margin is None else mu+margin)

def group_by_state(outcomes, attribute: str):
    groups={}
    for outcome in outcomes:
        state=getattr(outcome,"state",None)
        key=getattr(state,attribute,None) if state is not None else None
        groups.setdefault(key,[]).append(outcome)
    return {key:summarize(items) for key,items in groups.items()}

def split_time(outcomes, train_ratio: float=0.7):
    if not 0.5 <= train_ratio < 1.0:
        raise ValueError("train_ratio must be in [0.5, 1.0)")
    ordered=sorted(outcomes,key=lambda x:x.state_timestamp)
    cut=int(len(ordered)*train_ratio)
    return ordered[:cut],ordered[cut:]
