from datetime import datetime, timedelta, timezone
from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.normalization import normalize_past_only

def test_normalization_excludes_current_observation():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    history=[CrossMarketObservation("VIX",t+timedelta(minutes=i),t+timedelta(minutes=i),float(i+1),"test") for i in range(20)]
    result=normalize_past_only("VIX",t+timedelta(minutes=20),21,history,min_samples=20)
    assert result.available
    assert result.sample_size==20
    assert result.zscore is not None
    assert result.percentile==1.0

def test_normalization_abstains_without_history():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    result=normalize_past_only("VIX",t,10,[],min_samples=20)
    assert not result.available
