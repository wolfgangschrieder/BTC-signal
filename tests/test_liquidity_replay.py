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
