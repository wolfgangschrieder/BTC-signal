from datetime import datetime, timezone
from research_os.features.derivatives import DerivativesState
from research_os.research.derivatives_outcomes import DerivativesOutcome
from research_os.research.derivatives_analysis import summarize, split_time, group_by_state

def outcome(ts, ret, state):
    return DerivativesOutcome(ts,state,ts,60,ret,abs(ret)*2,-abs(ret),None,None,None)

def test_statistics_and_confidence_interval():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    s=DerivativesState("positive_funding","rising","crowded_long","high","aligned_or_neutral","aligned_or_neutral","neutral",.25,True)
    r=summarize([outcome(t,.01,s),outcome(t+__import__("datetime").timedelta(hours=1),-.01,s),outcome(t+__import__("datetime").timedelta(hours=2),.02,s)])
    assert r.sample_size==3
    assert r.positive_return_rate==2/3
    assert r.ci95_low is not None and r.ci95_high is not None

def test_grouping_and_time_split_are_deterministic():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    s1=DerivativesState("positive_funding","rising","crowded_long","high","aligned_or_neutral","aligned_or_neutral","neutral",.25,True)
    s2=DerivativesState("negative_funding","falling","mixed","none","aligned_or_neutral","aligned_or_neutral","neutral",0,True)
    xs=[outcome(t+i*__import__("datetime").timedelta(hours=1),0.01 if i%2==0 else -0.01,s1 if i<3 else s2) for i in range(6)]
    groups=group_by_state(xs,"funding_regime")
    assert set(groups)=={"positive_funding","negative_funding"}
    train,test=split_time(xs,.5)
    assert len(train)==3 and len(test)==3
