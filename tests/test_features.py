from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine

def test_feature_engine_is_deterministic_and_does_not_fabricate_missing_data():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    a=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    b=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    assert a==b
    assert a.features[0].available
    assert any(f.name=="volume_mean" and not f.available for f in a.features)
