from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from research_os.features.derivatives import DerivativesState

@dataclass(frozen=True)
class DerivativesOutcome:
    state_timestamp: datetime
    outcome_timestamp: datetime
    horizon_minutes: int
    return_pct: float
    mfe_pct: float
    mae_pct: float
    volatility: float | None
    oi_change_after: float | None
    regime_after: str | None

def compute_outcome(state: DerivativesState, state_timestamp: datetime, candles, horizon_minutes: int, oi_before: float | None = None, oi_after: float | None = None) -> DerivativesOutcome | None:
    if not candles:
        return None
    target=state_timestamp + timedelta(minutes=horizon_minutes)
    window=[c for c in candles if state_timestamp <= c.timestamp <= target]
    if not window:
        return None
    entry=float(window[0].close)
    if entry <= 0:
        return None
    final=window[-1]
    return_pct=(float(final.close)-entry)/entry
    highs=[float(c.high) for c in window]
    lows=[float(c.low) for c in window]
    mfe=(max(highs)-entry)/entry
    mae=(min(lows)-entry)/entry
    oi_change_after=None if oi_before in (None,0) or oi_after is None else (oi_after-oi_before)/abs(oi_before)
    return DerivativesOutcome(state_timestamp,final.timestamp,horizon_minutes,return_pct,mfe,mae,None,oi_change_after,None)
