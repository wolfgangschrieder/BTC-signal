from datetime import datetime, timezone

def test_market_state_vector_is_not_a_signal():
    from research_os.market.state_vector import MarketStateVector
    now=datetime.now(timezone.utc)
    state=MarketStateVector.build(
        "BTCUSDT",now,now,now,
        {"return_5m":0.01,"mtf_trend":"bullish"},
        {"return_5m":True,"mtf_trend":True},
        {},
    )
    assert state.symbol=="BTCUSDT"
    assert not hasattr(state,"direction")

def test_msv_separates_numeric_and_categorical_values():
    from research_os.market.state_vector import MarketStateVector
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    s=MarketStateVector.build(
        "BTCUSDT",t,t,t,
        {"return_1":0.01,"mtf_trend":"bullish","flag":True},{},{}
    )
    assert s.numeric["return_1"]==0.01
    assert s.categorical["mtf_trend"]=="bullish"
    assert s.numeric["flag"]==1.0
    assert s.fingerprint

def test_msv_fingerprint_changes_when_categorical_state_changes():
    from research_os.market.state_vector import MarketStateVector
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    a=MarketStateVector.build("BTCUSDT",t,t,t,{"x":1},{"x":True},{},categorical={"trend":"bullish"})
    b=MarketStateVector.build("BTCUSDT",t,t,t,{"x":1},{"x":True},{},categorical={"trend":"bearish"})
    assert a.fingerprint!=b.fingerprint
