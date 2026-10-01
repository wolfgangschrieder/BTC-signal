from datetime import datetime, timedelta, timezone
from research_os.cross_market.engine import CrossMarketFeatureEngine, returns
from research_os.cross_market.models import CrossMarketObservation

def test_cross_market_is_pit_safe():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    observations=[
        CrossMarketObservation("DXY",t-timedelta(minutes=1),t,100,"test"),
        CrossMarketObservation("DXY",t,t+timedelta(minutes=1),101,"future-source"),
        CrossMarketObservation("VIX",t-timedelta(minutes=1),t,20,"test"),
    ]
    s=CrossMarketFeatureEngine().build(t,observations,as_of=t)
    assert s.values["DXY"]==100
    assert s.values["VIX"]==20
    assert s.sources["DXY"]=="test"

def test_cross_market_returns_require_previous_value():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    s=CrossMarketFeatureEngine().build(t,[CrossMarketObservation("DXY",t,t,101,"test")])
    assert returns(s,None)["DXY_return"] is None
