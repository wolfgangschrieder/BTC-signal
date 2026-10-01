from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine
from research_os.market.state_builder import MarketStateBuilder

def test_msv_has_stable_fingerprint():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    f=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    a=MarketStateBuilder().build("BTCUSDT",t,t,t,f,{})
    b=MarketStateBuilder().build("BTCUSDT",t,t,t,f,{})
    assert a.fingerprint==b.fingerprint
    assert a.availability["volume_mean"] is False
