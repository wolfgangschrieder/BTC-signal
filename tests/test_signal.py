from datetime import datetime,timezone
from research_os.intelligence.models import AnalysisResult,EvidenceDirection
from research_os.intelligence.probability import ProbabilityResult
from research_os.signals.engine import SignalEngine
from research_os.signals.models import SignalDirection

def inputs(direction=EvidenceDirection.BULLISH):
    a=AnalysisResult("BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),direction,(),.9,.1,0,True,"")
    p=ProbabilityResult("BTCUSDT",a.timestamp,.8,.1,.1)
    return a,p

def test_long_signal_has_levels_and_risk():
    a,p=inputs()
    s=SignalEngine().build(a,p,100,2)
    assert s.direction is SignalDirection.LONG
    assert s.levels and s.levels.stop_loss<100
    assert s.levels.rr_tp1>=1.5
    assert s.leverage>=1

def test_short_signal():
    a,p=inputs(EvidenceDirection.BEARISH)
    p=ProbabilityResult("BTCUSDT",a.timestamp,.1,.8,.1)
    s=SignalEngine().build(a,p,100,2)
    assert s.direction is SignalDirection.SHORT
    assert s.levels.stop_loss>100

def test_no_atr_means_no_trade():
    a,p=inputs()
    s=SignalEngine().build(a,p,100,None)
    assert s.direction is SignalDirection.NONE
    assert s.levels is None
