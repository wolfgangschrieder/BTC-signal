from datetime import datetime, timezone
from math import isclose
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine, CalibrationMetrics, CalibrationSample

def a(direction,b,s,ok=True):
    return AnalysisResult("BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),direction,(),b,s,0,ok,"")

def test_probabilities_sum_to_one():
    r=ProbabilityEngine().predict(a(EvidenceDirection.BULLISH,.8,.1))
    assert abs(r.long+r.short+r.no_signal-1)<1e-9 and r.long>r.short

def test_conflict_abstains():
    r=ProbabilityEngine().predict(a(EvidenceDirection.CONFLICTING,.8,.8))
    assert r.no_signal==1 and r.long==0 and r.short==0

def test_missing_data_abstains():
    r=ProbabilityEngine().predict(a(EvidenceDirection.BULLISH,.8,.1,False))
    assert r.no_signal==1

def test_calibration_metrics():
    xs=[CalibrationSample(.8,1),CalibrationSample(.2,0)]
    assert isclose(CalibrationMetrics.brier(xs),0.04,rel_tol=0,abs_tol=1e-12)
    assert CalibrationMetrics.log_loss(xs)>0
