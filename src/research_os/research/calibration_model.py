"""Frozen, content-addressed TP1 calibration artifacts and chronological training."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_os.intelligence.probability import CalibrationSample
from research_os.research.calibration import CalibrationLab
from research_os.research.temperature_scaling import TemperatureScaler

TARGET = "confirmed-tp1-within-horizon-v1"


def digest(value) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ForecastSample:
    signal_id: str
    symbol: str
    direction: str
    decision_time: datetime
    label_available_at: datetime
    score: float
    status: str
    context_id: str

    @property
    def label(self):
        # This predicts confirmed success under the persisted simulator, not profitability.
        return 1 if self.status == "win" else 0


class ArtifactSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AcceptanceGates(ArtifactSchema):
    min_train: int = Field(default=200, ge=20)
    min_validation: int = Field(default=100, ge=20)
    min_test: int = Field(default=100, ge=20)
    min_each_class: int = Field(default=10, ge=2)
    min_actionable: int = Field(default=30, ge=10)
    max_ece: float = Field(default=0.05, ge=0, le=1)
    max_mce: float = Field(default=0.15, ge=0, le=1)
    max_brier: float = Field(default=0.25, ge=0, le=1)


class Partition(ArtifactSchema):
    samples: int = Field(ge=0)
    successes: int = Field(ge=0)
    start: datetime
    end: datetime
    labels_until: datetime


class HoldoutMetrics(ArtifactSchema):
    brier: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)
    ece: float = Field(ge=0, le=1)
    mce: float = Field(ge=0, le=1)
    raw_log_loss: float = Field(ge=0)
    constant_log_loss: float = Field(ge=0)
    constant_brier: float = Field(ge=0, le=1)
    out_of_support: int = Field(ge=0)
    actionable_samples: int = Field(ge=0)
    actionable_successes: int = Field(ge=0)
    actionable_error: float = Field(ge=0, le=1)


class CalibrationArtifact(ArtifactSchema):
    schema_version: Literal["tp1-calibration-v1"] = "tp1-calibration-v1"
    target: Literal["confirmed-tp1-within-horizon-v1"] = TARGET
    symbol: str
    direction: Literal["long", "short"]
    context_id: str
    dataset_sha256: str
    created_at: datetime
    temperature: float = Field(ge=0.05, le=20)
    decision_threshold: float = Field(ge=0, le=1)
    score_min: float = Field(ge=0, le=1)
    score_max: float = Field(ge=0, le=1)
    train: Partition
    validation: Partition
    test: Partition
    gates: AcceptanceGates
    metrics: HoldoutMetrics

    @property
    def model_id(self) -> str:
        return digest(self.model_dump(mode="json"))

    def rejection_reasons(self) -> tuple[str, ...]:
        reasons = []
        for name, part, minimum in (
            ("train", self.train, self.gates.min_train),
            ("validation", self.validation, self.gates.min_validation),
            ("test", self.test, self.gates.min_test),
        ):
            if part.samples < minimum:
                reasons.append(f"insufficient {name} samples")
            if min(part.successes, part.samples - part.successes) < self.gates.min_each_class:
                reasons.append(f"insufficient {name} class support")
            if any(t.tzinfo is None for t in (part.start, part.end, part.labels_until)):
                reasons.append(f"naive {name} timestamps")
            elif not part.start <= part.end <= part.labels_until:
                reasons.append(f"invalid {name} timestamps")
        if not reasons:
            if (
                self.train.labels_until >= self.validation.start
                or self.validation.labels_until >= self.test.start
            ):
                reasons.append("overlapping information boundaries")
            if self.created_at.tzinfo is None or self.created_at < self.test.labels_until:
                reasons.append("artifact predates test labels")
        if self.score_min >= self.score_max:
            reasons.append("insufficient score range")
        m = self.metrics
        if m.actionable_samples < self.gates.min_actionable:
            reasons.append("insufficient actionable OOS support")
        if (
            min(m.actionable_successes, m.actionable_samples - m.actionable_successes)
            < self.gates.min_each_class
        ):
            reasons.append("insufficient actionable class support")
        if m.actionable_error > self.gates.max_ece:
            reasons.append("actionable calibration error above gate")
        if m.out_of_support:
            reasons.append("test scores outside fitted support")
        if m.ece > self.gates.max_ece:
            reasons.append("ECE above gate")
        if m.mce > self.gates.max_mce:
            reasons.append("MCE above gate")
        if m.brier > self.gates.max_brier:
            reasons.append("Brier above gate")
        if m.log_loss > m.raw_log_loss + 1e-12:
            reasons.append("worse than raw score baseline")
        if m.log_loss >= m.constant_log_loss or m.brier >= m.constant_brier:
            reasons.append("no improvement over frozen train-prior baseline")
        return tuple(reasons)

    def validate_for_live(
        self, model_id: str, symbol: str, context_id: str, now: datetime, max_age_days: int = 30
    ) -> None:
        if model_id != self.model_id:
            raise ValueError("calibration artifact checksum mismatch")
        policy = AcceptanceGates().model_dump()
        for name, value in self.gates.model_dump().items():
            if (name.startswith("min_") and value < policy[name]) or (
                name.startswith("max_") and value > policy[name]
            ):
                raise ValueError("calibration artifact weakens live acceptance policy")
        reasons = self.rejection_reasons()
        if reasons:
            raise ValueError("calibration rejected: " + "; ".join(reasons))
        if self.symbol != symbol or self.context_id != context_id:
            raise ValueError("calibration context mismatch")
        if (
            max_age_days <= 0
            or not self.created_at <= now
            or not timedelta(0) <= now - self.test.labels_until <= timedelta(days=max_age_days)
        ):
            raise ValueError("calibration artifact is stale or from the future")


def fit_artifact(
    rows,
    *,
    symbol: str,
    direction: str,
    context_id: str,
    gates: AcceptanceGates | None = None,
    now: datetime | None = None,
    decision_threshold: float = 0.7,
):
    """Freeze transform on train/validation, then inspect untouched test once."""
    gates = gates or AcceptanceGates()
    now = now or datetime.now(UTC)
    ordered = sorted(rows, key=lambda row: (row.decision_time, row.signal_id))
    if not ordered:
        raise ValueError("no eligible forecasts with matching provenance")
    if len({row.signal_id for row in ordered}) != len(ordered):
        raise ValueError("duplicate forecast IDs")
    for row in ordered:
        if row.symbol != symbol or row.direction != direction or row.context_id != context_id:
            raise ValueError("mixed forecast context")
        if row.status not in ("win", "loss", "expired", "ambiguous"):
            raise ValueError("unresolved forecast label")
        if row.decision_time.tzinfo is None or row.label_available_at.tzinfo is None:
            raise ValueError("forecast timestamps must be timezone-aware")
        if not row.decision_time < row.label_available_at <= now:
            raise ValueError("label unavailable at fitting time")
        if not isfinite(row.score) or not 0 <= row.score <= 1:
            raise ValueError("invalid forecast score")
    a, b = int(len(ordered) * 0.6), int(len(ordered) * 0.8)
    train = ordered[:a]
    if not train:
        raise ValueError("empty training partition")
    train_boundary = max(row.label_available_at for row in train)
    validation = [row for row in ordered[a:b] if row.decision_time > train_boundary]
    if not validation:
        raise ValueError("purge removed validation partition")
    validation_boundary = max(row.label_available_at for row in validation)
    test = [row for row in ordered[b:] if row.decision_time > validation_boundary]
    if not test:
        raise ValueError("purge removed test partition")
    for name, part, minimum in (
        ("train", train, gates.min_train),
        ("validation", validation, gates.min_validation),
        ("test", test, gates.min_test),
    ):
        if (
            len(part) < minimum
            or min(sum(row.label for row in part), sum(1 - row.label for row in part))
            < gates.min_each_class
        ):
            raise ValueError(f"insufficient {name} samples or class support after purge")
    sample = lambda part: [CalibrationSample(row.score, row.label) for row in part]
    scaler = TemperatureScaler(min_improvement=1e-6)
    selected = scaler.fit_and_select(train=sample(train), validation=sample(validation))
    # TEST does not select temperature, thresholds, score support or constant prior.
    test_samples = sample(test)
    transformed = scaler.transform(test_samples, selected.selected_temperature)
    lab = CalibrationLab()
    report = lab.evaluate(transformed)
    raw = lab.evaluate(test_samples)
    prior = sum(row.label for row in train) / len(train)
    baseline = lab.evaluate([CalibrationSample(prior, row.label) for row in test])
    actionable = [sample for sample in transformed if sample.predicted >= decision_threshold]
    actionable_error = (
        abs(sum(x.predicted - x.outcome for x in actionable) / len(actionable))
        if actionable
        else 1.0
    )
    score_min = min(row.score for row in train + validation)
    score_max = max(row.score for row in train + validation)

    def partition(part):
        return Partition(
            samples=len(part),
            successes=sum(row.label for row in part),
            start=part[0].decision_time,
            end=part[-1].decision_time,
            labels_until=max(row.label_available_at for row in part),
        )

    artifact = CalibrationArtifact(
        symbol=symbol,
        direction=direction,
        context_id=context_id,
        dataset_sha256=digest(
            [
                {
                    **asdict(row),
                    "decision_time": row.decision_time.isoformat(),
                    "label_available_at": row.label_available_at.isoformat(),
                }
                for row in ordered
            ]
        ),
        created_at=now,
        temperature=selected.selected_temperature,
        decision_threshold=decision_threshold,
        score_min=score_min,
        score_max=score_max,
        train=partition(train),
        validation=partition(validation),
        test=partition(test),
        gates=gates,
        metrics=HoldoutMetrics(
            brier=report.brier,
            log_loss=report.log_loss,
            ece=report.expected_calibration_error,
            mce=report.max_calibration_error,
            raw_log_loss=raw.log_loss,
            constant_log_loss=baseline.log_loss,
            constant_brier=baseline.brier,
            out_of_support=sum(not score_min <= row.score <= score_max for row in test),
            actionable_samples=len(actionable),
            actionable_successes=sum(x.outcome for x in actionable),
            actionable_error=actionable_error,
        ),
    )
    return artifact
