from dataclasses import dataclass
from enum import StrEnum
from research_os.signals.models import SignalDirection

class ExecutionStatus(StrEnum):
    NO_FILL="no_fill"
    PENDING="pending"
    WIN="win"
    LOSS="loss"
    AMBIGUOUS="ambiguous"

@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ExecutionStatus
    entry_price: float|None=None
    realized_return: float|None=None
    reason: str|None=None

def evaluate_candle(direction, *, entry_price, stop_loss, take_profit, high, low, fee_bps=0.0, slippage_bps=0.0, check_exit=True, entry_filled=False, conservative_entry=False):
    if entry_price<=0 or stop_loss<=0 or take_profit<=0:
        raise ValueError("prices must be positive")
    if fee_bps<0 or slippage_bps<0:
        raise ValueError("fees and slippage must be non-negative")
    direction=SignalDirection(direction)
    slip=slippage_bps/10000.0
    fee=fee_bps/10000.0
    if not entry_filled:
        if not (low<=entry_price<=high):
            return ExecutionResult(ExecutionStatus.NO_FILL)
        entry=entry_price*(1+slip) if direction is SignalDirection.LONG else entry_price*(1-slip)
        if not check_exit:
            if conservative_entry:
                touches_exit = (low <= stop_loss or high >= take_profit) if direction is SignalDirection.LONG else (high >= stop_loss or low <= take_profit)
                if touches_exit:
                    return ExecutionResult(ExecutionStatus.AMBIGUOUS, entry, None, "entry and exit touched in one candle; ordering unknown")
            return ExecutionResult(ExecutionStatus.PENDING,entry)
    else:
        entry=entry_price
    if not check_exit and entry_filled:
        return ExecutionResult(ExecutionStatus.PENDING,entry)
    if direction is SignalDirection.LONG:
        hit_sl=low<=stop_loss
        hit_tp=high>=take_profit
        if hit_sl and hit_tp:
            return ExecutionResult(ExecutionStatus.AMBIGUOUS,entry,None,"both targets touched in one candle")
        if hit_sl:
            exit_price=stop_loss*(1-slip)
            return ExecutionResult(ExecutionStatus.LOSS,entry,(exit_price-entry)/entry-2*fee)
        if hit_tp:
            exit_price=take_profit*(1-slip)
            return ExecutionResult(ExecutionStatus.WIN,entry,(exit_price-entry)/entry-2*fee)
    else:
        hit_sl=high>=stop_loss
        hit_tp=low<=take_profit
        if hit_sl and hit_tp:
            return ExecutionResult(ExecutionStatus.AMBIGUOUS,entry,None,"both targets touched in one candle")
        if hit_sl:
            exit_price=stop_loss*(1+slip)
            return ExecutionResult(ExecutionStatus.LOSS,entry,(entry-exit_price)/entry-2*fee)
        if hit_tp:
            exit_price=take_profit*(1+slip)
            return ExecutionResult(ExecutionStatus.WIN,entry,(entry-exit_price)/entry-2*fee)
    return ExecutionResult(ExecutionStatus.PENDING)
