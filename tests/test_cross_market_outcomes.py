from datetime import datetime, timedelta, timezone
from research_os.research.cross_market_outcomes import compute_btc_outcome, summarize

class Candle:
    def __init__(self,timestamp,close,high,low):
        self.timestamp=timestamp; self.close=close; self.high=high; self.low=low

def test_outcome_requires_complete_future_horizon():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    candles=[Candle(t+timedelta(minutes=i),100+i,101+i,99+i) for i in range(1,6)]
    assert compute_btc_outcome(t,"VIX",2.0,candles,10,100) is None

def test_outcome_uses_only_future_candles():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    candles=[Candle(t,100,1000,1),Candle(t+timedelta(minutes=1),101,102,99),Candle(t+timedelta(minutes=2),102,103,100)]
    o=compute_btc_outcome(t,"VIX",2.0,candles,2,100)
    assert o is not None
    assert o.btc_return_pct==0.02
    assert o.btc_mfe_pct==0.03
    assert o.btc_mae_pct==-0.01

def test_summary_is_descriptive():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    candles=[Candle(t+timedelta(minutes=i),100+i,100+i,100+i) for i in range(1,3)]
    outcomes=[
        compute_btc_outcome(t,"VIX",1.0,candles,2,100),
        compute_btc_outcome(t,"VIX",-1.0,candles,2,100),
    ]
    s=summarize(outcomes)
    assert s.sample_size==2
    assert s.positive_rate==1.0
