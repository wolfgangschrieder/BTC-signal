from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from research_os.intelligence.calibrated_probability import FrozenCalibratedProbabilityEngine
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.pipeline.live import LiveSignalService
from research_os.research.calibration_model import ForecastSample, fit_artifact

START = datetime(2026, 1, 1, tzinfo=UTC)


def samples(context="test-context", count=600):
    result = []
    for i in range(count):
        high = i % 20 < 10
        success = i % 10 < (8 if high else 6)
        decision = START + timedelta(hours=2 * i)
        result.append(
            ForecastSample(
                str(i),
                "BTCUSDT",
                "long",
                decision,
                decision + timedelta(minutes=61),
                0.9 if high else 0.7,
                "win" if success else ("loss", "expired", "ambiguous")[i % 3],
                context,
            )
        )
    return result


@pytest.fixture(scope="module")
def artifact():
    rows = samples()
    return fit_artifact(
        rows,
        symbol="BTCUSDT",
        direction="long",
        context_id="test-context",
        now=rows[-1].label_available_at + timedelta(hours=1),
    )


def test_frozen_artifact_includes_all_completed_outcomes_and_passes_oos(artifact):
    assert artifact.rejection_reasons() == ()
    assert (
        artifact.train.samples == 360
        and artifact.validation.samples == artifact.test.samples == 120
    )
    assert artifact.train.successes == 252  # expired/ambiguous are included as non-success.
    assert artifact.temperature != 1
    assert artifact.metrics.log_loss < artifact.metrics.constant_log_loss
    assert artifact.target == "confirmed-tp1-within-horizon-v1"
    assert artifact.train.labels_until < artifact.validation.start
    assert artifact.validation.labels_until < artifact.test.start


def test_holdout_labels_do_not_fit_temperature_or_support(artifact):
    rows = samples()
    changed = [
        replace(row, status="loss" if row.status == "win" else "win") if i >= 480 else row
        for i, row in enumerate(rows)
    ]
    other = fit_artifact(
        changed,
        symbol="BTCUSDT",
        direction="long",
        context_id="test-context",
        now=artifact.created_at,
    )
    assert other.temperature == artifact.temperature
    assert (other.score_min, other.score_max) == (artifact.score_min, artifact.score_max)
    assert other.rejection_reasons()
    assert other.dataset_sha256 != artifact.dataset_sha256


def test_label_boundaries_are_purged_and_unavailable_labels_rejected(artifact):
    rows = samples()
    delayed = [
        replace(row, label_available_at=rows[380].decision_time) if i == 359 else row
        for i, row in enumerate(rows)
    ]
    with pytest.raises(ValueError, match="insufficient validation"):
        fit_artifact(
            delayed,
            symbol="BTCUSDT",
            direction="long",
            context_id="test-context",
            now=artifact.created_at,
        )
    with pytest.raises(ValueError, match="unavailable"):
        fit_artifact(rows, symbol="BTCUSDT", direction="long", context_id="test-context", now=START)


@pytest.mark.parametrize("change", ["duplicate", "context", "unresolved", "score"])
def test_invalid_training_data_rejected(artifact, change):
    rows = samples()
    if change == "duplicate":
        rows.append(rows[0])
    if change == "context":
        rows[0] = replace(rows[0], context_id="different")
    if change == "unresolved":
        rows[0] = replace(rows[0], status="pending")
    if change == "score":
        rows[0] = replace(rows[0], score=float("nan"))
    with pytest.raises(ValueError):
        fit_artifact(
            rows,
            symbol="BTCUSDT",
            direction="long",
            context_id="test-context",
            now=artifact.created_at,
        )


def test_loader_rejects_changed_checksum_context_staleness_and_rejected_metrics(artifact):
    args = dict(
        model_id=artifact.model_id,
        symbol="BTCUSDT",
        context_id="test-context",
        now=artifact.created_at,
    )
    artifact.validate_for_live(**args)
    with pytest.raises(ValueError, match="checksum"):
        artifact.model_copy(update={"temperature": 2}).validate_for_live(**args)
    with pytest.raises(ValueError, match="context"):
        artifact.validate_for_live(**{**args, "context_id": "other"})
    with pytest.raises(ValueError, match="stale"):
        artifact.validate_for_live(**{**args, "now": artifact.created_at + timedelta(days=31)})
    rejected = artifact.model_copy(
        update={"metrics": artifact.metrics.model_copy(update={"ece": 0.9})}
    )
    with pytest.raises(ValueError, match="rejected"):
        rejected.validate_for_live(**{**args, "model_id": rejected.model_id})


