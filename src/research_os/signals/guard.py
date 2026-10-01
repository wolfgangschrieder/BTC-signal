from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from research_os.signals.models import SignalDirection, SignalResult

@dataclass
class SignalGuard:
    cooldown: timedelta=timedelta(minutes=15)
    last_key: str|None=None
    last_sent_at: datetime|None=None

    def allow(self, signal: SignalResult) -> bool:
        if signal.direction is SignalDirection.NONE: return False
        key=f"{signal.symbol}:{signal.direction.value}:{signal.levels}"
        if self.last_key == key and self.last_sent_at is not None:
            return signal.timestamp-self.last_sent_at >= self.cooldown
        return True

    def mark_sent(self, signal: SignalResult) -> None:
        self.last_key=f"{signal.symbol}:{signal.direction.value}:{signal.levels}"
        self.last_sent_at=signal.timestamp
