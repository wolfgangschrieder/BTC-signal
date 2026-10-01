from datetime import datetime, timezone
from research_os.market.state import DataQualityState, MarketStateVector, MarketStructure

def test_market_state_vector_is_not_a_signal():
    now = datetime.now(timezone.utc)
    state = MarketStateVector(
        state_id="test",
        symbol="BTCUSDT",
        timestamp=now,
        decision_time=now,
        point_in_time_available_at=now,
        feature_version="test",
        factor_version="test",
        regime_version="test",
        code_version="test",
        vector={"return_5m": 0.01},
        market_state=MarketStructure.BULLISH,
        data_quality=DataQualityState(
            overall_score=1.0,
            pit_valid=True,
            orderbook_valid=True,
            missing_ratio=0.0,
            stale_ratio=0.0,
        ),
    )
    assert state.symbol == "BTCUSDT"
    assert not hasattr(state, "direction")


def test_msv_separates_numeric_and_categorical_values():
    from datetime import datetime, timezone
    from research_os.market.state_vector import MarketStateVector
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    s=MarketStateVector.build("BTCUSDT",t,t,t,{"return_1":0.01,"mtf_trend":"bullish","flag":True},{}, {})
    assert s.numeric["return_1"]==0.01
    assert s.categorical["mtf_trend"]=="bullish"
    assert s.numeric["flag"]==1.0
    assert s.fingerprint
