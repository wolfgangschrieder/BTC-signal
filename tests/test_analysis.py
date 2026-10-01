from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine
from research_os.market.state_builder import MarketStateBuilder
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection

def state(closes):
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    f=FeatureEngine().build("BTCUSDT",t,closes)
    return MarketStateBuilder().build("BTCUSDT",t,t,t,f,{})

def test_analysis_is_directional_but_not_probability():
    r=MarketAnalyzer().analyze(state([100,101,102,103,104,105]))
    assert r.direction is EvidenceDirection.BULLISH
    assert r.bullish_score>r.bearish_score
    assert not hasattr(r,"probability")

def test_conflicting_short_and_long_horizons_are_visible():
    r=MarketAnalyzer().analyze(state([100,110,100,110,94.1747572815534,97]))
    assert r.direction is EvidenceDirection.CONFLICTING
    assert r.conflicts >= 1
    assert len(r.evidence)>=2

def test_orderbook_imbalance_contributes_directional_evidence():
    from research_os.market.state_vector import MarketStateVector
    state=MarketStateVector.build(
        "BTCUSDT",
        datetime(2026,1,1,tzinfo=timezone.utc),
        datetime(2026,1,1,tzinfo=timezone.utc),
        datetime(2026,1,1,tzinfo=timezone.utc),
        {"return_1":0.0,"return_5":0.0,"realized_vol":0.005,"orderbook_imbalance":0.6},
        {"return_1":True,"return_5":True,"realized_vol":True,"orderbook_imbalance":True},
        {},
    )
    result=MarketAnalyzer().analyze(state)
    evidence=[e for e in result.evidence if e.feature=="orderbook_imbalance"]
    assert evidence
    assert evidence[0].direction.value=="bullish"
