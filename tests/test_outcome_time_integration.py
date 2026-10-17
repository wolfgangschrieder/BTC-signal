import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from research_os.market.models import Candle
from research_os.research.replay import ReplayCandle, ReplayEngine
from research_os.signals.models import SignalDirection
from research_os.signals.outcome_evaluator import SignalOutcomeEvaluator
from research_os.signals.outcome_repository import SignalOutcomeRepository
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome


@pytest.fixture
def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()
    engine.dispose()


def pending(db, decision, direction="long", **assumptions):
    outcome = SignalOutcome(
        "time-boundary-audit",
        "AUDIT-TIME-BTC",
        direction,
        decision,
        100,
        99 if direction == "long" else 101,
        101 if direction == "long" else 99,
        102,
        103,
        0.8,
        OutcomeStatus.PENDING,
        horizon_minutes=10,
        **assumptions,
    )
    SignalOutcomeRepository().record_pending(db, outcome)
    return outcome


def store_candle(db, at, high, low, available=None):
    available = available or at + timedelta(minutes=1)
    db.add(
        Candle(
            symbol="AUDIT-TIME-BTC",
            interval="1",
            event_time=at,
            ingestion_time=available,
            point_in_time_available_at=available,
            open=100,
            high=high,
            low=low,
            close=100,
            volume=1,
            source="audit",
        )
    )
    db.flush()
    return ReplayCandle(at, 100, high, low, 100, 1, available)


def status(db):
    return db.execute(
        text("SELECT status FROM signal_outcomes WHERE signal_id='time-boundary-audit'")
    ).scalar_one()


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("policy,expected", [("legacy-entry-only", "win"), ("conservative-midpoint-v2", "ambiguous")])
def test_delayed_decision_matches_replay_for_persisted_policy(db, direction, policy, expected):
    from types import SimpleNamespace

    t = datetime(2026, 1, 1, tzinfo=UTC)
    decision = t + timedelta(minutes=1, milliseconds=100)
    outcome = pending(db, decision, direction, execution_policy=policy)
    candles = [
        store_candle(db, t, 102, 98),
        store_candle(db, t + timedelta(minutes=1), 102, 98),
        store_candle(db, t + timedelta(minutes=2), 102, 98),
        store_candle(
            db,
            t + timedelta(minutes=3),
            101 if direction == "long" else 100,
            100 if direction == "long" else 99,
        ),
    ]
    assert SignalOutcomeEvaluator().resolve_pending(db, t + timedelta(minutes=5)) == 1
    assert status(db) == expected
    signal = SimpleNamespace(
        direction=SignalDirection(direction),
        levels=SimpleNamespace(
            entry_min=100,
            entry_max=100,
            stop_loss=outcome.stop_loss,
            tp1=outcome.tp1,
        ),
    )
    replay_status, score, _ = ReplayEngine(horizon_minutes=10, conservative_entry=policy != "legacy-entry-only")._future_outcome(
        signal, candles, decision
    )
    assert replay_status == status(db)
    assert score == (1 if expected == "win" else None)



def test_conservative_policy_marks_decision_minute_entry_and_target_ambiguous(db):
    from types import SimpleNamespace

    t = datetime(2026, 1, 1, tzinfo=UTC)
    decision = t + timedelta(minutes=1, milliseconds=100)
    outcome = pending(db, decision, "short", execution_policy="conservative-midpoint-v2")
    same_minute = store_candle(db, t + timedelta(minutes=1), 100.5, 98.5)
    next_minute = store_candle(db, t + timedelta(minutes=2), 99.5, 98.0)

    assert SignalOutcomeEvaluator().resolve_pending(db, t + timedelta(minutes=4)) == 1
    assert status(db) == "ambiguous"

    signal = SimpleNamespace(
        direction=SignalDirection.SHORT,
        levels=SimpleNamespace(
            entry_min=100,
            entry_max=100,
            stop_loss=outcome.stop_loss,
            tp1=outcome.tp1,
        ),
    )
    replay_status, score, _ = ReplayEngine(horizon_minutes=10, conservative_entry=True)._future_outcome(
        signal, [same_minute, next_minute], decision
    )
    assert replay_status == status(db)
    assert score is None

