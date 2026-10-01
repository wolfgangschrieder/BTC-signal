from datetime import datetime, timezone
import pytest
from research_os.execution.adapter import PaperExecutionAdapter
from research_os.execution.confirmation import HumanConfirmationService
from research_os.execution.guard import ExecutionGuardContext
from research_os.execution.service import ExecutionService, ExecutionStatus
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult

def make_signal():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    levels=SignalLevels(100,101,95,110,115,120,2,3,4)
    return SignalResult("BTCUSDT",now,SignalDirection.LONG,.82,.1,levels,.6,2,("x",),())

def confirmed(signal):
    svc=HumanConfirmationService()
    return svc.confirm(signal.signal_id,signal.timestamp) if False else svc.create(signal,signal.timestamp)

def test_paper_adapter_submits_without_exchange():
    signal=make_signal()
    c=HumanConfirmationService(); confirmation=c.create(signal,signal.timestamp); confirmation=c.confirm(signal.signal_id,signal.timestamp)
    adapter=PaperExecutionAdapter()
    service=ExecutionService(adapter=adapter)
    record=service.prepare(signal,confirmation,ExecutionGuardContext(signal.timestamp,100.5),1)
    submitted=service.submit(record.client_order_id,signal.timestamp)
    assert submitted.status is ExecutionStatus.SUBMITTED
    assert submitted.exchange_order_id=="paper-"+record.client_order_id
    assert len(adapter.submissions)==1

def test_paper_adapter_can_reject():
    signal=make_signal()
    c=HumanConfirmationService(); confirmation=c.create(signal,signal.timestamp); confirmation=c.confirm(signal.signal_id,signal.timestamp)
    service=ExecutionService(adapter=PaperExecutionAdapter(accept=False))
    record=service.prepare(signal,confirmation,ExecutionGuardContext(signal.timestamp,100.5),1)
    assert service.submit(record.client_order_id,signal.timestamp).status is ExecutionStatus.REJECTED

def test_submit_requires_adapter():
    signal=make_signal()
    c=HumanConfirmationService(); confirmation=c.create(signal,signal.timestamp); confirmation=c.confirm(signal.signal_id,signal.timestamp)
    service=ExecutionService()
    record=service.prepare(signal,confirmation,ExecutionGuardContext(signal.timestamp,100.5),1)
    with pytest.raises(RuntimeError):
        service.submit(record.client_order_id,signal.timestamp)
