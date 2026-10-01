from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from research_os.features.derivatives import DerivativesState
from research_os.research.derivatives_outcomes import compute_outcome

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

def test_derivatives_outcome_is_deterministic():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    state=DerivativesState("positive_funding","rising","crowded_long","high","aligned_or_neutral","aligned_or_neutral","neutral",0.25,True)
    candles=[
        Candle(t,100,101,99,100),
        Candle(t+timedelta(minutes=1),100,103,98,102),
        Candle(t+timedelta(minutes=2),102,104,101,103),
    ]
    o=compute_outcome(state,t,candles,2,100,110)
    assert o is not None
    assert round(o.return_pct,6)==0.03
    assert round(o.mfe_pct,6)==0.04
    assert round(o.mae_pct,6)==-0.02
    assert round(o.oi_change_after,6)==0.1

def test_derivatives_outcome_requires_future_window():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    state=DerivativesState("unknown","unknown","unknown","unknown","unknown","unknown","unknown",0,False)
    candles=[Candle(t,100,101,99,100)]
    assert compute_outcome(state,t,candles,5) is not None
