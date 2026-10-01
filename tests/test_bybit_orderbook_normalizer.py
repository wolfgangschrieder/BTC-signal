from datetime import datetime, timezone
from research_os.data.models import EventType
from research_os.exchanges.bybit.normalizer import BybitNormalizer

def test_orderbook_snapshot_normalization_preserves_pit():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    raw={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":1000,"data":{"s":"BTCUSDT","u":7,"seq":9,"b":[["100","1.2"]],"a":[["101","2.3"]]}}
    e=BybitNormalizer.orderbook(raw,t)
    assert e.event_type is EventType.ORDERBOOK_SNAPSHOT
    assert e.symbol=="BTCUSDT"
    assert e.payload["update_id"]==7
    assert e.point_in_time_available_at==t
    assert e.payload["bids"]==[["100","1.2"]]

def test_orderbook_delta_normalization():
    raw={"topic":"orderbook.50.BTCUSDT","type":"delta","ts":2000,"data":{"s":"BTCUSDT","u":8,"seq":10,"b":[["100","0"]],"a":[]}}
    e=BybitNormalizer.orderbook(raw,datetime(2026,1,1,tzinfo=timezone.utc))
    assert e.event_type is EventType.ORDERBOOK_UPDATE
    assert e.payload["update_id"]==8
    assert e.payload["sequence"]==10
