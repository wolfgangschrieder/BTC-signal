from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from research_os.execution.order_intent import OrderIntent

class AdapterOrderStatus(StrEnum):
    SUBMITTED="submitted"
    REJECTED="rejected"

@dataclass(frozen=True)
class AdapterOrderResult:
    client_order_id: str
    status: AdapterOrderStatus
    exchange_order_id: str | None
    reason: str | None = None

class ExecutionAdapter:
    name="base"
    def submit(self, intent: OrderIntent) -> AdapterOrderResult:
        raise NotImplementedError

class PaperExecutionAdapter(ExecutionAdapter):
    """Deterministic dry-run adapter; never contacts an exchange."""
    name="paper"
    def __init__(self, accept: bool=True, exchange_order_id_prefix: str="paper"):
        self.accept=accept
        self.exchange_order_id_prefix=exchange_order_id_prefix
        self.submissions: list[OrderIntent]=[]

    def submit(self, intent: OrderIntent) -> AdapterOrderResult:
        if intent.quantity <= 0:
            return AdapterOrderResult(intent.client_order_id,AdapterOrderStatus.REJECTED,None,"invalid quantity")
        if not self.accept:
            return AdapterOrderResult(intent.client_order_id,AdapterOrderStatus.REJECTED,None,"paper adapter configured to reject")
        self.submissions.append(intent)
        return AdapterOrderResult(intent.client_order_id,AdapterOrderStatus.SUBMITTED,f"{self.exchange_order_id_prefix}-{intent.client_order_id}")
