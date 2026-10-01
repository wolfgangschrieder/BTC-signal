from datetime import datetime, timezone
from research_os.features.derivatives import DerivativesEngine, snapshot_features

def test_price_oi_divergence():
    s=DerivativesEngine().build(datetime.now(timezone.utc),100,open_interest=90,previous_price=99,previous_open_interest=100)
    assert s.price_oi_divergence == -1.0

def test_liquidation_imbalance():
    s=DerivativesEngine().build(datetime.now(timezone.utc),100,liquidation_long=8,liquidation_short=2)
    assert s.liquidation_imbalance == 0.6
    assert snapshot_features(s)["derivatives_liquidation_long"] == 8

def test_unavailable_without_data():
    s=DerivativesEngine().build(datetime.now(timezone.utc),100)
    assert not s.available
