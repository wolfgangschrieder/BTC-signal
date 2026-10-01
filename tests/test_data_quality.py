from datetime import datetime, timedelta, timezone
from research_os.data.models import EventType, RawEvent, QualityCode
from research_os.data.quality import DataQualityEngine

def make_event(pit_offset=0):
    now=datetime.now(timezone.utc)
    return RawEvent(
        source="test",event_type=EventType.TRADE,symbol="BTCUSDT",
        event_time=now,ingestion_time=now,
        point_in_time_available_at=now+timedelta(seconds=pit_offset),
        payload={"price":"100000","size":"0.01"},
    )

def test_pit_violation_is_detected():
    event=make_event(60)
    issues=DataQualityEngine().validate_event(event,event.point_in_time_available_at-timedelta(seconds=1))
    assert any(x.code is QualityCode.PIT_VIOLATION for x in issues)

def test_valid_event_has_no_pit_error():
    event=make_event()
    issues=DataQualityEngine().validate_event(event,event.point_in_time_available_at)
    assert not any(x.code is QualityCode.PIT_VIOLATION for x in issues)
