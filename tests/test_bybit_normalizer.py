from datetime import datetime, timezone
from research_os.exchanges.bybit.normalizer import BybitNormalizer

def test_trade_normalization_sets_pit_to_ingestion_time():
    ingestion = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = BybitNormalizer.trade({
        "data": [{"symbol": "BTCUSDT", "price": "100000", "size": "0.01", "side": "Buy", "timestamp_ms": 1767225600000}]
    }, ingestion)
    assert event.source == "bybit"
    assert event.symbol == "BTCUSDT"
    assert event.point_in_time_available_at == ingestion
    assert event.payload["price"] == "100000"

def test_liquidation_normalizer():
    event=BybitNormalizer.liquidation({"topic":"allLiquidation.BTCUSDT","ts":1000,"data":[{"T":900,"s":"BTCUSDT","S":"Buy","v":"2.5","p":"60000"}]})
    assert event.symbol=="BTCUSDT"
    assert event.payload["side"]=="Buy"
    assert event.payload["size"]=="2.5"
