from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from research_os.execution.confirmation import PendingConfirmation, ConfirmationStatus
from research_os.signals.models import SignalResult

@dataclass(frozen=True)
class ExecutionGuardContext:
    now: datetime
    current_price: float
    max_entry_deviation_bps: float=25.0
    max_signal_age_seconds: float=60.0
    existing_position: bool=False
    orderbook_valid: bool=True
    spread_bps: float=0.0
    max_spread_bps: float=10.0

@dataclass(frozen=True)
class ExecutionGuardResult:
    allowed: bool
    reasons: tuple[str,...]

class ExecutionGuard:
    version="execution-guard-v1"

    def validate(self, signal: SignalResult, confirmation: PendingConfirmation, ctx: ExecutionGuardContext) -> ExecutionGuardResult:
        reasons=[]
        if confirmation.status is not ConfirmationStatus.CONFIRMED:
            reasons.append("human confirmation is not confirmed")
        if ctx.now.tzinfo is None:
            reasons.append("current time must be timezone-aware")
        age=(ctx.now-signal.timestamp).total_seconds() if ctx.now.tzinfo and signal.timestamp.tzinfo else float("inf")
        if age < 0 or age > ctx.max_signal_age_seconds:
            reasons.append("signal is expired")
        if signal.levels is None:
            reasons.append("signal levels are missing")
        else:
            reference=(signal.levels.entry_min+signal.levels.entry_max)/2
            if reference <= 0 or abs(ctx.current_price-reference)/reference*10000 > ctx.max_entry_deviation_bps:
                reasons.append("price moved beyond entry tolerance")
        if ctx.existing_position:
            reasons.append("existing position blocks duplicate execution")
        if not ctx.orderbook_valid:
            reasons.append("orderbook is invalid")
        if ctx.spread_bps > ctx.max_spread_bps:
            reasons.append("spread exceeds execution limit")
        return ExecutionGuardResult(not reasons,tuple(reasons))
