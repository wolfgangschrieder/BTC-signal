import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from research_os.research.calibration_model import ForecastSample, fit_artifact
from research_os.research.calibration_model_repository import CalibrationModelRepository
from research_os.signals.outcome_repository import SignalOutcomeRepository
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome


@pytest.fixture
def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL required for PostgreSQL integration")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()
    engine.dispose()


def test_forecast_provenance_selection_excludes_legacy_models_and_unavailable_labels(db):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    context = uuid4().hex
    repo = SignalOutcomeRepository()
    for i in range(5):
        signal_id = uuid4().hex
        outcome = SignalOutcome(
            signal_id,
            "MODEL-AUDIT",
            "long",
            start,
            100,
            99,
            101,
            102,
            103,
            0.8,
            OutcomeStatus.PENDING,
            horizon_minutes=60,
            execution_policy="conservative-midpoint-v2",
            research_score=None if i == 2 else 0.9,
            calibration_context="other" if i == 3 else context,
            probability_model_id="already-calibrated" if i == 4 else None,
        )
        repo.record_pending(db, outcome)
        repo.resolve(
            db,
            signal_id,
            (OutcomeStatus.EXPIRED, OutcomeStatus.AMBIGUOUS)[i % 2],
            resolved_at=start + timedelta(minutes=30),
        )
    model_repo = CalibrationModelRepository()
    assert not model_repo.load_samples(
        db,
        symbol="MODEL-AUDIT",
        direction="long",
        context_id=context,
        as_of=start + timedelta(minutes=45),
    )
    rows = model_repo.load_samples(
        db,
        symbol="MODEL-AUDIT",
        direction="long",
        context_id=context,
        as_of=start + timedelta(hours=2),
    )
    assert len(rows) == 2
    assert all(
        row.label == 0 and row.label_available_at == start + timedelta(hours=1) for row in rows
    )


def test_artifact_roundtrip_is_content_addressed_and_idempotent(db):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    context = uuid4().hex
    rows = []
    for i in range(600):
        high = i % 20 < 10
        success = i % 10 < (8 if high else 6)
        decision = start + timedelta(hours=2 * i)
        rows.append(
            ForecastSample(
                str(i),
                "BTCUSDT",
                "long",
                decision,
                decision + timedelta(minutes=61),
                0.9 if high else 0.7,
                "win" if success else "expired",
                context,
            )
        )
    artifact = fit_artifact(
        rows,
        symbol="BTCUSDT",
        direction="long",
        context_id=context,
        now=rows[-1].label_available_at + timedelta(hours=1),
    )
    assert not artifact.rejection_reasons()
    repository = CalibrationModelRepository()
    model_id = repository.save(db, artifact)
    assert repository.save(db, artifact) == model_id
    loaded = repository.load(db, model_id)
    assert loaded == artifact and loaded.model_id == model_id
    assert db.execute(
        text("SELECT accepted FROM intelligence.calibration_models WHERE model_id=:id"),
        {"id": model_id},
    ).scalar_one()
    with pytest.raises(ValueError, match="not found"):
        repository.load(db, "missing-model")


def test_selected_model_loads_and_emission_retains_raw_provenance(db, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from research_os.intelligence.models import AnalysisResult, EvidenceDirection
    from research_os.pipeline import live

    now = datetime.now(UTC)
    start = now - timedelta(days=50)
    context = live.LiveSignalService().calibration_context
    rows = []
    for i in range(600):
        decision = start + timedelta(hours=2 * i)
        high = i % 20 < 10
        success = i % 10 < (8 if high else 6)
        rows.append(
            ForecastSample(
                str(i),
                "BTCUSDT",
                "long",
                decision,
                decision + timedelta(minutes=61),
                0.9 if high else 0.7,
                "win" if success else "expired",
                context,
            )
        )
    artifact = fit_artifact(rows, symbol="BTCUSDT", direction="long", context_id=context, now=now)
    CalibrationModelRepository().save(db, artifact)
    monkeypatch.setattr(live, "SessionLocal", lambda: nullcontext(db))
    service = live.LiveSignalService(
        settings=SimpleNamespace(calibration_model_ids=artifact.model_id, environment="production")
    )
    service._load_calibration()
    analysis = AnalysisResult("BTCUSDT", now, EvidenceDirection.BULLISH, (), 5, 0, 0, True, "")
    probability = service.pipeline.probability.predict(analysis)
    signal = service.pipeline.signal.build(analysis, probability, 100, 2)
    assert signal.direction.value == "long" and signal.probability_is_calibrated
    service._persist_emission(signal, "test")
    row = (
        db.execute(
            text(
                "SELECT research_score,probability_model_id,calibration_context FROM signal_outcomes WHERE signal_id=:id"
            ),
            {"id": signal.signal_id},
        )
        .mappings()
        .one()
    )
    assert row["research_score"] == probability.research_score
    assert row["probability_model_id"] == artifact.model_id
    assert row["calibration_context"] == context
