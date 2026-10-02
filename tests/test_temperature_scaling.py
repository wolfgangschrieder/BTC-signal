import math

import pytest

from research_os.intelligence.probability import CalibrationSample
from research_os.research.temperature_scaling import TemperatureScaler


def test_temperature_scaling_moves_overconfident_probabilities_toward_half():
    scaler = TemperatureScaler()

    assert scaler.apply(0.9, 2.0) < 0.9
    assert scaler.apply(0.1, 2.0) > 0.1
    assert scaler.apply(0.9, 0.5) > 0.9
    assert scaler.apply(0.5, 2.0) == pytest.approx(0.5)


def test_fit_reduces_train_log_loss_for_overconfident_samples():
    scaler = TemperatureScaler()
    samples = [
        CalibrationSample(0.9, 0),
        CalibrationSample(0.9, 1),
        CalibrationSample(0.8, 0),
        CalibrationSample(0.8, 1),
    ]

    fitted = scaler.fit(samples)

    assert fitted > 1.0
    transformed = scaler.transform(samples, fitted)
    assert scaler._log_loss(transformed, 1.0) < scaler._log_loss(samples, 1.0)


def test_validation_selects_frozen_temperature_without_touching_test():
    scaler = TemperatureScaler(min_improvement=0.0001)
    train = [
        CalibrationSample(0.9, 0),
        CalibrationSample(0.9, 1),
        CalibrationSample(0.8, 0),
        CalibrationSample(0.8, 1),
    ]
    validation = [
        CalibrationSample(0.9, 0),
        CalibrationSample(0.9, 1),
        CalibrationSample(0.8, 0),
        CalibrationSample(0.8, 1),
    ]

    result = scaler.fit_and_select(train=train, validation=validation)

    assert math.isfinite(result.fitted_temperature)
    assert result.selected_temperature >= scaler.min_temperature
    assert result.selected_temperature <= scaler.max_temperature
    assert result.validation_calibrated_log_loss <= result.validation_baseline_log_loss
    assert result.train_log_loss >= 0.0


def test_validation_can_reject_calibration():
    scaler = TemperatureScaler(min_improvement=100.0)
    samples = [
        CalibrationSample(0.2, 0),
        CalibrationSample(0.8, 1),
        CalibrationSample(0.3, 0),
        CalibrationSample(0.7, 1),
    ]

    result = scaler.fit_and_select(train=samples, validation=samples)

    assert result.accepted is False
    assert result.selected_temperature == 1.0


@pytest.mark.parametrize(
    "temperature",
    [0.0, -1.0, math.nan, math.inf],
)
def test_invalid_temperature_is_rejected(temperature):
    scaler = TemperatureScaler()
    with pytest.raises(ValueError):
        scaler.apply(0.5, temperature)


def test_empty_fit_inputs_are_rejected():
    scaler = TemperatureScaler()
    with pytest.raises(ValueError):
        scaler.fit([])
    with pytest.raises(ValueError):
        scaler.fit_and_select(train=[CalibrationSample(0.5, 1)], validation=[])
