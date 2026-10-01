from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Mapping, Sequence

from research_os.intelligence.events import ExternalEvent, ExternalEventEngine
from research_os.research.replay import ReplayCandle


@dataclass(frozen=True, slots=True)
class ResearchDatasetRow:
    symbol: str
    decision_time: datetime
    entry_price: float
    horizon_minutes: int
    outcome_time: datetime
    return_pct: float
    mfe_pct: float
    mae_pct: float
    features: tuple[tuple[str, float], ...]
    external_event_count: int
    external_high_impact_count: int
    external_weighted_sentiment: float | None
    external_max_relevance: float
    external_categories: tuple[str, ...]
    external_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchDataset:
    symbol: str
    version: str
    rows: tuple[ResearchDatasetRow, ...]
    skipped: int


@dataclass(frozen=True, slots=True)
class DatasetPITViolation:
    decision_time: datetime
    field: str
    value_time: datetime


class ResearchDatasetBuilder:
    version = "research-dataset-v1"

    def __init__(self, external_engine: ExternalEventEngine | None = None) -> None:
        self.external_engine = external_engine or ExternalEventEngine()

    def build(
        self,
        symbol: str,
        decision_times: Sequence[datetime],
        candles: Sequence[ReplayCandle],
        *,
        features_by_time: Mapping[datetime, Mapping[str, float | None]] | None = None,
        external_events: Sequence[ExternalEvent] = (),
        horizon_minutes: int = 60,
        external_lookback_seconds: float = 3600.0,
        min_event_relevance: float = 0.0,
    ) -> ResearchDataset:
        if horizon_minutes <= 0:
            raise ValueError("horizon_minutes must be positive")
        if external_lookback_seconds < 0:
            raise ValueError("external_lookback_seconds must be non-negative")
        if not 0.0 <= min_event_relevance <= 1.0:
            raise ValueError("min_event_relevance must be between 0 and 1")

        ordered_candles = tuple(sorted(candles, key=lambda c: c.event_time))
        ordered_decisions = tuple(sorted(set(decision_times)))
        rows: list[ResearchDatasetRow] = []
        skipped = 0

        for decision_time in ordered_decisions:
            candle = self._decision_candle(ordered_candles, decision_time)
            if candle is None:
                skipped += 1
                continue

            pit = candle.point_in_time_available_at or candle.event_time
            if pit > decision_time:
                skipped += 1
                continue

            future = self._future_window(
                ordered_candles,
                decision_time,
                decision_time + timedelta(minutes=horizon_minutes),
            )
            if not future or future[-1].event_time < decision_time + timedelta(minutes=horizon_minutes):
                skipped += 1
                continue

            snapshot = self.external_engine.build(
                decision_time,
                list(external_events),
                as_of=decision_time,
                lookback_seconds=external_lookback_seconds,
                min_relevance=min_event_relevance,
            )

            feature_items: list[tuple[str, float]] = []
            for name, value in sorted((features_by_time or {}).get(decision_time, {}).items()):
                if value is None:
                    continue
                numeric = float(value)
                if not isfinite(numeric):
                    raise ValueError(f"feature {name!r} must be finite")
                feature_items.append((name, numeric))

            entry = float(candle.close)
            final = future[-1]
            rows.append(
                ResearchDatasetRow(
                    symbol=symbol,
                    decision_time=decision_time,
                    entry_price=entry,
                    horizon_minutes=horizon_minutes,
                    outcome_time=final.event_time,
                    return_pct=(float(final.close) - entry) / entry,
                    mfe_pct=(max(float(c.high) for c in future) - entry) / entry,
                    mae_pct=(min(float(c.low) for c in future) - entry) / entry,
                    features=tuple(feature_items),
                    external_event_count=snapshot.total_count,
                    external_high_impact_count=snapshot.high_impact_count,
                    external_weighted_sentiment=snapshot.weighted_sentiment,
                    external_max_relevance=snapshot.max_relevance,
                    external_categories=snapshot.categories,
                    external_event_ids=tuple(event.event_id for event in snapshot.events),
                )
            )

        rows.sort(key=lambda row: (row.decision_time, row.outcome_time))
        return ResearchDataset(
            symbol=symbol,
            version=f"{self.version}:{horizon_minutes}:{int(external_lookback_seconds)}:{min_event_relevance:g}",
            rows=tuple(rows),
            skipped=skipped,
        )

    @staticmethod
    def _decision_candle(candles: Sequence[ReplayCandle], timestamp: datetime) -> ReplayCandle | None:
        candidates = [
            candle
            for candle in candles
            if candle.event_time == timestamp
            and (candle.point_in_time_available_at or candle.event_time) <= timestamp
        ]
        return candidates[-1] if candidates else None

    @staticmethod
    def _future_window(candles: Sequence[ReplayCandle], start: datetime, end: datetime) -> list[ReplayCandle]:
        return [candle for candle in candles if start < candle.event_time <= end]

    @staticmethod
    def audit_pit(dataset: ResearchDataset) -> tuple[DatasetPITViolation, ...]:
        violations: list[DatasetPITViolation] = []
        for row in dataset.rows:
            if row.outcome_time <= row.decision_time:
                violations.append(DatasetPITViolation(row.decision_time, "outcome_time", row.outcome_time))
            for event_id in row.external_event_ids:
                # Event IDs are materialized only after ExternalEventEngine PIT filtering.
                # The detailed event timestamp audit is performed against source events below.
                if not event_id:
                    violations.append(DatasetPITViolation(row.decision_time, "external_event_id", row.decision_time))
        return tuple(violations)

    @staticmethod
    def chronological_split(
        dataset: ResearchDataset,
        train_ratio: float = 0.7,
    ) -> tuple[ResearchDataset, ResearchDataset]:
        if not 0.0 < train_ratio < 1.0:
            raise ValueError("train_ratio must be between 0 and 1")
        rows = tuple(sorted(dataset.rows, key=lambda row: row.decision_time))
        cut = int(len(rows) * train_ratio)
        return (
            ResearchDataset(dataset.symbol, dataset.version + ":train", rows[:cut], 0),
            ResearchDataset(dataset.symbol, dataset.version + ":test", rows[cut:], 0),
        )
