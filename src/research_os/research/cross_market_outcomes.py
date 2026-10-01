from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt

@dataclass(frozen=True)
class CrossMarketOutcome:
    state_timestamp: datetime
    asset: str
    normalized_value: float | None
    outcome_timestamp: datetime
    horizon_minutes: int
    btc_return_pct: float
    btc_mfe_pct: float
    btc_mae_pct: float

def compute_btc_outcome(state_timestamp,asset,normalized_value,candles,horizon_minutes,entry_price=None):
    if entry_price is None or entry_price <= 0 or not candles:
        return None
    target=state_timestamp+timedelta(minutes=horizon_minutes)
    window=[c for c in candles if state_timestamp < c.timestamp <= target]
    if not window or window[-1].timestamp < target:
        return None
    entry=float(entry_price)
    final=window[-1]
    return CrossMarketOutcome(
        state_timestamp,asset,normalized_value,final.timestamp,horizon_minutes,
        (float(final.close)-entry)/entry,
        (max(float(c.high) for c in window)-entry)/entry,
        (min(float(c.low) for c in window)-entry)/entry,
    )

@dataclass(frozen=True)
class CrossMarketOutcomeStats:
    sample_size:int
    mean_return:float|None
    positive_rate:float|None
    mean_mfe:float|None
    mean_mae:float|None
    standard_error:float|None

def summarize(outcomes):
    values=[o.btc_return_pct for o in outcomes]
    if not values:
        return CrossMarketOutcomeStats(0,None,None,None,None,None)
    n=len(values); mu=sum(values)/n
    variance=sum((x-mu)**2 for x in values)/(n-1) if n>1 else 0.0
    se=sqrt(variance/n) if n>1 else None
    return CrossMarketOutcomeStats(
        n,mu,sum(x>0 for x in values)/n,
        sum(o.btc_mfe_pct for o in outcomes)/n,
        sum(o.btc_mae_pct for o in outcomes)/n,se)
