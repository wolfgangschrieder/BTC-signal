from research_os.cross_market.microstructure import (BookLevel, ExchangeOrderBook, OFIObservation, RollingOFIZScore, aggregate_normalized_multi_exchange_ofi, lead_lag_scan, normalize_multi_exchange_ofi, order_flow_imbalance, pearson_lead_lag)

def book(exchange, bid_price, ask_price, bid_size=10.0, ask_size=10.0):
    return ExchangeOrderBook(exchange, 1000, tuple(BookLevel(bid_price - i, bid_size) for i in range(5)), tuple(BookLevel(ask_price + i, ask_size) for i in range(5)))

def test_ofi_requires_previous_and_top_five():
    current = book("bybit", 100.0, 101.0)
    assert order_flow_imbalance(None, current) is None
    assert order_flow_imbalance(current, current) == 0.0

def test_ofi_buy_pressure():
    previous = book("bybit", 99.0, 101.0)
    current = book("bybit", 100.0, 101.0)
    assert order_flow_imbalance(previous, current) > 0.0

def test_rolling_zscore_is_past_only():
    z = RollingOFIZScore(window=10, min_samples=3)
    assert z.transform(1.0) is None
    assert z.transform(2.0) is None
    assert z.transform(3.0) is None
    value = z.transform(10.0)
    assert value is not None and value > 1.0

def test_lead_lag_positive_signal():
    leader = [1, 2, 3, 4, 5]
    follower = [0, 1, 2, 3, 4]
    assert pearson_lead_lag(leader, follower, 1) == 1.0

def test_lead_lag_scan():
    result = lead_lag_scan([1, 2, 3, 4, 5], [0, 1, 2, 3, 4], 1000)
    assert result[1].lag_ms == 5000
    assert len(result) == 6


def test_multi_exchange_ofi_is_normalized_per_exchange():
    normalizers = {
        "binance": RollingOFIZScore(window=10, min_samples=2),
        "bybit": RollingOFIZScore(window=10, min_samples=2),
    }
    history = [
        OFIObservation("binance", 1, 1.0, None),
        OFIObservation("binance", 2, 2.0, None),
        OFIObservation("bybit", 1, 10.0, None),
        OFIObservation("bybit", 2, 20.0, None),
    ]
    normalize_multi_exchange_ofi(history, normalizers)
    current = normalize_multi_exchange_ofi(
        [OFIObservation("binance", 3, 10.0, None), OFIObservation("bybit", 3, 100.0, None)],
        normalizers,
    )
    assert current[0].normalized_ofi is not None
    assert current[1].normalized_ofi is not None
    aggregate = aggregate_normalized_multi_exchange_ofi(current, min_exchanges=2)
    assert aggregate.available
    assert aggregate.coverage == 2
    assert aggregate.value is not None
