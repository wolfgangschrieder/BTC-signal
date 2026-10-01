from datetime import datetime, timezone
from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.repository import CrossMarketRepository

class FakeResult:
    def mappings(self):
        return self
    def first(self):
        return {"asset":"DXY","event_time":datetime(2026,1,1,tzinfo=timezone.utc),"value":100.0}

class FakeSession:
    def __init__(self):
        self.calls=[]
    def execute(self, statement, params):
        self.calls.append((str(statement),params))
        return FakeResult()

def test_repository_api_is_pit_safe():
    assert hasattr(CrossMarketRepository,"save")
    assert hasattr(CrossMarketRepository,"latest")

def test_latest_passes_decision_time_to_both_event_and_pit_filters():
    session=FakeSession()
    t=datetime(2026,1,2,tzinfo=timezone.utc)
    row=CrossMarketRepository().latest(session,"DXY",t)
    assert row["asset"]=="DXY"
    sql,params=session.calls[0]
    assert "event_time<=:decision_time" in sql
    assert "point_in_time_available_at<=:decision_time" in sql
    assert params["decision_time"]==t

def test_save_preserves_observation_pit():
    session=FakeSession()
    obs=CrossMarketObservation("DXY",datetime(2026,1,1,tzinfo=timezone.utc),datetime(2026,1,1,0,1,tzinfo=timezone.utc),100.0,"test")
    CrossMarketRepository().save(session,obs)
    _,params=session.calls[0]
    assert params["event_time"]==obs.timestamp
    assert params["pit"]==obs.point_in_time_available_at
