from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean, median

@dataclass(frozen=True)
class CrossMarketEvaluation:
    asset: str
    feature: str
    horizon_minutes: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_rate: float | None
    mean_mfe: float | None
    mean_mae: float | None
    standard_error: float | None
    ci95_low: float | None
    ci95_high: float | None
    train_sample_size: int
    test_sample_size: int

def _summary(values):
    if not values:
        return (None,None,None,None,None,None,None)
    n=len(values); mu=mean(values)
    variance=sum((x-mu)**2 for x in values)/(n-1) if n>1 else 0.0
    se=sqrt(variance/n) if n>1 else None
    margin=1.96*se if se is not None else None
    return (mu,median(values),sum(x>0 for x in values)/n,se,
            None if margin is None else mu-margin,
            None if margin is None else mu+margin,n)

def evaluate(rows, asset, horizon_minutes, feature="zscore", split_time=None):
    selected=[r for r in rows if r.asset==asset and horizon_minutes in (getattr(r,"horizon_minutes",horizon_minutes),)]
    if not selected:
        return CrossMarketEvaluation(asset,feature,horizon_minutes,0,None,None,None,None,None,None,None,None,0,0)
    # Dataset rows currently represent one outcome per asset/horizon; tolerate rows without horizon metadata.
    values=[float(r.btc_return_pct) for r in selected if r.btc_return_pct is not None]
    mfe=[float(r.btc_mfe_pct) for r in selected if r.btc_mfe_pct is not None]
    mae=[float(r.btc_mae_pct) for r in selected if r.btc_mae_pct is not None]
    mu,med,pos,se,lo,hi,n=_summary(values)
    train=sum(1 for r in selected if split_time is not None and r.timestamp < split_time)
    test=sum(1 for r in selected if split_time is not None and r.timestamp >= split_time)
    if split_time is None:
        train=n; test=0
    return CrossMarketEvaluation(asset,feature,horizon_minutes,n,mu,med,pos,
        mean(mfe) if mfe else None,mean(mae) if mae else None,se,lo,hi,train,test)

def evaluate_threshold(rows,asset,horizon_minutes,lower=None,upper=None,feature="zscore"):
    selected=[]
    for r in rows:
        if r.asset!=asset: continue
        value=getattr(r,feature,None)
        if value is None: continue
        if lower is not None and value < lower: continue
        if upper is not None and value > upper: continue
        selected.append(r)
    return evaluate(selected,asset,horizon_minutes,feature=feature)
