from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Sequence
from .liquidity_replay import LiquidityReplayOutcome

@dataclass(frozen=True)
class RiskEvaluation:
    label: str
    horizon_minutes: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_rate: float | None
    mean_mfe: float | None
    mean_mae: float | None
    standard_error: float | None

def evaluate(outcomes: Sequence[LiquidityReplayOutcome], label: str, horizon_minutes: int) -> RiskEvaluation:
    xs=[float(x.realized_return_pct) for x in outcomes if x.realized_return_pct is not None]
    if not xs:
        return RiskEvaluation(label,horizon_minutes,0,None,None,None,None,None,None)
    ys=sorted(xs); n=len(xs); mean=sum(xs)/n
    variance=sum((x-mean)**2 for x in xs)/(n-1) if n>1 else 0.0
    mfe=sum(x.mfe_pct for x in outcomes)/len(outcomes)
    mae=sum(x.mae_pct for x in outcomes)/len(outcomes)
    return RiskEvaluation(label,horizon_minutes,n,mean,
        ys[n//2] if n%2 else (ys[n//2-1]+ys[n//2])/2,
        sum(x>0 for x in xs)/n,mfe,mae,sqrt(variance/n) if n>1 else 0.0)

def compare(outcomes: Sequence[LiquidityReplayOutcome], horizon_minutes: int) -> tuple[RiskEvaluation,...]:
    groups={}
    for item in outcomes:
        groups.setdefault(item.point.stop_source,[]).append(item)
    return tuple(evaluate(groups[k],k,horizon_minutes) for k in sorted(groups))

def split_evaluate(outcomes: Sequence[LiquidityReplayOutcome], horizon_minutes: int,
                   train_ratio: float=.70) -> tuple[tuple[RiskEvaluation,...],tuple[RiskEvaluation,...]]:
    ordered=tuple(sorted(outcomes,key=lambda x:x.point.timestamp))
    cut=int(len(ordered)*train_ratio)
    return compare(ordered[:cut],horizon_minutes), compare(ordered[cut:],horizon_minutes)
