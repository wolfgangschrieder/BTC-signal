from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log

from research_os.intelligence.probability import CalibrationSample
from research_os.research.calibration import CalibrationLab


@dataclass(frozen=True, slots=True)
class TemperatureScalingResult:
    fitted_temperature: float
    selected_temperature: float
    train_log_loss: float
    validation_baseline_log_loss: float
    validation_calibrated_log_loss: float
    accepted: bool

    @property
    def improvement(self) -> float:
        return self.validation_baseline_log_loss - self.validation_calibrated_log_loss


class TemperatureScaler:
    """Research-only binary temperature scaling.

    The base probability model is never modified here. A temperature is fitted on
    TRAIN, then VALIDATION chooses whether the fitted transform (or a bounded set
    of nearby temperatures) is retained. TEST must be evaluated separately after
    the returned temperature has been frozen.
    """

    def __init__(
        self,
        *,
        min_temperature: float = 0.05,
        max_temperature: float = 20.0,
        epsilon: float = 1e-12,
        min_improvement: float = 0.0,
    ):
        if (
            not isfinite(min_temperature)
            or not isfinite(max_temperature)
            or min_temperature <= 0
            or max_temperature < min_temperature
        ):
            raise ValueError("invalid temperature bounds")
        if not isfinite(epsilon) or not 0 < epsilon < 0.5:
            raise ValueError("epsilon must be finite and between 0 and 0.5")
        if not isfinite(min_improvement) or min_improvement < 0:
            raise ValueError("min_improvement must be finite and non-negative")
        self.min_temperature = min_temperature
        self.max_temperature = max_temperature
        self.epsilon = epsilon
        self.min_improvement = min_improvement

    def transform(self, samples: list[CalibrationSample] | tuple[CalibrationSample, ...], temperature: float) -> list[CalibrationSample]:
        self._validate_temperature(temperature)
        return [
            CalibrationSample(self.apply(sample.predicted, temperature), sample.outcome)
            for sample in samples
        ]

    def apply(self, probability: float, temperature: float) -> float:
        self._validate_temperature(temperature)
        if not isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be finite and between 0 and 1")
        p = min(1.0 - self.epsilon, max(self.epsilon, probability))
        logit = log(p / (1.0 - p))
        scaled = logit / temperature
        if scaled >= 0:
            z = exp(-scaled)
            return 1.0 / (1.0 + z)
        z = exp(scaled)
        return z / (1.0 + z)

    def fit(self, train: list[CalibrationSample] | tuple[CalibrationSample, ...]) -> float:
        if not train:
            raise ValueError("train samples must not be empty")
        CalibrationLab().evaluate(train)

        # Optimize in log-temperature space. This keeps T > 0 and gives a
        # deterministic one-dimensional search without scipy or ML dependencies.
        lo = log(self.min_temperature)
        hi = log(self.max_temperature)
        phi = (1.0 + 5.0**0.5) / 2.0

        x1 = hi - (hi - lo) / phi
        x2 = lo + (hi - lo) / phi
        f1 = self._log_loss(train, exp(x1))
        f2 = self._log_loss(train, exp(x2))

        for _ in range(80):
            if f1 <= f2:
                hi, x2, f2 = x2, x1, f1
                x1 = hi - (hi - lo) / phi
                f1 = self._log_loss(train, exp(x1))
            else:
                lo, x1, f1 = x1, x2, f2
                x2 = lo + (hi - lo) / phi
                f2 = self._log_loss(train, exp(x2))

        return exp((lo + hi) / 2.0)

    def fit_and_select(
        self,
        *,
        train: list[CalibrationSample] | tuple[CalibrationSample, ...],
        validation: list[CalibrationSample] | tuple[CalibrationSample, ...],
    ) -> TemperatureScalingResult:
        if not validation:
            raise ValueError("validation samples must not be empty")

        fitted = self.fit(train)
        candidates = self._candidate_temperatures(fitted)

        baseline_loss = self._log_loss(validation, 1.0)
        best_temperature = 1.0
        best_loss = baseline_loss

        for temperature in candidates:
            loss = self._log_loss(validation, temperature)
            if loss < best_loss - 1e-15 or (
                abs(loss - best_loss) <= 1e-15 and temperature < best_temperature
            ):
                best_temperature = temperature
                best_loss = loss

        accepted = (
            best_temperature != 1.0
            and baseline_loss - best_loss >= self.min_improvement
        )
        selected = best_temperature if accepted else 1.0

        return TemperatureScalingResult(
            fitted_temperature=fitted,
            selected_temperature=selected,
            train_log_loss=self._log_loss(train, fitted),
            validation_baseline_log_loss=baseline_loss,
            validation_calibrated_log_loss=self._log_loss(validation, selected),
            accepted=accepted,
        )

    def _candidate_temperatures(self, fitted: float) -> tuple[float, ...]:
        values = {1.0, fitted}
        for multiplier in (0.5, 0.75, 1.0, 4.0 / 3.0, 2.0):
            values.add(
                min(
                    self.max_temperature,
                    max(self.min_temperature, fitted * multiplier),
                )
            )
        return tuple(sorted(values))

    def _log_loss(
        self,
        samples: list[CalibrationSample] | tuple[CalibrationSample, ...],
        temperature: float,
    ) -> float:
        transformed = self.transform(samples, temperature)
        return CalibrationLab().evaluate(transformed).log_loss

    def _validate_temperature(self, temperature: float) -> None:
        if (
            not isfinite(temperature)
            or temperature < self.min_temperature
            or temperature > self.max_temperature
        ):
            raise ValueError("temperature is outside configured bounds")
