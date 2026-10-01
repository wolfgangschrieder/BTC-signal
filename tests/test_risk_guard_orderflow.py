from datetime import datetime, timezone
import asyncio
from research_os.signals.risk import RiskEngine, LiquidityLevel
from research_os.signals.guard import SignalGuard, SignalExecutionContext
from research_os.features.orderflow import OrderFlowEngine, TradeObservation
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult

def test_liquidity_stop_is_buffered_beyond_bid_pool():
    levels=RiskEngine().build_levels("long",100,2,(LiquidityLevel(98,100,"bid"),LiquidityLevel(99,10,"bid")))
    assert levels.stop_source=="liquidity"
    assert levels.stop_loss < 98
    assert levels.liquidity_reference < 98

def test_atr_fallback_without_liquidity():
    levels=RiskEngine().build_levels("short",100,2,())
    assert levels.stop_source=="atr"
    assert levels.stop_loss==102

def signal():
    return SignalResult("BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),SignalDirection.LONG,.8,.1,
        SignalLevels(99,101,98,103,105,107,1.5,2.5,3.5),1.2,2.0,(),())

def test_guard_rejects_bad_latency_and_spread():
    guard=SignalGuard(max_latency_ms=100,max_spread_bps=5)
    ok,reasons=guard.validate(signal(),SignalExecutionContext(latency_ms=101,spread_bps=1))
    assert not ok and reasons
    ok,reasons=guard.validate(signal(),SignalExecutionContext(latency_ms=10,spread_bps=6))
    assert not ok and reasons

def test_orderflow_async_offload_returns_snapshot():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    trades=[TradeObservation(t,100+i,1,"buy" if i%2 else "sell") for i in range(20)]
    async def run():
        return await OrderFlowEngine().build_async(trades,t)
    snapshot=asyncio.run(run())
    assert snapshot.available
