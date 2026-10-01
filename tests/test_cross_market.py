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


def test_cross_market_engine_adds_pit_safe_returns():
    from datetime import datetime, timezone
    from research_os.cross_market.models import CrossMarketObservation
    from research_os.cross_market.engine import CrossMarketFeatureEngine
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    previous=CrossMarketFeatureEngine().build(t,[CrossMarketObservation("DXY",t,t,100,"test")])
    current=CrossMarketFeatureEngine().build(t,[CrossMarketObservation("DXY",t,t,101,"test")],previous=previous)
    assert round(current.values["DXY_return"],6)==0.01

def test_cross_market_rejects_invalid_observation():
    from datetime import datetime, timezone, timedelta
    import pytest
    from research_os.cross_market.models import CrossMarketObservation
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        CrossMarketObservation("DXY",t,t,float("inf"),"test")
    with pytest.raises(ValueError):
        CrossMarketObservation("DXY",t,t-timedelta(seconds=1),100,"test")


def test_cross_market_rejects_latency_skew():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    observations=[
        CrossMarketObservation("SPX",t,t,5000,"source-a"),
        CrossMarketObservation("VIX",t+timedelta(minutes=10),t+timedelta(minutes=10),20,"source-b"),
    ]
    snapshot=CrossMarketFeatureEngine().build(t+timedelta(minutes=10),observations,as_of=t+timedelta(minutes=10),max_skew_seconds=300)
    assert not snapshot.synchronized
    assert snapshot.max_event_time_skew_seconds == 600
    assert not any(snapshot.availability.values())
