from datetime import datetime, timezone
from research_os.market.types import BookLevel, OrderbookState, OrderflowState, CrossMarketObservation
def test_orderbook_hot_path_properties():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    book=OrderbookState("BTCUSDT",ts,(BookLevel(100,2),),(BookLevel(101,3),))
    assert book.mid_price==100.5
    assert book.spread==1
def test_orderflow_slots():
    assert "__dict__" not in OrderflowState.__slots__
def test_cross_market_observation():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    x=CrossMarketObservation("DXY",ts,ts,100,"fred")
    assert x.value==100
