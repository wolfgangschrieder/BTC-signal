from datetime import datetime, timedelta, timezone

import pytest

from research_os.intelligence.events import (
    EventCategory,
    EventImpact,
    ExternalEvent,
    ExternalEventEngine,
)


def event(event_id="e1", *, event_time=None, available_at=None, sentiment=0.5):
    event_time = event_time or datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    available_at = available_at or event_time + timedelta(seconds=5)
    return ExternalEvent(
        event_id=event_id,
        title="test event",
        source="test",
        event_time=event_time,
        point_in_time_available_at=available_at,
        category=EventCategory.MACRO,
        impact=EventImpact.HIGH,
        relevance=0.8,
        sentiment=sentiment,
        confidence=0.9,
    )


def test_external_event_rejects_pit_before_event():
    with pytest.raises(ValueError):
        event(available_at=datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc))


def test_engine_excludes_events_not_yet_available():
    t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    e = event(available_at=t + timedelta(seconds=1))
    snapshot = ExternalEventEngine().build(t, [e], as_of=t)
    assert snapshot.available is False
    assert snapshot.total_count == 0


def test_engine_excludes_future_events_and_old_events():
    t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    old = event("old", event_time=t - timedelta(hours=2), available_at=t - timedelta(hours=2))
    future = event("future", event_time=t + timedelta(seconds=1), available_at=t + timedelta(seconds=1))
    snapshot = ExternalEventEngine().build(t, [old, future], lookback_seconds=3600)
    assert snapshot.total_count == 0


def test_engine_calculates_weighted_sentiment_pit_safely():
    t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    a = event("a", sentiment=1.0, available_at=t)
    b = event("b", sentiment=-1.0, available_at=t)
    snapshot = ExternalEventEngine().build(t, [a, b], as_of=t)
    assert snapshot.total_count == 2
    assert snapshot.weighted_sentiment == pytest.approx(0.0)


def test_engine_orders_events_deterministically():
    t = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    a = event("a", available_at=t)
    b = event("b", available_at=t)
    snapshot = ExternalEventEngine().build(t, [b, a], as_of=t)
    assert [x.event_id for x in snapshot.events] == ["a", "b"]
