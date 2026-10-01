from datetime import datetime, timezone
from research_os.features.engine import FeatureEngine
from research_os.features.orderflow import OrderflowEngine
from research_os.market.types import TradeEvent,OrderSide,BookLevel,OrderbookState

def test_orderflow_calculation():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    trades=(TradeEvent("BTCUSDT",ts,ts,100,2,OrderSide.BUY),
             TradeEvent("BTCUSDT",ts,ts,100,1,OrderSide.SELL))
    state=OrderflowEngine().calculate(trades)
    assert state.delta==1
    assert state.buy_volume==2

def test_liquidity_uses_top_n_levels():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    book=OrderbookState("BTCUSDT",ts,
        tuple(BookLevel(100-i,1) for i in range(7)),
        tuple(BookLevel(101+i,2) for i in range(7)))
    snapshot=FeatureEngine(5).build(orderbook=book)
    assert snapshot.numeric["liquidity.bid_depth"]==5
    assert snapshot.numeric["liquidity.ask_depth"]==10
