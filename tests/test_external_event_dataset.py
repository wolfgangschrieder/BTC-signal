from datetime import datetime, timedelta, timezone

import pytest

from research_os.intelligence.events import EventCategory, EventImpact, ExternalEvent
from research_os.research.external_event_dataset import ExternalEventDatasetBuilder


def event(event_id, event_time, available_at, *, relevance=0.9):
    return ExternalEvent(
        event_id=event_id,
        title=event_id,
        source="test",
        event_time=event_time,
        point_in_time_available_at=available_at,
        category=EventCategory.MACRO,
        impact=EventImpact.HIGH,
        relevance=relevance,
        sentiment=0.5,
        confidence=0.8,
    )


def test_dataset_contains_only_pit_available_events():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    events = [
        event("visible", t - timedelta(minutes=5), t - timedelta(minutes=4)),
        event("late", t - timedelta(minutes=3), t + timedelta(minutes=1)),
        event("future", t + timedelta(minutes=1), t + timedelta(minutes=1)),
    ]

    dataset = ExternalEventDatasetBuilder().build(
        "BTCUSDT",
        [t],
        events,
        lookback_seconds=600,
    )

    assert [row.event_id for row in dataset.rows] == ["visible"]
    assert dataset.decision_times == 1
    assert dataset.decisions_with_events == 1
    assert ExternalEventDatasetBuilder.audit_pit(dataset) == ()


def test_dataset_is_deterministic_for_reordered_inputs():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    events = [
        event("b", t - timedelta(minutes=2), t - timedelta(minutes=1)),
        event("a", t - timedelta(minutes=2), t - timedelta(minutes=1)),
    ]

    builder = ExternalEventDatasetBuilder()
    first = builder.build("BTCUSDT", [t], events)
    second = builder.build("BTCUSDT", [t], list(reversed(events)))

    assert first == second
    assert [row.event_id for row in first.rows] == ["a", "b"]


def test_dataset_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        ExternalEventDatasetBuilder().build("BTCUSDT", [], [], lookback_seconds=-1)
    with pytest.raises(ValueError):
        ExternalEventDatasetBuilder().build("BTCUSDT", [], [], min_relevance=1.1)


def test_pit_audit_detects_corrupted_dataset_row():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    dataset = ExternalEventDatasetBuilder().build(
        "BTCUSDT",
        [t],
        [event("visible", t - timedelta(minutes=1), t - timedelta(seconds=30))],
    )

    from dataclasses import replace
    corrupted = replace(
        dataset,
        rows=(
            replace(dataset.rows[0], point_in_time_available_at=t + timedelta(seconds=1)),
        ),
    )

    violations = ExternalEventDatasetBuilder.audit_pit(corrupted)
    assert len(violations) == 1
    assert violations[0].event_id == "visible"
