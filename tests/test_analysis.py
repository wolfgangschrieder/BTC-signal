from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine
from research_os.market.state_builder import MarketStateBuilder
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection

def state(closes):
 t=datetime(2026,1,1,tzinfo=timezone.utc); f=FeatureEngine().build("BTCUSDT",t,closes); return MarketStateBuilder().build("BTCUSDT",t,t,t,f,{})

def test_analysis_is_directional_but_not_probability():
 r=MarketAnalyzer().analyze(state([100,101,102,103,104,105]))
 assert r.direction is EvidenceDirection.BULLISH
 assert r.bullish_score>r.bearish_score
 assert not hasattr(r,"probability")

def test_conflicting_short_and_long_horizons_are_visible():
 r=MarketAnalyzer().analyze(state([100,110,100,110,100,101]))
 assert r.direction in (EvidenceDirection.CONFLICTING,EvidenceDirection.BEARISH)
 assert len(r.evidence)>=2
