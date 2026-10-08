from datetime import UTC, datetime

from research_os.exchanges.bybit.normalizer import BybitNormalizer


def test_trade_normalization_sets_pit_to_ingestion_time():
    ingestion = datetime(2026, 1, 1, tzinfo=UTC)
    event = BybitNormalizer.trade(
        {
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "price": "100000",
                    "size": "0.01",
                    "side": "Buy",
                    "timestamp_ms": 1767225600000,
                }
            ]
        },
        ingestion,
    )
    assert event.source == "bybit"
    assert event.symbol == "BTCUSDT"
    assert event.point_in_time_available_at == ingestion
    assert event.payload["price"] == "100000"


def test_liquidation_normalizer():
    event = BybitNormalizer.liquidation(
        {
            "topic": "allLiquidation.BTCUSDT",
            "ts": 1000,
            "data": [{"T": 900, "s": "BTCUSDT", "S": "Buy", "v": "2.5", "p": "60000"}],
        }
    )
    assert event.symbol == "BTCUSDT"
    assert event.payload["side"] == "Buy"
    assert event.payload["size"] == "2.5"


def test_compact_trade_batch_preserves_all_trades_and_identity():
    from research_os.data.ingestion import event_fingerprint

    ingestion = datetime(2026, 1, 1, tzinfo=UTC)
    item = {"s": "BTCUSDT", "p": "100", "v": "1", "S": "Buy", "T": 1767225600000}
    events = BybitNormalizer.trades(
        {"data": [{**item, "i": "one"}, {**item, "i": "two"}]}, ingestion
    )
    assert [event.payload["trade_id"] for event in events] == ["one", "two"]
    assert all(event.point_in_time_available_at == ingestion for event in events)
    assert all(event.payload["price"] == "100" for event in events)
    assert event_fingerprint(events[0]) != event_fingerprint(events[1])
    assert event_fingerprint(events[0]) == event_fingerprint(
        BybitNormalizer.trades({"data": [{**item, "i": "one"}]}, ingestion)[0]
    )


def test_single_trade_api_rejects_batch_instead_of_truncating():
    import pytest

    item = {"s": "BTCUSDT", "p": "100", "v": "1", "S": "Buy", "T": 1767225600000}
    with pytest.raises(ValueError, match="multi-trade batch"):
        BybitNormalizer.trade({"data": [item, item]})


def test_trade_batch_validates_every_item():
    import pytest

    item = {"s": "BTCUSDT", "p": "100", "v": "1", "S": "Buy", "T": 1767225600000}
    for data in ([], None, [item, {**item, "v": "-1"}], [{**item, "S": "invalid"}]):
        with pytest.raises(ValueError):
            BybitNormalizer.trades({"data": data})
