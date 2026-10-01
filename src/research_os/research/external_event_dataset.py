from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from research_os.intelligence.events import ExternalEvent, ExternalEventEngine


@dataclass(frozen=True, slots=True)
class ExternalEventDatasetRow:
    timestamp: datetime
    event_id: str
    source: str
    event_time: datetime
    point_in_time_available_at: datetime
    category: str
    impact: str
    relevance: float
    sentiment: float | None
    confidence: float
    age_seconds: float


@dataclass(frozen=True, slots=True)
class ExternalEventDataset:
    symbol: str
    version: str
    rows: tuple[ExternalEventDatasetRow, ...]
    decision_times: int
    decisions_with_events: int
    skipped_events: int


@dataclass(frozen=True, slots=True)
class ExternalEventPITViolation:
    decision_time: datetime
    event_id: str
    source: str
    point_in_time_available_at: datetime


class ExternalEventDatasetBuilder:
    """Build a reproducible event-at-decision dataset with a strict PIT boundary."""

    version = "external-event-dataset-v1"

    def __init__(self, engine: ExternalEventEngine | None = None) -> None:
        self.engine = engine or ExternalEventEngine()

    def build(
        self,
        symbol: str,
        decision_times: Sequence[datetime],
        events: Sequence[ExternalEvent],
        *,
        lookback_seconds: float = 3600.0,
        min_relevance: float = 0.0,
    ) -> ExternalEventDataset:
        if lookback_seconds < 0:
            raise ValueError("lookback_seconds must be non-negative")
        if not 0.0 <= min_relevance <= 1.0:
            raise ValueError("min_relevance must be between 0 and 1")

        rows: list[ExternalEventDatasetRow] = []
        decisions_with_events = 0
        ordered_decisions = sorted(set(decision_times))

        for decision_time in ordered_decisions:
            snapshot = self.engine.build(
                decision_time,
                list(events),
                as_of=decision_time,
                lookback_seconds=lookback_seconds,
                min_relevance=min_relevance,
            )
            if snapshot.events:
                decisions_with_events += 1

            for event in snapshot.events:
                rows.append(
                    ExternalEventDatasetRow(
                        timestamp=decision_time,
                        event_id=event.event_id,
                        source=event.source,
                        event_time=event.event_time,
                        point_in_time_available_at=event.point_in_time_available_at,
                        category=event.category.value,
                        impact=event.impact.value,
                        relevance=event.relevance,
                        sentiment=event.sentiment,
                        confidence=event.confidence,
                        age_seconds=(decision_time - event.event_time).total_seconds(),
                    )
                )

        rows.sort(
            key=lambda row: (
                row.timestamp,
                row.event_time,
                row.point_in_time_available_at,
                row.source,
                row.event_id,
            )
        )
        return ExternalEventDataset(
            symbol=symbol,
            version=f"{self.version}:{int(lookback_seconds)}:{min_relevance:g}",
            rows=tuple(rows),
            decision_times=len(ordered_decisions),
            decisions_with_events=decisions_with_events,
            skipped_events=max(
                0,
                len(events) - len({(e.source, e.event_id) for e in events}),
            ),
        )

    @staticmethod
    def audit_pit(
        dataset: ExternalEventDataset,
    ) -> tuple[ExternalEventPITViolation, ...]:
        violations: list[ExternalEventPITViolation] = []
        for row in dataset.rows:
            if row.point_in_time_available_at > row.timestamp:
                violations.append(
                    ExternalEventPITViolation(
                        row.timestamp,
                        row.event_id,
                        row.source,
                        row.point_in_time_available_at,
                    )
                )
        return tuple(violations)
