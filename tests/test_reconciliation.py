from datetime import datetime, timezone
from research_os.execution.order_intent import OrderIntent
from research_os.execution.reconciliation import ReconciliationAction, ReconciliationEngine, RemoteOrderState
from research_os.execution.service import ExecutionRecord, ExecutionStatus

def record(status):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    intent=OrderIntent("sig","BTCUSDT",__import__("research_os.execution.order_intent",fromlist=["OrderSide"]).OrderSide.BUY,__import__("research_os.execution.order_intent",fromlist=["OrderType"]).OrderType.LIMIT,1,100,95,110,now,"rs-sig")
    return ExecutionRecord("rs-sig","sig",status,now,now,intent)

def test_missing_remote_state_requires_investigation_for_inflight():
    r=ReconciliationEngine().reconcile(record(ExecutionStatus.SUBMITTED),None)
    assert r.action is ReconciliationAction.INVESTIGATE

def test_matching_state_is_noop():
    r=ReconciliationEngine().reconcile(record(ExecutionStatus.SUBMITTED),RemoteOrderState("rs-sig",ExecutionStatus.SUBMITTED))
    assert r.action is ReconciliationAction.NOOP

def test_remote_fill_can_update_nonterminal_local_state():
    r=ReconciliationEngine().reconcile(record(ExecutionStatus.SUBMITTED),RemoteOrderState("rs-sig",ExecutionStatus.FILLED,"ex-1"))
    assert r.action is ReconciliationAction.UPDATE

def test_local_terminal_mismatch_is_not_silently_overwritten():
    r=ReconciliationEngine().reconcile(record(ExecutionStatus.FILLED),RemoteOrderState("rs-sig",ExecutionStatus.CANCELLED))
    assert r.action is ReconciliationAction.INVESTIGATE
