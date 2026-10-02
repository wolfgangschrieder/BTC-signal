from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from research_os.intelligence.probability import CalibrationSample
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome

from .calibration import CalibrationLab, CalibrationReport


@dataclass(frozen=True, slots=True)
class OOSCalibrationEvaluation:
    train_samples: int
    validation_samples: int
    test_samples: int
    report: CalibrationReport
    accepted: bool
    rejection_reasons: tuple[str, ...]


class OOSCalibrationEvaluator:
    """Evaluate an already-frozen probability model on a chronologically isolated OOS set.

    This class deliberately performs no fitting and no threshold tuning. Any calibration
    transform must be fitted on train/validation data and then passed in as frozen
    probabilities before this evaluator is called.
    """

    def __init__(
        self,
        *,
        bucket_count: int = 10,
        min_test_samples: int = 100,
        max_ece: float | None = None,
        max_mce: float | None = None,
        max_brier: float | None = None,
    ):
        if min_test_samples < 1:
            raise ValueError("min_test_samples must be >= 1")
        for name, value in (
            ("max_ece", max_ece),
            ("max_mce", max_mce),
            ("max_brier", max_brier),
        ):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and non-negative")
        self.lab = CalibrationLab(bucket_count)
        self.min_test_samples = min_test_samples
        self.max_ece = max_ece
        self.max_mce = max_mce
        self.max_brier = max_brier

    @staticmethod
    def samples_from_outcomes(
        outcomes: list[SignalOutcome] | tuple[SignalOutcome, ...],
    ) -> list[CalibrationSample]:
        return CalibrationLab.from_signal_outcomes(outcomes)

    def evaluate(
        self,
        *,
        train: list[SignalOutcome] | tuple[SignalOutcome, ...],
        validation: list[SignalOutcome] | tuple[SignalOutcome, ...],
        test: list[SignalOutcome] | tuple[SignalOutcome, ...],
    ) -> OOSCalibrationEvaluation:
        train_samples = self.samples_from_outcomes(train)
        validation_samples = self.samples_from_outcomes(validation)
        test_samples = self.samples_from_outcomes(test)

        report = self.lab.evaluate(test_samples)
        reasons: list[str] = []

        if len(test_samples) < self.min_test_samples:
            reasons.append(
                f"insufficient OOS samples: {len(test_samples)} < {self.min_test_samples}"
            )
        if self.max_ece is not None and report.expected_calibration_error > self.max_ece:
            reasons.append(
                f"ECE {report.expected_calibration_error:.6f} > {self.max_ece:.6f}"
            )
        if self.max_mce is not None and report.max_calibration_error > self.max_mce:
            reasons.append(
                f"MCE {report.max_calibration_error:.6f} > {self.max_mce:.6f}"
            )
        if self.max_brier is not None and report.brier > self.max_brier:
            reasons.append(f"Brier {report.brier:.6f} > {self.max_brier:.6f}")

        return OOSCalibrationEvaluation(
            len(train_samples),
            len(validation_samples),
            len(test_samples),
            report,
            not reasons,
            tuple(reasons),
        )
