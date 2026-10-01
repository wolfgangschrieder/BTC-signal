from datetime import datetime, timezone
from research_os.execution.adapter import PaperExecutionAdapter
from research_os.execution.reconciliation_service import ExecutionReconciliationService
from research_os.execution.service import ExecutionRecord, ExecutionService, ExecutionStatus
from research_os.execution.order_intent import OrderIntent, OrderSide, OrderType

def make_record(service,status=ExecutionStatus.SUBMITTED):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    intent=OrderIntent("sig","BTCUSDT",OrderSide.BUY,OrderType.LIMIT,1,100,95,110,now,"rs-1")
    record=ExecutionRecord("rs-1","sig",status,now,now,intent)
    service.restore(record)
    return record

class RemoteAdapter(PaperExecutionAdapter):
    def __init__(self,status):
        super().__init__()
        self.remote_status=status
    def get_order(self,client_order_id):
        return __import__("research_os.execution.reconciliation",fromlist=["RemoteOrderState"]).RemoteOrderState(client_order_id,self.remote_status,"ex-1")

def test_reconciliation_updates_to_remote_filled():
    execution=ExecutionService()
    make_record(execution)
    service=ExecutionReconciliationService(execution,RemoteAdapter(ExecutionStatus.FILLED))
    result,updated=service.reconcile("rs-1",datetime(2026,1,1,0,1,tzinfo=timezone.utc))
    assert result.action.value=="update"
    assert updated.status is ExecutionStatus.FILLED
    assert updated.exchange_order_id=="ex-1"
