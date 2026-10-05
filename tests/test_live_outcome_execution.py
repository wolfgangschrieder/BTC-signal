from datetime import datetime, timedelta, timezone
from research_os.signals.execution import ExecutionStatus, evaluate_candle
from research_os.signals.models import SignalDirection

def test_live_entry_candle_only_fills():
    fill=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=102,low=99,check_exit=False)
    assert fill.status is ExecutionStatus.PENDING
    assert fill.entry_price==100

def test_live_next_candle_resolves_after_fill():
    fill=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=102,low=99,check_exit=False)
    result=evaluate_candle(SignalDirection.LONG,entry_price=fill.entry_price,stop_loss=99,take_profit=101,high=101,low=100)
    assert result.status is ExecutionStatus.WIN

def test_live_entry_gap_does_not_fill():
    result=evaluate_candle(SignalDirection.SHORT,entry_price=100,stop_loss=101,take_profit=99,high=103,low=102,check_exit=False)
    assert result.status is ExecutionStatus.NO_FILL
