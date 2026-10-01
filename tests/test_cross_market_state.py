from datetime import datetime, timezone
from research_os.cross_market.models import CrossMarketSnapshot
from research_os.cross_market.state import classify

def test_cross_market_risk_on_state():
    s=CrossMarketSnapshot(datetime(2026,1,1,tzinfo=timezone.utc),
      {"DXY_return":-0.01,"NASDAQ_return":0.01,"SPX_return":0.008,"VIX_return":-0.05},
      {"DXY_return":True,"NASDAQ_return":True,"SPX_return":True,"VIX_return":True},
      {"DXY_return":"test","NASDAQ_return":"test","SPX_return":"test","VIX_return":"test"})
    state=classify(s)
    assert state.available
    assert state.risk_sentiment=="risk_on"
    assert state.alignment=="aligned"

def test_cross_market_unavailable():
    s=CrossMarketSnapshot(datetime(2026,1,1,tzinfo=timezone.utc),{}, {}, {})
    assert not classify(s).available
