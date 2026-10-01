from datetime import datetime, timezone
import pytest
from research_os.notifications.telegram import TelegramFormatter
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult

def make_signal():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    return SignalResult("BTCUSDT",now,SignalDirection.LONG,.82,.1,SignalLevels(100,101,95,110,115,120,2,3,4),.6,2,("x",),())

def test_signal_contains_confirmation_buttons():
    s=make_signal()
    m=TelegramFormatter().format(s)
    assert ("confirm:"+s.signal_id) in dict(m.buttons)
    assert ("cancel:"+s.signal_id) in dict(m.buttons)

def test_callback_parser():
    assert TelegramFormatter.callback_action("confirm:abc") == ("confirm","abc")
    assert TelegramFormatter.callback_action("cancel:abc") == ("cancel","abc")
    with pytest.raises(ValueError):
        TelegramFormatter.callback_action("confirm")
    with pytest.raises(ValueError):
        TelegramFormatter.callback_action("hack:abc")
