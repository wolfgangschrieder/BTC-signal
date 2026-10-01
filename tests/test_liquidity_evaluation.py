from datetime import datetime, timezone
from types import SimpleNamespace
from research_os.research.liquidity_evaluation import evaluate, compare, split_evaluate
from research_os.research.liquidity_replay import LiquidityReplayOutcome, LiquidityReplayPoint

def _o(i,source,ret):
    ts=datetime(2026,1,1,i,tzinfo=timezone.utc)
    point=LiquidityReplayPoint(ts,100,2,source=="liquidity",source,98,101,98 if source=="liquidity" else None)
    return LiquidityReplayOutcome(point,60,"win" if ret>0 else "loss",ret,.03,-.02,ts)

def test_evaluate_statistics():
    r=evaluate([_o(0,"liquidity",.01),_o(1,"liquidity",-.01)],"liquidity",60)
    assert r.sample_size==2
    assert r.mean_return==0
    assert r.positive_rate==.5
    assert r.standard_error>0

def test_compare_separates_sources():
    rs=compare([_o(0,"liquidity",.02),_o(1,"atr",-.01)],60)
    assert [x.label for x in rs]==["atr","liquidity"]

def test_split_is_chronological():
    xs=[_o(i,"atr",.01) for i in range(10)]
    train,test=split_evaluate(xs,60,.7)
    assert train[0].sample_size==7
    assert test[0].sample_size==3
