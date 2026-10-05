from research_os.signals.execution import ExecutionStatus, evaluate_candle
from research_os.signals.models import SignalDirection

def test_execution_fill_does_not_exit_when_check_exit_false():
    result=evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=102,low=98,check_exit=False)
    assert result.status is ExecutionStatus.PENDING
    assert result.entry_price==100

def test_execution_short_entry_fill_preserves_slippage():
    result=evaluate_candle(SignalDirection.SHORT,entry_price=100,stop_loss=101,take_profit=99,high=101,low=99,slippage_bps=10,check_exit=False)
    assert result.status is ExecutionStatus.PENDING
    assert result.entry_price==99.9

def test_execution_invalid_costs_rejected():
    try:
        evaluate_candle(SignalDirection.LONG,entry_price=100,stop_loss=99,take_profit=101,high=101,low=100,fee_bps=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative fees must be rejected")
