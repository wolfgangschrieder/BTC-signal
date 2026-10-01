from datetime import datetime, timezone, timedelta
from research_os.execution.confirmation import HumanConfirmationService
from research_os.execution.guard import ExecutionGuard, ExecutionGuardContext
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult

def make_signal(now):
    levels=SignalLevels(100,101,95,110,115,120,2,3,4)
    return SignalResult("BTCUSDT",now,SignalDirection.LONG,.82,.1,levels,.6,2,("evidence",),())

def test_guard_allows_confirmed_fresh_signal():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    s=make_signal(now)
    svc=HumanConfirmationService(); c=svc.create(s,now); c=svc.confirm(s.signal_id,now)
    result=ExecutionGuard().validate(s,c,ExecutionGuardContext(now,100.5))
    assert result.allowed is True

def test_guard_rejects_price_move_and_existing_position():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    s=make_signal(now)
    svc=HumanConfirmationService(); c=svc.create(s,now); c=svc.confirm(s.signal_id,now)
    result=ExecutionGuard().validate(s,c,ExecutionGuardContext(now+timedelta(seconds=5),110,existing_position=True))
    assert result.allowed is False
    assert "price moved beyond entry tolerance" in result.reasons
    assert "existing position blocks duplicate execution" in result.reasons

def test_order_intent_is_deterministic():
    from research_os.execution.order_intent import OrderIntent, OrderSide
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    intent=OrderIntent.from_signal(make_signal(now),1.5,now)
    assert intent.side is OrderSide.BUY
    assert intent.client_order_id=="rs-"+make_signal(now).signal_id[:24]
