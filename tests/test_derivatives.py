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


def test_derivatives_state_is_explicit_and_reproducible():
    s=DerivativesEngine().build(
        datetime(2026,1,1,tzinfo=timezone.utc),100,
        funding_rate=0.001, open_interest=110,
        previous_price=99, previous_funding_rate=0.0005,
        previous_open_interest=100,
        liquidation_long=8, liquidation_short=2,
    )
    assert s.state is not None
    assert s.state.available
    assert s.state.funding_regime == "positive_funding"
    assert s.state.oi_regime == "rising"
    assert s.state.positioning == "crowded_long"
    assert s.state.liquidation_stress == "observed"


def test_derivatives_state_unavailable_is_explicit():
    s=DerivativesEngine().build(datetime(2026,1,1,tzinfo=timezone.utc),100)
    assert s.state is not None
    assert not s.state.available
    assert s.state.alignment == "unknown"
