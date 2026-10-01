from datetime import datetime, timezone, timedelta
import pytest
from research_os.execution.confirmation import HumanConfirmationService, ConfirmationStatus

def test_confirmation_expires_and_cannot_be_reused():
    from research_os.signals.models import SignalDirection, SignalResult
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    signal=SignalResult("BTCUSDT",now,SignalDirection.LONG,.8,.1,None,0,2,("x",),())
    svc=HumanConfirmationService(ttl_seconds=30)
    item=svc.create(signal,now)
    assert item.status is ConfirmationStatus.PENDING
    assert svc.get(signal.signal_id,now+timedelta(seconds=31)).status is ConfirmationStatus.EXPIRED
    with pytest.raises(ValueError):
        svc.confirm(signal.signal_id,now+timedelta(seconds=31))

def test_confirmation_is_one_shot():
    from research_os.signals.models import SignalDirection, SignalResult
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    signal=SignalResult("BTCUSDT",now,SignalDirection.SHORT,.8,.1,None,0,2,("x",),())
    svc=HumanConfirmationService()
    svc.create(signal,now)
    assert svc.confirm(signal.signal_id,now).status is ConfirmationStatus.CONFIRMED
    with pytest.raises(ValueError):
        svc.confirm(signal.signal_id,now)
