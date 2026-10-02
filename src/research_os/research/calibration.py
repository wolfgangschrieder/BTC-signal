from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

from research_os.intelligence.probability import CalibrationMetrics, CalibrationSample
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    lower: float
    upper: float
    samples: int
    predicted_mean: float
    actual_rate: float
    calibration_error: float


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    samples: int
    brier: float
    log_loss: float
    buckets: tuple[CalibrationBucket, ...]
    max_calibration_error: float
    expected_calibration_error: float


class CalibrationLab:
    """Measures probability quality without changing the model or thresholds."""

    def __init__(self, bucket_count: int = 10):
        if bucket_count < 2:
            raise ValueError("bucket_count must be >= 2")
        self.bucket_count = bucket_count

    def evaluate(
        self,
        samples: list[CalibrationSample] | tuple[CalibrationSample, ...],
    ) -> CalibrationReport:
        if not samples:
            return CalibrationReport(0, 0.0, 0.0, (), 0.0, 0.0)

        groups = defaultdict(list)
        normalized: list[CalibrationSample] = []
        for sample in samples:
            p = float(sample.predicted)
            outcome = int(sample.outcome)
            if not isfinite(p) or not 0.0 <= p <= 1.0:
                raise ValueError("predicted probability must be finite and between 0 and 1")
            if outcome not in (0, 1):
                raise ValueError("calibration outcome must be 0 or 1")
            normalized.append(CalibrationSample(p, outcome))
            idx = min(self.bucket_count - 1, int(p * self.bucket_count))
            groups[idx].append((p, outcome))

        buckets = []
        for idx in range(self.bucket_count):
            rows = groups.get(idx, [])
            lower = idx / self.bucket_count
            upper = (idx + 1) / self.bucket_count
            if not rows:
                buckets.append(CalibrationBucket(lower, upper, 0, 0.0, 0.0, 0.0))
                continue
            predicted_mean = sum(p for p, _ in rows) / len(rows)
            actual_rate = sum(y for _, y in rows) / len(rows)
            buckets.append(
                CalibrationBucket(
                    lower,
                    upper,
                    len(rows),
                    predicted_mean,
                    actual_rate,
                    abs(predicted_mean - actual_rate),
                )
            )

        nonempty = [bucket for bucket in buckets if bucket.samples]
        ece = sum(bucket.samples * bucket.calibration_error for bucket in nonempty) / len(normalized)
        mce = max((bucket.calibration_error for bucket in nonempty), default=0.0)
        return CalibrationReport(
            len(normalized),
            CalibrationMetrics.brier(normalized),
            CalibrationMetrics.log_loss(normalized),
            tuple(buckets),
            mce,
            ece,
        )

    @staticmethod
    def from_signal_outcomes(
        outcomes: list[SignalOutcome] | tuple[SignalOutcome, ...],
    ) -> list[CalibrationSample]:
        """Build TP1-success calibration labels; expired outcomes are excluded."""
        return [
            CalibrationSample(float(outcome.probability), 1 if outcome.status is OutcomeStatus.WIN else 0)
            for outcome in outcomes
            if outcome.status in (OutcomeStatus.WIN, OutcomeStatus.LOSS)
        ]

    @staticmethod
    def from_outcomes(rows):
        """Backward-compatible adapter for repository/dict rows."""
        samples = []
        for row in rows:
            status = row["status"]
            if status in ("win", "loss"):
                samples.append(
                    CalibrationSample(
                        float(row["probability"]),
                        1 if status == "win" else 0,
                    )
                )
        return samples
