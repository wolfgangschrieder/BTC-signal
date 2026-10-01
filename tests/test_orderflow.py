from datetime import datetime, timezone
from research_os.features.orderflow import OrderFlowEngine, TradeObservation, snapshot_features

def trade(sec, size, side):
    return TradeObservation(datetime.fromtimestamp(sec,tz=timezone.utc),100.0,size,side)

def test_orderflow_delta_and_imbalance():
    result=OrderFlowEngine().build([
        trade(1,3,"Buy"), trade(2,1,"Sell"), trade(3,2,"Buy")
    ],datetime.fromtimestamp(3,tz=timezone.utc))
    assert result.available
    assert result.buy_volume==5
    assert result.sell_volume==1
    assert result.delta==4
    assert result.imbalance==0.6666666666666666

def test_orderflow_cumulative_delta_is_stateful():
    result=OrderFlowEngine().build([trade(1,2,"Sell"),trade(2,1,"Buy")],datetime.fromtimestamp(2,tz=timezone.utc),cumulative_delta_base=10)
    assert result.delta==-1
    assert result.cumulative_delta==9

def test_orderflow_excludes_invalid_trades_and_reports_unavailable_when_empty():
    invalid=TradeObservation(datetime.now(timezone.utc),0,-1,"Buy")
    result=OrderFlowEngine().build([invalid],datetime.now(timezone.utc))
    assert result.available is False
    assert result.trade_count==0

def test_snapshot_features_are_numeric():
    result=OrderFlowEngine().build([trade(1,4,"Buy"),trade(2,2,"Sell")],datetime.fromtimestamp(2,tz=timezone.utc))
    values=snapshot_features(result)
    assert values["orderflow_delta"]==2
    assert values["orderflow_trade_count"]==2.0
