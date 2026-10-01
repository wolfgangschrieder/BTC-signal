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
    from datetime import datetime, timezone
    snapshot = FeatureEngine().build(
        "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        [100.0, 102.0, 101.0],
        highs=[101.0, 104.0, 103.0],
        lows=[99.0, 100.0, 99.0],
    )
    atr = next(feature for feature in snapshot.features if feature.name == "atr_14")
    assert atr.available is True
    assert atr.value == 4.0
