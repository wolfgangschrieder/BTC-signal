import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from research_os.intelligence.event_repository import ExternalEventRepository
from research_os.intelligence.events import EventCategory, EventImpact, ExternalEvent


@pytest.fixture
def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.begin() as connection:
        yield connection
        connection.execute(
            text("DELETE FROM intelligence.external_events WHERE source=:source"),
            {"source": "integration-test"},
        )
    engine.dispose()


def make_event(event_id, event_time, available_at, *, title=None, relevance=0.9):
    return ExternalEvent(
        event_id=event_id,
        title=title or event_id,
        source="integration-test",
        event_time=event_time,
        point_in_time_available_at=available_at,
        category=EventCategory.MACRO,
        impact=EventImpact.HIGH,
        relevance=relevance,
        sentiment=0.5,
        confidence=0.8,
        payload={"integration": True},
    )


def test_external_event_repository_enforces_pit_and_deterministic_order(db):
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    repo = ExternalEventRepository()

    repo.save(db, make_event("visible", t, t + timedelta(minutes=1)))
    repo.save(db, make_event("late", t, t + timedelta(hours=2)))
    repo.save(db, make_event("future", t + timedelta(hours=1), t + timedelta(hours=1, minutes=1)))
    repo.save(
        db,
        make_event(
            "same-time-later-pit",
            t,
            t + timedelta(minutes=2),
            title="later PIT",
        ),
    )

    rows = repo.latest(db, t + timedelta(minutes=30), limit=10)

    assert [event.event_id for event in rows] == [
        "same-time-later-pit",
        "visible",
    ]
    assert all(event.point_in_time_available_at <= t + timedelta(minutes=30) for event in rows)
    assert all(event.event_time <= t + timedelta(minutes=30) for event in rows)


def test_external_event_repository_applies_lookback_and_relevance(db):
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    repo = ExternalEventRepository()

    repo.save(db, make_event("inside", t - timedelta(minutes=5), t - timedelta(minutes=4)))
    repo.save(db, make_event("old", t - timedelta(hours=2), t - timedelta(hours=1)))
    repo.save(db, make_event("low-relevance", t - timedelta(minutes=1), t, relevance=0.1))

    rows = repo.latest(
        db,
        t + timedelta(minutes=1),
        lookback_seconds=600,
        min_relevance=0.5,
        limit=10,
    )

    assert [event.event_id for event in rows] == ["inside"]
