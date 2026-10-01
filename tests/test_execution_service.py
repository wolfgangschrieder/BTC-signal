from datetime import datetime, timezone
import pytest
from research_os.execution.confirmation import HumanConfirmationService
from research_os.execution.guard import ExecutionGuardContext
from research_os.execution.service import ExecutionService, ExecutionStatus
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult

def make_signal(now):
    levels=SignalLevels(100,101,95,110,115,120,2,3,4)
    return SignalResult("BTCUSDT",now,SignalDirection.LONG,.82,.1,levels,.6,2,("evidence",),())

def test_prepare_is_idempotent():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    s=make_signal(now); svc_confirm=HumanConfirmationService(); c=svc_confirm.create(s,now); c=svc_confirm.confirm(s.signal_id,now)
    service=ExecutionService(); ctx=ExecutionGuardContext(now,100.5)
    a=service.prepare(s,c,ctx,1); b=service.prepare(s,c,ctx,1)
    assert a.client_order_id==b.client_order_id
    assert a.status is ExecutionStatus.CREATED
    assert len(a.client_order_id)==27

def test_state_machine_rejects_invalid_transition():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    s=make_signal(now); c=HumanConfirmationService().create(s,now)
    service=ExecutionService(); record=service.prepare(s,c,ExecutionGuardContext(now,100.5),1)
    assert record.status is ExecutionStatus.BLOCKED
    with pytest.raises(ValueError):
        service.transition(record.client_order_id,ExecutionStatus.FILLED,now)
