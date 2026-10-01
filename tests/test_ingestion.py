from datetime import datetime, timezone

from research_os.data.ingestion import event_fingerprint
from research_os.data.models import EventType, RawEvent


def make_event(price: str = "100") -> RawEvent:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return RawEvent(
        source="bybit",
        event_type=EventType.TRADE,
        symbol="BTCUSDT",
        event_time=ts,
        ingestion_time=ts,
        point_in_time_available_at=ts,
        payload={"price": price, "size": "1"},
    )


def test_same_event_has_stable_fingerprint():
    assert event_fingerprint(make_event()) == event_fingerprint(make_event())


def test_payload_change_changes_fingerprint():
    assert event_fingerprint(make_event()) != event_fingerprint(make_event("101"))
