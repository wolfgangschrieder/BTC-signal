from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from research_os.signals.models import SignalResult

class ConfirmationStatus(StrEnum):
    PENDING="pending"
    CONFIRMED="confirmed"
    CANCELLED="cancelled"
    EXPIRED="expired"

@dataclass(frozen=True)
class PendingConfirmation:
    signal_id: str
    symbol: str
    direction: str
    created_at: datetime
    expires_at: datetime
    status: ConfirmationStatus=ConfirmationStatus.PENDING

class HumanConfirmationService:
    """Human approval boundary. It never submits an exchange order."""
    version="confirmation-v1"

    def __init__(self, ttl_seconds: int=60, repository=None):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl=timedelta(seconds=ttl_seconds)
        self._pending: dict[str,PendingConfirmation]={}
        self.repository=repository

    def create(self, signal: SignalResult, now: datetime | None=None) -> PendingConfirmation:
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        item=PendingConfirmation(signal.signal_id,signal.symbol,signal.direction.value,now,now+self.ttl)
        self._pending[item.signal_id]=item
        if self.repository is not None:
            self.repository.save_confirmation(item)
        return item

    def get(self, signal_id: str, now: datetime | None=None) -> PendingConfirmation | None:
        item=self._pending.get(signal_id)
        if item is None:
            return None
        now=now or datetime.now(timezone.utc)
        if now >= item.expires_at and item.status is ConfirmationStatus.PENDING:
            item=PendingConfirmation(item.signal_id,item.symbol,item.direction,item.created_at,item.expires_at,ConfirmationStatus.EXPIRED)
            self._pending[signal_id]=item
            if self.repository is not None:
                self.repository.save_confirmation(item)
        return item

    def confirm(self, signal_id: str, now: datetime | None=None) -> PendingConfirmation:
        item=self.get(signal_id,now)
        if item is None:
            raise KeyError("unknown signal")
        if item.status is not ConfirmationStatus.PENDING:
            raise ValueError(f"confirmation is {item.status.value}")
        item=PendingConfirmation(item.signal_id,item.symbol,item.direction,item.created_at,item.expires_at,ConfirmationStatus.CONFIRMED)
        self._pending[signal_id]=item
        if self.repository is not None:
            self.repository.save_confirmation(item)
        return item

    def cancel(self, signal_id: str, now: datetime | None=None) -> PendingConfirmation:
        item=self.get(signal_id,now)
        if item is None:
            raise KeyError("unknown signal")
        if item.status is not ConfirmationStatus.PENDING:
            raise ValueError(f"confirmation is {item.status.value}")
        item=PendingConfirmation(item.signal_id,item.symbol,item.direction,item.created_at,item.expires_at,ConfirmationStatus.CANCELLED)
        self._pending[signal_id]=item
        if self.repository is not None:
            self.repository.save_confirmation(item)
        return item
