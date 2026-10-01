from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from research_os.features.liquidity import LiquidityCluster, LiquidityState
from research_os.research.liquidity_replay import build_risk_point, resolve
from research_os.signals.risk import RiskEngine

def _liq(ts):
    c=LiquidityCluster("bid",97.9,98.1,98.0,500,4,.99,200,True,0,3000,3000)
    return LiquidityState(ts,True,(c,),(),c,None)

def test_replay_uses_persistent_liquidity():
    t=1_700_000_000_000
    point=build_risk_point(datetime(2026,1,1,tzinfo=timezone.utc),100,2,"long",_liq(t),RiskEngine())
    assert point.stop_source=="liquidity"
    assert point.liquidity_reference==98.0

def test_replay_resolves_tp():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    point=build_risk_point(ts,100,2,"long",None,RiskEngine())
    candles=[SimpleNamespace(timestamp=ts+timedelta(minutes=i),high=104,low=99,close=103) for i in range(1,61)]
    out=resolve(point,candles,"long",60)
    assert out is not None
    assert out.status=="win"
    assert out.realized_return_pct>0

def test_replay_dataset_is_chronological():
    from research_os.research.liquidity_replay import build_dataset, chronological_split, summarize_replay, LiquidityReplayPoint
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    points=[
        LiquidityReplayPoint(ts,100,2,False,"atr",98,101,None),
        LiquidityReplayPoint(ts+timedelta(minutes=1),100,2,False,"atr",98,101,None),
    ]
    candles=[]
    for i in range(1,61):
        candles.append(SimpleNamespace(timestamp=ts+timedelta(minutes=i),high=102,low=99,close=101))
    candles += [SimpleNamespace(timestamp=ts+timedelta(minutes=61+i),high=102,low=99,close=101) for i in range(60)]
    dataset=build_dataset(points,candles,"long",train_ratio=.5)
    train,test=chronological_split(dataset)
    assert len(train)==1 and len(test)==1
    assert train[0].point.timestamp < test[0].point.timestamp
    assert summarize_replay(dataset.outcomes)["sample_size"]==2
