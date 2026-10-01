from datetime import datetime, timedelta, timezone

from research_os.intelligence.event_repository import ExternalEventRepository
from research_os.intelligence.events import EventCategory, EventImpact, ExternalEvent


def test_repository_sql_contains_strict_pit_filters():
    import inspect
    source = inspect.getsource(ExternalEventRepository.latest)
    assert "point_in_time_available_at <= :decision_time" in source
    assert "event_time <= :decision_time" in source
    assert "ORDER BY event_time DESC, point_in_time_available_at DESC, source ASC, event_id ASC" in source


def test_repository_round_trip_mapping():
    t = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    row = {"event_id": "e1", "title": "event", "source": "fixture",
           "event_time": t, "point_in_time_available_at": t + timedelta(seconds=1),
           "category": "macro", "impact": "high", "relevance": 0.9,
           "sentiment": 0.5, "confidence": 0.8, "payload": {"x": 1}}
    event = ExternalEventRepository._to_event(row)
    assert event.event_id == "e1"
    assert event.category is EventCategory.MACRO
    assert event.impact is EventImpact.HIGH
    assert event.payload == {"x": 1}
