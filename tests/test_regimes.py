from research_os.research.regimes import RegimeClassifier,Regime,RegimeAnalyzer
from research_os.research.replay import ReplayResult
from research_os.signals.models import SignalResult,SignalDirection

def test_regime_classifier():
    c=RegimeClassifier()
    assert c.classify({"return_5":.02,"realized_vol":.01}) is Regime.TREND
    assert c.classify({"return_5":.001,"realized_vol":.01}) is Regime.RANGE
    assert c.classify({"return_5":.02,"realized_vol":.03}) is Regime.HIGH_VOLATILITY
    assert c.classify({"return_5":.02,"realized_vol":.001}) is Regime.LOW_VOLATILITY

def test_regime_analysis_counts_outcomes():
    s=SignalResult("BTCUSDT",None,SignalDirection.LONG,.8,.1,None,0,1,(),(), "signal-v1")
    a=ReplayResult(None,s,1,"win",.01,{"return_5":.02,"realized_vol":.01})
    b=ReplayResult(None,s,0,"loss",-.01,{"return_5":.03,"realized_vol":.01})
    report=RegimeAnalyzer().analyze([(a,a.features),(b,b.features)])
    assert report.stats[0].signals==2
    assert report.stats[0].resolved==2
    assert report.stats[0].win_rate==.5
