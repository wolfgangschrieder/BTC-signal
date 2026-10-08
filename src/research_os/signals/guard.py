from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite
from research_os.signals.models import SignalDirection, SignalResult

@dataclass(frozen=True)
class SignalExecutionContext:
    latency_ms: float | None = None
    spread_bps: float | None = None
    orderbook_valid: bool = True
    orderbook_age_ms: int | None = None
    data_quality_ok: bool = True

@dataclass
class SignalGuard:
    cooldown: timedelta=timedelta(minutes=15)
    max_latency_ms: float=500.0
    max_spread_bps: float=10.0
    max_orderbook_age_ms: int=5000
    min_probability: float=0.70
    min_expected_value: float=0.0
    min_rr: float=1.5
    last_key: str|None=None
    last_sent_at: datetime|None=None
    sent_at: dict[str, datetime] = field(default_factory=dict)

    def validate(self, signal: SignalResult, context: SignalExecutionContext | None = None) -> tuple[bool, tuple[str,...]]:
        if signal.direction is SignalDirection.NONE:
            return False, ("signal direction is none",)
        if not isfinite(signal.probability) or not 0.0 <= signal.probability <= 1.0:
            return False, ("invalid directional probability",)
        if not isfinite(signal.no_signal_probability) or not 0.0 <= signal.no_signal_probability <= 1.0:
            return False, ("invalid no-signal probability",)
        if signal.probability + signal.no_signal_probability > 1.0 + 1e-9:
            return False, ("probability mass exceeds one",)
        if signal.probability < self.min_probability:
            return False, ("probability below guard threshold",)
        if not isfinite(signal.expected_value) or signal.expected_value < self.min_expected_value:
            return False, ("expected value below guard threshold",)
        if not isfinite(signal.leverage) or signal.leverage <= 0:
            return False, ("invalid leverage",)
        if signal.levels is None:
            return False, ("signal levels are missing",)
        if not all(isfinite(x) and x > 0 for x in (
            signal.levels.entry_min, signal.levels.entry_max, signal.levels.stop_loss,
            signal.levels.tp1, signal.levels.tp2, signal.levels.tp3,
        )):
            return False, ("signal levels are invalid",)
        if min(signal.levels.rr_tp1, signal.levels.rr_tp2, signal.levels.rr_tp3) < self.min_rr:
            return False, ("risk/reward below guard threshold",)
        if context is not None:
            if not context.data_quality_ok:
                return False, ("data quality degraded",)
            if context.latency_ms is not None and context.latency_ms > self.max_latency_ms:
                return False, ("socket latency above guard threshold",)
            if context.spread_bps is not None and context.spread_bps > self.max_spread_bps:
                return False, ("spread above guard threshold",)
            if not context.orderbook_valid:
                return False, ("orderbook is invalid",)
            if context.orderbook_age_ms is not None and context.orderbook_age_ms > self.max_orderbook_age_ms:
                return False, ("orderbook is stale",)
        key=f"{signal.symbol}:{signal.direction.value}"
        last = self.sent_at.get(key)
        if last is not None and signal.timestamp-last < self.cooldown:
            return False, ("duplicate signal inside cooldown",)
        return True, ()

    def allow(self, signal: SignalResult, context: SignalExecutionContext | None = None) -> bool:
        return self.validate(signal, context)[0]

    def restore_sent(self, symbol: str, direction: str, timestamp: datetime) -> None:
        key = f"{symbol}:{direction}"
        previous = self.sent_at.get(key)
        if previous is None or timestamp > previous:
            self.sent_at[key] = timestamp

    def mark_sent(self, signal: SignalResult) -> None:
        self.last_key=f"{signal.symbol}:{signal.direction.value}"
        self.last_sent_at=signal.timestamp
        self.restore_sent(signal.symbol, signal.direction.value, signal.timestamp)
