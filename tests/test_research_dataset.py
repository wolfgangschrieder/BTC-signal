from datetime import datetime, timedelta, timezone

import pytest

from research_os.intelligence.events import EventCategory, EventImpact, ExternalEvent
from research_os.research.replay import ReplayCandle
from research_os.research.research_dataset import ResearchDatasetBuilder


def candle(t, close, *, pit=None, high=None, low=None):
    return ReplayCandle(t, close, high if high is not None else close, low if low is not None else close, close, 1.0, pit)


def event(event_id, event_time, available_at):
    return ExternalEvent(event_id, event_id, "test", event_time, available_at, EventCategory.MACRO, EventImpact.HIGH, 0.9, 0.5, 0.8)


def test_dataset_joins_pit_evidence_to_future_outcome():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    candles = [candle(t, 100.0, pit=t), candle(t + timedelta(minutes=1), 101.0, pit=t + timedelta(minutes=1)), candle(t + timedelta(minutes=2), 102.0, pit=t + timedelta(minutes=2))]
    events = [event("known", t - timedelta(minutes=1), t - timedelta(seconds=30))]
    dataset = ResearchDatasetBuilder().build("BTCUSDT", [t], candles, features_by_time={t: {"x": 1.5, "missing": None}}, external_events=events, horizon_minutes=2)
    assert len(dataset.rows) == 1
    row = dataset.rows[0]
    assert row.entry_price == 100.0
    assert row.return_pct == pytest.approx(0.02)
    assert row.external_event_ids == ("known",)
    assert row.features == (("x", 1.5),)
    assert ResearchDatasetBuilder.audit_pit(dataset, events) == ()


def test_future_outcome_is_never_available_at_decision_time():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    candles = [candle(t, 100.0, pit=t), candle(t + timedelta(minutes=1), 101.0, pit=t + timedelta(hours=1)), candle(t + timedelta(minutes=2), 102.0, pit=t + timedelta(hours=1))]
    dataset = ResearchDatasetBuilder().build("BTCUSDT", [t], candles, horizon_minutes=2)
    assert len(dataset.rows) == 1
    assert dataset.rows[0].outcome_time > t


def test_decision_candle_with_future_pit_is_rejected():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    dataset = ResearchDatasetBuilder().build("BTCUSDT", [t], [candle(t, 100.0, pit=t + timedelta(seconds=1))], horizon_minutes=1)
    assert dataset.rows == ()
    assert dataset.skipped == 1


def test_chronological_split_purges_overlapping_outcomes():
    t = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    candles = [candle(t + timedelta(minutes=i), 100.0 + i, pit=t + timedelta(minutes=i)) for i in range(5)]
    dataset = ResearchDatasetBuilder().build("BTCUSDT", [t + timedelta(minutes=i) for i in range(4)], candles, horizon_minutes=1)
    train, test = ResearchDatasetBuilder.chronological_split(dataset, 0.5)
    assert len(train.rows) == 2
    assert len(test.rows) == 1
    assert train.rows[-1].decision_time < test.rows[0].decision_time
    assert train.rows[-1].outcome_time < test.rows[0].decision_time
    assert test.skipped == 1
