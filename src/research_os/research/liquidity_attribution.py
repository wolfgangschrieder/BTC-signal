from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean, median
from typing import Iterable

@dataclass(frozen=True)
class LiquidityRiskObservation:
    timestamp: object
    direction: str
    entry: float
    atr: float
    stop: float
    stop_source: str
    liquidity_reference: float | None
    cluster_size: float | None
    cluster_percentile: float | None
    cluster_persistent: bool
    cluster_lifetime_ms: int
    horizon_minutes: int
    realized_return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None

@dataclass(frozen=True)
class LiquidityRiskSummary:
    stop_source: str
    horizon_minutes: int
    sample_size: int
    mean_return_pct: float | None
    median_return_pct: float | None
    positive_rate: float | None
    mean_mfe_pct: float | None
    mean_mae_pct: float | None
    stop_distance_atr: float | None
    standard_error: float | None

def summarize(observations: Iterable[LiquidityRiskObservation], stop_source: str, horizon_minutes: int) -> LiquidityRiskSummary:
    rows=[x for x in observations if x.stop_source==stop_source and x.horizon_minutes==horizon_minutes]
    returns=[float(x.realized_return_pct) for x in rows if x.realized_return_pct is not None]
    mfe=[float(x.mfe_pct) for x in rows if x.mfe_pct is not None]
    mae=[float(x.mae_pct) for x in rows if x.mae_pct is not None]
    distances=[abs(x.entry-x.stop)/x.atr for x in rows if x.atr>0 and x.entry>0]
    if not returns:
        return LiquidityRiskSummary(stop_source,horizon_minutes,0,None,None,None,None,None,
                                    mean(distances) if distances else None,None)
    n=len(returns); mu=mean(returns)
    variance=sum((x-mu)**2 for x in returns)/(n-1) if n>1 else 0.0
    se=sqrt(variance/n) if n>1 else None
    return LiquidityRiskSummary(stop_source,horizon_minutes,n,mu,median(returns),
        sum(x>0 for x in returns)/n,mean(mfe) if mfe else None,
        mean(mae) if mae else None,mean(distances) if distances else None,se)

def compare_sources(observations: Iterable[LiquidityRiskObservation], horizon_minutes: int):
    rows=list(observations)
    return {source: summarize(rows,source,horizon_minutes)
            for source in ("liquidity","atr","atr_fallback")}
