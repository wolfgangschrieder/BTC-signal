from datetime import datetime,timezone
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine,ProbabilityResult
from research_os.market.state_builder import MarketStateBuilder
from research_os.features.engine import FeatureEngine
from research_os.notifications.telegram import TelegramFormatter
from research_os.pipeline.realtime import RealtimeSignalPipeline
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard
from research_os.signals.models import SignalDirection
from research_os.intelligence.models import AnalysisResult,EvidenceDirection

def test_formatter_contains_human_actionable_fields():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    a=AnalysisResult("BTCUSDT",t,EvidenceDirection.BULLISH,(),.9,.1,0,True,"")
    p=ProbabilityResult("BTCUSDT",t,.8,.1,.1)
    s=SignalEngine().build(a,p,100,2)
    text=TelegramFormatter().format(s).text
    assert "BTCUSDT LONG" in text and "Entry:" in text and "SL:" in text and "TP1:" in text and "Probability:" in text

def test_pipeline_does_not_emit_no_signal():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    f=FeatureEngine().build("BTCUSDT",t,[100,101,102,103,104,105])
    state=MarketStateBuilder().build("BTCUSDT",t,t,t,f,{})
    pipe=RealtimeSignalPipeline(
        MarketAnalyzer(),ProbabilityEngine(),SignalEngine(min_probability=.30),
        TelegramFormatter(),SignalGuard(min_probability=.30,min_rr=1.0)
    )
    signal,msg=pipe.evaluate(state,105,2)
    assert signal.direction is SignalDirection.LONG and msg is not None
