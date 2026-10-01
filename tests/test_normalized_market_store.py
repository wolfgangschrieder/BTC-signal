from datetime import datetime, timezone
from research_os.data.models import EventType, RawEvent
from research_os.market.store import NormalizedMarketDataStore
from research_os.market.models import Trade, MarketSnapshot

class FakeSession:
    def __init__(self): self.items=[]
    def add(self,obj): self.items.append(obj)

def event(kind,payload):
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    return RawEvent(source="bybit",event_type=kind,symbol="BTCUSDT",event_time=t,ingestion_time=t,point_in_time_available_at=t,payload=payload)

def test_trade_projection():
    s=FakeSession()
    NormalizedMarketDataStore().persist(s,event(EventType.TRADE,{"price":"100","size":"2","side":"Buy"}),11)
    assert isinstance(s.items[0],Trade)
    assert s.items[0].raw_event_id==11

def test_ticker_projection_derives_mid_and_spread():
    s=FakeSession()
    NormalizedMarketDataStore().persist(s,event(EventType.TICKER,{"last_price":"100","bid_price":"99","ask_price":"101","timestamp_ms":1}),12)
    assert isinstance(s.items[0],MarketSnapshot)
    assert s.items[0].mid_price==100
    assert s.items[0].spread==2
