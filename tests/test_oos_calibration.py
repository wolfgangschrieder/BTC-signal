from datetime import datetime, timedelta, timezone

import pytest

from research_os.research.oos_calibration import OOSCalibrationEvaluator
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome


def outcome(i: int, probability: float, status: OutcomeStatus) -> SignalOutcome:
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    return SignalOutcome(
        f"signal-{i}", "BTCUSDT", "long", t,
        100.0, 99.0, 101.0, 102.0, 103.0,
        probability, status,
    )


def test_oos_evaluator_uses_only_resolved_test_outcomes():
    train = [outcome(0, .8, OutcomeStatus.WIN)]
    validation = [outcome(1, .7, OutcomeStatus.LOSS)]
    test = [
        outcome(2, .8, OutcomeStatus.WIN),
        outcome(3, .2, OutcomeStatus.LOSS),
        outcome(4, .9, OutcomeStatus.EXPIRED),
    ]

    result = OOSCalibrationEvaluator(min_test_samples=2).evaluate(
        train=train, validation=validation, test=test
    )

    assert result.train_samples == 1
    assert result.validation_samples == 1
    assert result.test_samples == 2
    assert result.report.samples == 2
    assert result.accepted is True


def test_oos_evaluator_rejects_small_test_set():
    result = OOSCalibrationEvaluator(min_test_samples=3).evaluate(
        train=[outcome(0, .8, OutcomeStatus.WIN)],
        validation=[outcome(1, .7, OutcomeStatus.WIN)],
        test=[outcome(2, .8, OutcomeStatus.WIN)],
    )
    assert result.accepted is False
    assert "insufficient OOS samples" in result.rejection_reasons[0]


def test_oos_evaluator_applies_only_oos_acceptance_gates():
    result = OOSCalibrationEvaluator(
        min_test_samples=2,
        max_brier=.05,
    ).evaluate(
        train=[outcome(0, .5, OutcomeStatus.WIN)],
        validation=[outcome(1, .5, OutcomeStatus.WIN)],
        test=[
            outcome(2, .99, OutcomeStatus.LOSS),
            outcome(3, .99, OutcomeStatus.LOSS),
        ],
    )
    assert result.accepted is False
    assert any(reason.startswith("Brier") for reason in result.rejection_reasons)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_test_samples": 0},
        {"max_ece": -0.1},
        {"max_mce": float("inf")},
        {"max_brier": float("nan")},
    ],
)
def test_invalid_oos_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        OOSCalibrationEvaluator(**kwargs)
