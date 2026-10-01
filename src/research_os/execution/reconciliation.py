from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from research_os.execution.service import ExecutionRecord, ExecutionStatus

class ReconciliationAction(StrEnum):
    NOOP="noop"
    UPDATE="update"
    INVESTIGATE="investigate"

@dataclass(frozen=True)
class RemoteOrderState:
    client_order_id: str
    status: ExecutionStatus
    exchange_order_id: str | None = None
    reason: str | None = None

@dataclass(frozen=True)
class ReconciliationResult:
    client_order_id: str
    action: ReconciliationAction
    local_status: ExecutionStatus
    remote_status: ExecutionStatus | None
    reason: str

class ReconciliationEngine:
    version="reconciliation-v1"

    def reconcile(self, local: ExecutionRecord, remote: RemoteOrderState | None) -> ReconciliationResult:
        if remote is None:
            if local.status in {ExecutionStatus.SUBMITTING, ExecutionStatus.SUBMITTED, ExecutionStatus.PARTIALLY_FILLED}:
                return ReconciliationResult(local.client_order_id,ReconciliationAction.INVESTIGATE,local.status,None,"remote order state is missing")
            return ReconciliationResult(local.client_order_id,ReconciliationAction.NOOP,local.status,None,"no remote state expected")
        if remote.client_order_id != local.client_order_id:
            return ReconciliationResult(local.client_order_id,ReconciliationAction.INVESTIGATE,local.status,remote.status,"client order id mismatch")
        if remote.status is local.status:
            return ReconciliationResult(local.client_order_id,ReconciliationAction.NOOP,local.status,remote.status,"states match")
        terminal={ExecutionStatus.FILLED,ExecutionStatus.CANCELLED,ExecutionStatus.REJECTED}
        if local.status in terminal:
            return ReconciliationResult(local.client_order_id,ReconciliationAction.INVESTIGATE,local.status,remote.status,"local terminal state differs from remote")
        if remote.status in {ExecutionStatus.SUBMITTED,ExecutionStatus.PARTIALLY_FILLED,ExecutionStatus.FILLED,ExecutionStatus.CANCELLED,ExecutionStatus.REJECTED}:
            return ReconciliationResult(local.client_order_id,ReconciliationAction.UPDATE,local.status,remote.status,"remote state is authoritative for nonterminal local state")
        return ReconciliationResult(local.client_order_id,ReconciliationAction.INVESTIGATE,local.status,remote.status,"unrecognized state transition")