def test_live_prediction_has_target_and_abstains_for_unsupported_direction_score_time(artifact):
    engine = FrozenCalibratedProbabilityEngine(
        artifact,
        model_id=artifact.model_id,
        symbol="BTCUSDT",
        context_id="test-context",
        now=artifact.created_at,
    )
    analysis = AnalysisResult(
        "BTCUSDT", artifact.created_at, EvidenceDirection.BULLISH, (), 5, 0, 0, True, ""
    )
    probability = engine.predict(analysis)
    assert probability.calibrated and probability.model_id == artifact.model_id
    assert 0.7 <= probability.research_score <= 0.9
    assert probability.long + probability.short + probability.no_signal == pytest.approx(1)
    assert (
        engine.predict(
            replace(analysis, direction=EvidenceDirection.BEARISH, bullish_score=0, bearish_score=5)
        ).no_signal
        == 1
    )
    assert engine.predict(replace(analysis, bullish_score=0.1)).no_signal == 1
    assert engine.predict(replace(analysis, timestamp=START)).no_signal == 1
    assert (
        engine.predict(
            replace(analysis, timestamp=artifact.created_at + timedelta(days=31))
        ).no_signal
        == 1
    )


def test_runtime_context_changes_with_costs_and_threshold_but_not_model_selection():
    base = LiveSignalService()
    assert (
        base.calibration_context
        != LiveSignalService(settings=SimpleNamespace(execution_fee_bps=6)).calibration_context
    )
    assert (
        base.calibration_context
        != LiveSignalService(
            settings=SimpleNamespace(signal_min_probability=0.6)
        ).calibration_context
    )
    assert (
        base.calibration_context
        == LiveSignalService(
            settings=SimpleNamespace(calibration_model_ids="selected")
        ).calibration_context
    )


def test_model_load_failure_prevents_starting_stream(monkeypatch):
    import asyncio

    service = LiveSignalService(settings=SimpleNamespace(calibration_model_ids="missing"))

    def failed():
        raise ValueError("calibration model not found")

    monkeypatch.setattr(service, "_load_calibration", failed)
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(service.run())


def test_artifact_rejects_model_without_actionable_oos_support(artifact):
    rows = samples()
    rejected = fit_artifact(
        rows,
        symbol="BTCUSDT",
        direction="long",
        context_id="test-context",
        now=artifact.created_at,
        decision_threshold=0.99,
    )
    assert "insufficient actionable OOS support" in rejected.rejection_reasons()


def test_cli_rejection_does_not_publish_a_model(monkeypatch, capsys):
    from research_os import cli
    from research_os.research.calibration_model_repository import CalibrationModelRepository

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            raise AssertionError("must not commit without eligible data")

    monkeypatch.setattr(cli, "SessionLocal", Session)
    monkeypatch.setattr(CalibrationModelRepository, "load_samples", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        CalibrationModelRepository, "save", lambda *args: pytest.fail("must not save")
    )
    assert cli.calibration_fit("BTCUSDT", "long") == 2
    assert "no eligible forecasts" in capsys.readouterr().out


def test_registry_routes_both_directions_and_rejects_duplicate_models(artifact):
    from research_os.intelligence.calibrated_probability import FrozenCalibrationRegistry

    rows = [replace(row, direction="short") for row in samples()]
    short = fit_artifact(
        rows,
        symbol="BTCUSDT",
        direction="short",
        context_id="test-context",
        now=artifact.created_at,
    )
    args = dict(symbol="BTCUSDT", context_id="test-context", now=artifact.created_at)
    long_engine = FrozenCalibratedProbabilityEngine(artifact, model_id=artifact.model_id, **args)
    short_engine = FrozenCalibratedProbabilityEngine(short, model_id=short.model_id, **args)
    registry = FrozenCalibrationRegistry([long_engine, short_engine])
    analysis = AnalysisResult(
        "BTCUSDT", artifact.created_at, EvidenceDirection.BULLISH, (), 5, 0, 0, True, ""
    )
    assert registry.predict(analysis).model_id == artifact.model_id
    bearish = replace(
        analysis, direction=EvidenceDirection.BEARISH, bullish_score=0, bearish_score=5
    )
    assert registry.predict(bearish).model_id == short.model_id
    with pytest.raises(ValueError, match="duplicate"):
        FrozenCalibrationRegistry([long_engine, long_engine])
