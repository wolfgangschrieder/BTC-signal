import math
from datetime import datetime, timezone

import pytest

from research_os.intelligence.probability import CalibrationSample
from research_os.research.calibration import CalibrationLab
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome


def make_outcome(status, probability):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SignalOutcome(
        "signal",
        "BTCUSDT",
        "long",
        t,
        100.0,
        99.0,
        101.0,
        102.0,
        103.0,
        probability,
        status,
    )


def test_calibration_perfect():
    report = CalibrationLab().evaluate([
        CalibrationSample(.2, 0),
        CalibrationSample(.8, 1),
        CalibrationSample(.7, 1),
        CalibrationSample(.3, 0),
    ])
    assert report.samples == 4
    assert abs(report.brier - 0.065) < 1e-12
    assert report.expected_calibration_error > 0


def test_empty_calibration():
    report = CalibrationLab().evaluate([])
    assert report.samples == 0
    assert report.buckets == ()


def test_bucket_boundaries():
    report = CalibrationLab(bucket_count=5).evaluate([
        CalibrationSample(0.0, 0),
        CalibrationSample(.999, 1),
    ])
    assert report.buckets[0].samples == 1
    assert report.buckets[4].samples == 1


@pytest.mark.parametrize(
    "sample",
    [CalibrationSample(math.nan, 1), CalibrationSample(1.1, 1), CalibrationSample(-0.1, 0)],
)
def test_invalid_probability_is_rejected(sample):
    with pytest.raises(ValueError):
        CalibrationLab().evaluate([sample])


def test_invalid_outcome_is_rejected():
    with pytest.raises(ValueError):
        CalibrationLab().evaluate([CalibrationSample(.5, 2)])


def test_signal_outcome_adapter_excludes_expired():
    samples = CalibrationLab.from_signal_outcomes([
        make_outcome(OutcomeStatus.WIN, .8),
        make_outcome(OutcomeStatus.LOSS, .6),
        make_outcome(OutcomeStatus.EXPIRED, .9),
    ])
    assert samples == [CalibrationSample(.8, 1), CalibrationSample(.6, 0)]
