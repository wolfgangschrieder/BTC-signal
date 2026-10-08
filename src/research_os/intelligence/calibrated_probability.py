"""Explicitly selected frozen calibration; abstain outside validated context/support."""

from __future__ import annotations

from datetime import UTC, datetime

from research_os.intelligence.models import EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine, ProbabilityResult
from research_os.research.calibration_model import CalibrationArtifact
from research_os.research.temperature_scaling import TemperatureScaler


class FrozenCalibratedProbabilityEngine:
    def __init__(
        self,
        artifact: CalibrationArtifact,
        *,
        model_id: str,
        symbol: str,
        context_id: str,
        max_age_days: int = 30,
        now: datetime | None = None,
        decision_threshold: float | None = None,
    ):
        if decision_threshold is not None and artifact.decision_threshold != decision_threshold:
            raise ValueError("calibration decision threshold mismatch")
        artifact.validate_for_live(
            model_id, symbol, context_id, now or datetime.now(UTC), max_age_days
        )
        self.artifact = artifact
        self.model_id = model_id
        self.context_id = context_id
        self.max_age_days = max_age_days
        self.base = ProbabilityEngine()
        self.scaler = TemperatureScaler()
        self.version = "calibrated-tp1-v1:" + model_id

    def predict(self, analysis):
        # Validate against the decision clock as well: an artifact must never be
        # applied retrospectively to the data used to fit/validate it.
        try:
            self.artifact.validate_for_live(
                self.model_id,
                analysis.symbol,
                self.context_id,
                analysis.timestamp,
                self.max_age_days,
            )
        except ValueError:
            return ProbabilityResult(analysis.symbol, analysis.timestamp, 0, 0, 1, self.version)
        raw = self.base.predict(analysis)
        direction = (
            "long"
            if analysis.direction is EvidenceDirection.BULLISH
            else "short"
            if analysis.direction is EvidenceDirection.BEARISH
            else None
        )
        score = raw.long if direction == "long" else raw.short
        if (
            direction != self.artifact.direction
            or not self.artifact.score_min <= score <= self.artifact.score_max
        ):
            return ProbabilityResult(analysis.symbol, analysis.timestamp, 0, 0, 1, self.version)
        p = self.scaler.apply(score, self.artifact.temperature)
        return ProbabilityResult(
            analysis.symbol,
            analysis.timestamp,
            p if direction == "long" else 0,
            p if direction == "short" else 0,
            1 - p,
            self.version,
            calibrated=True,
            research_score=score,
            model_id=self.model_id,
            target=self.artifact.target,
        )


class FrozenCalibrationRegistry:
    """One explicitly pinned model per supported direction; no heuristic fallback."""

    def __init__(self, engines):
        self.engines = {}
        for engine in engines:
            direction = engine.artifact.direction
            if direction in self.engines:
                raise ValueError("duplicate calibrated direction")
            self.engines[direction] = engine
        if not self.engines:
            raise ValueError("no calibration models selected")
        self.version = "calibrated-registry-v1:" + ":".join(
            sorted(engine.model_id for engine in engines)
        )

    def predict(self, analysis):
        direction = (
            "long"
            if analysis.direction is EvidenceDirection.BULLISH
            else "short"
            if analysis.direction is EvidenceDirection.BEARISH
            else None
        )
        engine = self.engines.get(direction)
        if engine is None:
            return ProbabilityResult(analysis.symbol, analysis.timestamp, 0, 0, 1, self.version)
        return engine.predict(analysis)
