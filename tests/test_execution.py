from research_os.signals.execution import ExecutionStatus,evaluate_candle
from research_os.signals.models import SignalDirection

def test_execution_gap_is_no_fill():
    result=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=103,low=102)
    assert result.status is ExecutionStatus.NO_FILL

def test_execution_long_tp():
    result=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=101,low=100)
    assert result.status is ExecutionStatus.WIN
    assert result.realized_return is not None

def test_execution_short_sl():
    result=evaluate_candle(SignalDirection.SHORT,entry_price=100,stop_loss=101,take_profit=99,high=101,low=100)
    assert result.status is ExecutionStatus.LOSS

def test_execution_both_targets_are_ambiguous_for_both_directions():
    for direction in (SignalDirection.LONG,SignalDirection.SHORT):
        result=evaluate_candle(direction,entry_price=100,stop_loss=99 if direction is SignalDirection.LONG else 101,take_profit=101 if direction is SignalDirection.LONG else 99,high=102,low=98)
        assert result.status is ExecutionStatus.AMBIGUOUS
        assert result.realized_return is None

def test_execution_applies_costs():
    result=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=101,low=100,fee_bps=10,slippage_bps=10)
    assert result.status is ExecutionStatus.WIN
    assert result.realized_return is not None
    assert result.realized_return < 0.01


def test_execution_uses_filled_entry_without_double_slippage():
    fill=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=100.5,low=99.5,slippage_bps=10,check_exit=False)
    result=evaluate_candle(SignalDirection.LONG,entry_price=fill.entry_price,stop_loss=99,take_profit=101,high=101,low=100.5,slippage_bps=10,entry_filled=True)
    assert fill.entry_price==100.1
    assert result.status is ExecutionStatus.WIN
    assert result.entry_price==100.1

def test_execution_filled_entry_checks_exit_without_touching_entry():
    result=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=101,low=100.5,entry_filled=True)
    assert result.status is ExecutionStatus.WIN
