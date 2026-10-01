from __future__ import annotations
from datetime import datetime, timezone
from research_os.execution.adapter import ExecutionAdapter
from research_os.execution.reconciliation import ReconciliationAction, ReconciliationEngine
from research_os.execution.service import ExecutionService, ExecutionStatus

class ExecutionReconciliationService:
    """Synchronizes in-flight local orders with the remote adapter without touching research outcomes."""
    version="execution-reconciliation-service-v1"

    def __init__(self, execution: ExecutionService, adapter: ExecutionAdapter):
        self.execution=execution
        self.adapter=adapter
        self.engine=ReconciliationEngine()

    def reconcile(self, client_order_id: str, now: datetime | None=None):
        now=now or datetime.now(timezone.utc)
        local=self.execution.get(client_order_id)
        if local is None:
            raise KeyError("unknown client_order_id")
        remote=self.adapter.get_order(client_order_id)
        result=self.engine.reconcile(local,remote)
        if result.action is ReconciliationAction.UPDATE and remote is not None:
            updated=self.execution.transition(
                client_order_id, remote.status, now,
                reason=remote.reason,
                exchange_order_id=remote.exchange_order_id,
            )
            return result, updated
        return result, local

    def reconcile_inflight(self, now: datetime | None=None):
        now=now or datetime.now(timezone.utc)
        results=[]
        for record in list(self.execution._records.values()):
            if record.status in {
                ExecutionStatus.SUBMITTING,
                ExecutionStatus.SUBMITTED,
                ExecutionStatus.PARTIALLY_FILLED,
            }:
                results.append(self.reconcile(record.client_order_id,now))
        return results
