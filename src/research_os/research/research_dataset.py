from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Mapping, Sequence

from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.research import CrossMarketResearchEngine
from research_os.features.engine import FeatureEngine
from research_os.intelligence.events import ExternalEvent, ExternalEventEngine
from research_os.market.state_builder import MarketStateBuilder
from research_os.research.replay import ReplayCandle


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    source: str
    source_id: str
    first_event_time: datetime
    last_event_time: datetime
    available_at: datetime
    item_count: int

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.available_at <= decision_time


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
    cross_market: tuple[tuple[str, float | None, float | None, float | None, int, bool], ...]
    external_event_count: int
    external_high_impact_count: int
    external_weighted_sentiment: float | None
    external_max_relevance: float
    external_categories: tuple[str, ...]
    external_event_ids: tuple[str, ...]
    provenance: tuple[EvidenceProvenance, ...] = ()


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
    version = "research-dataset-v3"

    def __init__(self, feature_engine=None, state_builder=None, cross_market_engine=None, external_engine=None):
        self.features = feature_engine or FeatureEngine()
        self.state_builder = state_builder or MarketStateBuilder()
        self.cross_market = cross_market_engine or CrossMarketResearchEngine()
        self.external_engine = external_engine or ExternalEventEngine()

    def build(
        self,
        symbol: str,
        decision_times: Sequence[datetime],
        candles: Sequence[ReplayCandle],
        *,
        cross_market_observations: Sequence[CrossMarketObservation] = (),
        features_by_time: Mapping[datetime, Mapping[str, float | None]] | None = None,
        external_events: Sequence[ExternalEvent] = (),
        horizon_minutes: int = 60,
        external_lookback_seconds: float = 3600.0,
        min_event_relevance: float = 0.0,
        cross_market_min_samples: int = 20,
        cross_market_window_size: int = 252,
    ) -> ResearchDataset:
        if horizon_minutes <= 0:
            raise ValueError("horizon_minutes must be positive")
        if external_lookback_seconds < 0:
            raise ValueError("external_lookback_seconds must be non-negative")
        if not 0.0 <= min_event_relevance <= 1.0:
            raise ValueError("min_event_relevance must be between 0 and 1")
        if cross_market_min_samples < 1 or cross_market_window_size < cross_market_min_samples:
            raise ValueError("invalid cross-market normalization parameters")

        ordered = tuple(sorted(candles, key=lambda c: c.event_time))
        events = tuple(external_events)
        observations = tuple(cross_market_observations)
        rows = []
        skipped = 0

        for decision_time in sorted(set(decision_times)):
            available = tuple(
                c for c in ordered
                if c.event_time <= decision_time
                and (c.point_in_time_available_at or c.event_time) <= decision_time
            )
            if not available or available[-1].event_time != decision_time:
                skipped += 1
                continue

            future = tuple(
                c for c in ordered
                if decision_time < c.event_time <= decision_time + timedelta(minutes=horizon_minutes)
            )
            if not future or future[-1].event_time < decision_time + timedelta(minutes=horizon_minutes):
                skipped += 1
                continue

            closes = tuple(float(c.close) for c in available)
            volumes = tuple(float(c.volume) for c in available)
            highs = tuple(float(c.high) for c in available)
            lows = tuple(float(c.low) for c in available)
            snapshot = self.features.build(symbol, decision_time, closes, volumes, highs, lows)
            state = self.state_builder.build(symbol, decision_time, decision_time, decision_time, snapshot, {})

            feature_items = []
            for feature in snapshot.features:
                if feature.available and feature.value is not None:
                    value = float(feature.value)
                    if not isfinite(value):
                        raise ValueError(f"feature {feature.name!r} must be finite")
                    feature_items.append((feature.name, value))

            for name, value in sorted((features_by_time or {}).get(decision_time, {}).items()):
                if value is None:
                    continue
                value = float(value)
                if not isfinite(value):
                    raise ValueError(f"feature {name!r} must be finite")
                feature_items.append((name, value))

            for name, value in sorted(state.values.items()):
                if value is None:
                    continue
                value = float(value)
                if not isfinite(value):
                    raise ValueError(f"state value {name!r} must be finite")
                feature_items.append((f"state:{name}", value))

            cross = self.cross_market.build(
                decision_time, observations, as_of=decision_time,
                min_samples=cross_market_min_samples, window_size=cross_market_window_size
            )
            cross_rows = tuple(
                (asset, norm.value, norm.zscore, norm.percentile, norm.sample_size, norm.available)
                for asset, norm in sorted(cross.normalized.items())
            )

            external = self.external_engine.build(
                decision_time, list(events), as_of=decision_time,
                lookback_seconds=external_lookback_seconds, min_relevance=min_event_relevance
            )

            pit_candles = tuple(c for c in available if c.point_in_time_available_at is not None)
            candle_available_at = max((c.point_in_time_available_at or c.event_time) for c in available)
            provenance = [
                EvidenceProvenance(
                    "market_candles",
                    f"{symbol}:{available[0].event_time.isoformat()}:{available[-1].event_time.isoformat()}",
                    available[0].event_time,
                    available[-1].event_time,
                    candle_available_at,
                    len(available),
                )
            ]
            if observations:
                relevant_obs = tuple(
                    o for o in observations
                    if o.timestamp <= decision_time and o.point_in_time_available_at <= decision_time
                )
                if relevant_obs:
                    provenance.append(EvidenceProvenance(
                        "cross_market",
                        f"{len(relevant_obs)}-observations",
                        min(o.timestamp for o in relevant_obs),
                        max(o.timestamp for o in relevant_obs),
                        max(o.point_in_time_available_at for o in relevant_obs),
                        len(relevant_obs),
                    ))
            if external.events:
                provenance.extend(
                    EvidenceProvenance(
                        "external_event",
                        e.event_id,
                        e.event_time,
                        e.event_time,
                        e.point_in_time_available_at,
                        1,
                    )
                    for e in external.events
                )

            entry = float(available[-1].close)
            final = future[-1]
            rows.append(ResearchDatasetRow(
                symbol, decision_time, entry, horizon_minutes, final.event_time,
                (float(final.close) - entry) / entry,
                (max(float(c.high) for c in future) - entry) / entry,
                (min(float(c.low) for c in future) - entry) / entry,
                tuple(feature_items), cross_rows,
                external.total_count, external.high_impact_count,
                external.weighted_sentiment, external.max_relevance,
                external.categories, tuple(e.event_id for e in external.events),
                tuple(provenance),
            ))

        rows.sort(key=lambda r: (r.decision_time, r.outcome_time))
        return ResearchDataset(
            symbol, f"{self.version}:{horizon_minutes}:{int(external_lookback_seconds)}:{min_event_relevance:g}",
            tuple(rows), skipped
        )

    @staticmethod
    def audit_pit(dataset, external_events=(), cross_market_observations=()):
        violations = []
        for row in dataset.rows:
            if row.outcome_time <= row.decision_time:
                violations.append(DatasetPITViolation(row.decision_time, "outcome_time", row.outcome_time))
            for evidence in row.provenance:
                if evidence.available_at > row.decision_time:
                    violations.append(DatasetPITViolation(row.decision_time, f"provenance:{evidence.source}:{evidence.source_id}", evidence.available_at))
        return tuple(sorted(violations, key=lambda v: (v.decision_time, v.field, v.value_time)))

    @staticmethod
    def chronological_split(dataset, train_ratio=0.7, purge_minutes=None):
        if not 0.0 < train_ratio < 1.0:
            raise ValueError("train_ratio must be between 0 and 1")
        rows = tuple(sorted(dataset.rows, key=lambda r: r.decision_time))
        if not rows:
            return (
                ResearchDataset(dataset.symbol, dataset.version + ":train", (), 0),
                ResearchDataset(dataset.symbol, dataset.version + ":test", (), 0),
            )
        cut = int(len(rows) * train_ratio)
        if cut <= 0 or cut >= len(rows):
            raise ValueError("train_ratio produces an empty split")
        purge = rows[0].horizon_minutes if purge_minutes is None else purge_minutes
        if purge < 0:
            raise ValueError("purge_minutes must be non-negative")
        train = rows[:cut]
        boundary = train[-1].decision_time + timedelta(minutes=purge)
        test = tuple(r for r in rows[cut:] if r.decision_time > boundary)
        return (
            ResearchDataset(dataset.symbol, dataset.version + ":train", train, 0),
            ResearchDataset(dataset.symbol, dataset.version + ":test", test, len(rows[cut:]) - len(test)),
        )