def test_outcome_waits_for_delayed_candle_availability(db):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t)
    store_candle(db, t + timedelta(minutes=1), 100, 100)
    store_candle(db, t + timedelta(minutes=2), 101, 100, available=t + timedelta(minutes=8))
    assert SignalOutcomeEvaluator().resolve_pending(db, t + timedelta(minutes=4)) == 0
    assert status(db) == "pending"
    assert SignalOutcomeEvaluator().resolve_pending(db, t + timedelta(minutes=9)) == 1
    assert status(db) == "win"


def test_empty_future_remains_pending_then_expires(db):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t)
    evaluator = SignalOutcomeEvaluator()
    assert evaluator.resolve_pending(db, t + timedelta(minutes=1)) == 0
    assert status(db) == "pending"
    assert evaluator.resolve_pending(db, t + timedelta(minutes=10)) == 1
    assert status(db) == "expired"


@pytest.mark.parametrize("policy,expected", [("legacy-entry-only", "win"), ("conservative-midpoint-v2", "ambiguous")])
def test_persisted_execution_policy_controls_entry_bar(db, policy, expected):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t, execution_policy=policy, fee_bps=10, slippage_bps=5)
    store_candle(db, t+timedelta(minutes=1), 102, 98)
    store_candle(db, t+timedelta(minutes=2), 102, 100)
    SignalOutcomeEvaluator().resolve_pending(db, t+timedelta(minutes=4))
    assert status(db) == expected
    row = db.execute(text("SELECT fee_bps,slippage_bps,execution_policy,realized_return FROM signal_outcomes WHERE signal_id='time-boundary-audit'")).mappings().one()
    assert row["fee_bps"] == 10 and row["slippage_bps"] == 5
    assert row["execution_policy"] == policy
    if expected == "win":
        assert row["realized_return"] < .01
    else:
        assert row["realized_return"] is None


def test_committed_cooldown_restore_query_returns_latest_per_direction(db):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t)
    db.execute(text("UPDATE signal_outcomes SET signal_time=:time WHERE signal_id='time-boundary-audit'"), {"time":t+timedelta(minutes=5)})
    rows = SignalOutcomeRepository().latest_emissions(db, "AUDIT-TIME-BTC")
    assert len(rows) == 1 and rows[0]["signal_time"] == t+timedelta(minutes=5)


@pytest.mark.parametrize('filled', [True, False])
def test_expiry_separates_unfilled_from_marked_hypothetical_position(db, filled):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t, fee_bps=5, slippage_bps=2)
    for minute in range(1, 10):
        store_candle(db, t+timedelta(minutes=minute), 100.5, 99.5 if filled else 100.2)
    SignalOutcomeEvaluator().resolve_pending(db, t+timedelta(minutes=11))
    row = db.execute(text("SELECT execution_state,horizon_return,realized_return FROM signal_outcomes WHERE signal_id='time-boundary-audit'")).mappings().one()
    assert row['execution_state'] == ('filled_expired' if filled else 'unfilled')
    assert row['realized_return'] is None
    if filled:
        assert float(row['horizon_return']) == pytest.approx((100*(1-.0002)-100*(1+.0002))/(100*(1+.0002))-.001)
    else:
        assert row['horizon_return'] is None


def test_forecast_resolves_after_trade_already_resolved_without_requiring_fill(db):
    from research_os.signals.forecast_evaluator import SignalForecastEvaluator
    t = datetime(2026, 1, 1, tzinfo=UTC)
    pending(db, t)
    store_candle(db, t-timedelta(minutes=1), 100, 100, available=t)
    for minute in range(15):
        store_candle(db, t+timedelta(minutes=minute), 102, 101)
    db.execute(text("UPDATE market.candles SET close=102 WHERE symbol='AUDIT-TIME-BTC' AND event_time>=:t"), {'t':t})
    db.execute(text("UPDATE signal_outcomes SET status='expired' WHERE signal_id='time-boundary-audit'"))
    assert SignalForecastEvaluator().resolve(db,t+timedelta(minutes=16)) == 1
    row = db.execute(text("SELECT * FROM signal_forecasts WHERE signal_id='time-boundary-audit' AND horizon_minutes=15")).mappings().one()
    assert row['status'] == 'completed'
    assert row['directional_return'] == pytest.approx(.02)
    assert row['reference_price'] == 100
