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

def test_signal_guard_rejects_bad_expected_value():
    from research_os.signals.guard import SignalGuard
    from dataclasses import replace
    a,p=inputs()
    s=SignalEngine().build(a,p,100,2)
    rejected=replace(s, expected_value=-0.1)
    ok,reasons=SignalGuard().validate(rejected)
    assert not ok
    assert "expected value" in reasons[0]

def test_signal_guard_rejects_probability_below_threshold():
    from research_os.signals.guard import SignalGuard
    from dataclasses import replace
    a,p=inputs()
    s=SignalEngine().build(a,p,100,2)
    rejected=replace(s, probability=0.69)
    ok,reasons=SignalGuard().validate(rejected)
    assert not ok
    assert "probability" in reasons[0]

def test_signal_guard_fails_closed_on_data_quality_degradation():
    from research_os.signals.guard import SignalGuard, SignalExecutionContext
    a,p=inputs()
    s=SignalEngine().build(a,p,100,2)
    ok,reasons=SignalGuard().validate(s, SignalExecutionContext(data_quality_ok=False))
    assert not ok
    assert reasons == ("data quality degraded",)

def test_signal_guard_cooldown_blocks_repeated_emission():
    from research_os.signals.guard import SignalGuard
    a,p=inputs()
    s=SignalEngine().build(a,p,100,2)
    guard=SignalGuard()
    assert guard.allow(s)
    guard.mark_sent(s)
    ok,reasons=guard.validate(s)
    assert not ok
    assert reasons == ("duplicate signal inside cooldown",)
