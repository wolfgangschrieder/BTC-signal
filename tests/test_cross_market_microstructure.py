from research_os.cross_market.microstructure import BookLevel, ExchangeOrderBook, RollingOFIZScore, lead_lag_scan, order_flow_imbalance, pearson_lead_lag

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
