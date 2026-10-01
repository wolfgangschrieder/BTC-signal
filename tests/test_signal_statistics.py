from datetime import datetime, timezone
from research_os.research.signal_statistics import summarize
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome

def outcome(i,status,ret):
    t=datetime(2026,1,1+i,tzinfo=timezone.utc)
    return SignalOutcome("s"+str(i),"BTCUSDT","long",t,100,95,110,115,120,.8,status,ret,2,-1,t,60)

def test_statistics_include_uninteracted_signals():
    result=summarize((outcome(0,OutcomeStatus.WIN,.02),outcome(1,OutcomeStatus.LOSS,-.01),outcome(2,OutcomeStatus.EXPIRED,0)))
    assert result.sample_size==3
    assert result.wins==1
    assert result.losses==1
    assert result.expired==1
    assert result.win_rate==.5
    assert result.mean_return==.0033333333333333335
