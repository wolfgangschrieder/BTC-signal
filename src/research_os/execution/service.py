from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from threading import Lock
from research_os.execution.guard import ExecutionGuard, ExecutionGuardContext
from research_os.execution.order_intent import OrderIntent
from research_os.execution.confirmation import PendingConfirmation, ConfirmationStatus
from research_os.signals.models import SignalResult

class ExecutionStatus(StrEnum):
    CREATED="created"
    BLOCKED="blocked"
    SUBMITTING="submitting"
    SUBMITTED="submitted"
    PARTIALLY_FILLED="partially_filled"
    FILLED="filled"
    CANCELLED="cancelled"
    REJECTED="rejected"

@dataclass(frozen=True)
class ExecutionRecord:
    client_order_id: str
    signal_id: str
    status: ExecutionStatus
    created_at: datetime
    updated_at: datetime
    intent: OrderIntent
    reason: str | None=None
    exchange_order_id: str | None=None

class ExecutionService:
    """Orchestrates human-confirmed execution state; exchange I/O is injected."""
    version="execution-service-v1"

    def __init__(self, guard: ExecutionGuard | None=None):
        self.guard=guard or ExecutionGuard()
        self._records: dict[str,ExecutionRecord]={}
        self._lock=Lock()

    def prepare(self, signal: SignalResult, confirmation: PendingConfirmation,
                ctx: ExecutionGuardContext, quantity: float) -> ExecutionRecord:
        now=ctx.now
        result=self.guard.validate(signal,confirmation,ctx)
        if not result.allowed:
            intent=OrderIntent.from_signal(signal,quantity,now)
            record=ExecutionRecord(intent.client_order_id,signal.signal_id,ExecutionStatus.BLOCKED,now,now,intent,"; ".join(result.reasons))
            with self._lock:
                self._records[intent.client_order_id]=record
            return record
        intent=OrderIntent.from_signal(signal,quantity,now)
        with self._lock:
            existing=self._records.get(intent.client_order_id)
            if existing is not None:
                return existing
            record=ExecutionRecord(intent.client_order_id,signal.signal_id,ExecutionStatus.CREATED,now,now,intent)
            self._records[intent.client_order_id]=record
            return record

    def get(self, client_order_id: str) -> ExecutionRecord | None:
        with self._lock:
            return self._records.get(client_order_id)

    def transition(self, client_order_id: str, status: ExecutionStatus, now: datetime | None=None,
                   reason: str | None=None, exchange_order_id: str | None=None) -> ExecutionRecord:
        now=now or datetime.now(timezone.utc)
        with self._lock:
            current=self._records.get(client_order_id)
            if current is None:
                raise KeyError("unknown client_order_id")
            allowed={
                ExecutionStatus.CREATED:{ExecutionStatus.SUBMITTING,ExecutionStatus.CANCELLED,ExecutionStatus.BLOCKED},
                ExecutionStatus.SUBMITTING:{ExecutionStatus.SUBMITTED,ExecutionStatus.REJECTED,ExecutionStatus.CANCELLED},
                ExecutionStatus.SUBMITTED:{ExecutionStatus.PARTIALLY_FILLED,ExecutionStatus.FILLED,ExecutionStatus.CANCELLED,ExecutionStatus.REJECTED},
                ExecutionStatus.PARTIALLY_FILLED:{ExecutionStatus.PARTIALLY_FILLED,ExecutionStatus.FILLED,ExecutionStatus.CANCELLED},
                ExecutionStatus.FILLED:set(),
                ExecutionStatus.CANCELLED:set(),
                ExecutionStatus.REJECTED:set(),
                ExecutionStatus.BLOCKED:set(),
            }
            if status not in allowed[current.status]:
                raise ValueError(f"invalid transition {current.status.value}->{status.value}")
            record=ExecutionRecord(current.client_order_id,current.signal_id,status,current.created_at,now,current.intent,reason,exchange_order_id or current.exchange_order_id)
            self._records[client_order_id]=record
            return record
