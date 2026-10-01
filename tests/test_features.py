from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine

def test_feature_engine_is_deterministic_and_does_not_fabricate_missing_data():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    a=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    b=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    assert a==b
    assert a.features[0].available
    assert any(f.name=="volume_mean" and not f.available for f in a.features)

def test_true_atr_requires_ohlc_and_is_computed():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    snapshot=FeatureEngine().build(
        "BTCUSDT",t,[100.0,102.0,101.0],
        highs=[101.0,104.0,103.0],lows=[99.0,100.0,99.0],
    )
    atr=next(feature for feature in snapshot.features if feature.name=="atr_14")
    assert atr.available is True
    assert atr.value == 4.0

def test_orderbook_features_are_unavailable_when_book_is_invalid():
    from research_os.exchanges.bybit.orderbook import OrderBook
    book=OrderBook("BTCUSDT")
    snapshot=FeatureEngine().build(
        "BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),[100.0,101.0],
        orderbook=book.state,
    )
    features={feature.name:feature for feature in snapshot.features}
    assert features["orderbook_imbalance"].available is False

def test_orderbook_imbalance_is_derived_from_valid_top_depth():
    from research_os.exchanges.bybit.orderbook import OrderBook
    book=OrderBook("BTCUSDT")
    assert book.apply({
        "topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":1000,
        "data":{"u":1,"seq":1,"b":[["100","3"]],"a":[["101","1"]]},
    }) is None
    t=datetime.fromtimestamp(1,tz=timezone.utc)
    snapshot=FeatureEngine().build("BTCUSDT",t,[100.0,101.0],orderbook=book.state)
    features={feature.name:feature for feature in snapshot.features}
    assert features["orderbook_imbalance"].available is True
    assert features["orderbook_imbalance"].value == 0.5
