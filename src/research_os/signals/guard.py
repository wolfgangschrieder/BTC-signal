from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from research_os.signals.models import SignalDirection, SignalResult

@dataclass(frozen=True)
class SignalExecutionContext:
    latency_ms: float | None = None
    spread_bps: float | None = None
    orderbook_valid: bool = True
    orderbook_age_ms: int | None = None

@dataclass
class SignalGuard:
    cooldown: timedelta=timedelta(minutes=15)
    max_latency_ms: float=500.0
    max_spread_bps: float=10.0
    max_orderbook_age_ms: int=5000
    last_key: str|None=None
    last_sent_at: datetime|None=None

    def validate(self, signal: SignalResult, context: SignalExecutionContext | None = None) -> tuple[bool, tuple[str,...]]:
        if signal.direction is SignalDirection.NONE:
            return False, ("signal direction is none",)
        if context is not None:
            if context.latency_ms is not None and context.latency_ms > self.max_latency_ms:
                return False, ("socket latency above guard threshold",)
            if context.spread_bps is not None and context.spread_bps > self.max_spread_bps:
                return False, ("spread above guard threshold",)
            if not context.orderbook_valid:
                return False, ("orderbook is invalid",)
            if context.orderbook_age_ms is not None and context.orderbook_age_ms > self.max_orderbook_age_ms:
                return False, ("orderbook is stale",)
        key=f"{signal.symbol}:{signal.direction.value}:{signal.levels}"
        if self.last_key == key and self.last_sent_at is not None:
            if signal.timestamp-self.last_sent_at < self.cooldown:
                return False, ("duplicate signal inside cooldown",)
        return True, ()

    def allow(self, signal: SignalResult, context: SignalExecutionContext | None = None) -> bool:
        return self.validate(signal, context)[0]

    def mark_sent(self, signal: SignalResult) -> None:
        self.last_key=f"{signal.symbol}:{signal.direction.value}:{signal.levels}"
        self.last_sent_at=signal.timestamp
