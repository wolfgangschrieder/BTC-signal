from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class EventCategory(StrEnum):
    MACRO = "macro"
    REGULATION = "regulation"
    GEOPOLITICAL = "geopolitical"
    CRYPTO = "crypto"
    MARKET = "market"
    TECHNOLOGY = "technology"
    OTHER = "other"


class EventImpact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExternalEvent:
    event_id: str
    title: str
    source: str
    event_time: datetime
    point_in_time_available_at: datetime
    category: EventCategory
    impact: EventImpact = EventImpact.UNKNOWN
    relevance: float = 0.0
    sentiment: float | None = None
    confidence: float = 0.0
    payload: dict | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.title.strip() or not self.source.strip():
            raise ValueError("event_id, title and source are required")
        if self.point_in_time_available_at < self.event_time:
            raise ValueError("PIT availability cannot precede event time")
        for name, value in (
            ("relevance", self.relevance),
            ("confidence", self.confidence),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1")
        if self.sentiment is not None and (
            not isfinite(self.sentiment) or not -1.0 <= self.sentiment <= 1.0
        ):
            raise ValueError("sentiment must be between -1 and 1")

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.point_in_time_available_at <= decision_time


@dataclass(frozen=True, slots=True)
class ExternalEventSnapshot:
    timestamp: datetime
    events: tuple[ExternalEvent, ...]
    available: bool
    total_count: int
    high_impact_count: int
    categories: tuple[str, ...]
    weighted_sentiment: float | None
    max_relevance: float
    version: str = "external-events-v1"


class ExternalEventEngine:
    version = "external-events-v1"

    def build(
        self,
        timestamp: datetime,
        events: list[ExternalEvent] | tuple[ExternalEvent, ...],
        *,
        as_of: datetime | None = None,
        lookback_seconds: float = 3600.0,
        min_relevance: float = 0.0,
    ) -> ExternalEventSnapshot:
        cutoff = as_of or timestamp
        lower = timestamp.timestamp() - lookback_seconds
        valid = [
            event
            for event in events
            if event.is_pit_valid(cutoff)
            and lower <= event.event_time.timestamp() <= timestamp.timestamp()
            and event.relevance >= min_relevance
        ]
        valid.sort(key=lambda event: (event.event_time, event.point_in_time_available_at, event.source, event.event_id))
        categories = tuple(sorted({event.category.value for event in valid}))
        weighted = [
            (event.sentiment, event.relevance * event.confidence)
            for event in valid
            if event.sentiment is not None and event.relevance > 0.0 and event.confidence > 0.0
        ]
        weighted_sentiment = None
        if weighted:
            denominator = sum(weight for _, weight in weighted)
            if denominator > 0.0:
                weighted_sentiment = sum(sentiment * weight for sentiment, weight in weighted) / denominator
        return ExternalEventSnapshot(
            timestamp=timestamp,
            events=tuple(valid),
            available=bool(valid),
            total_count=len(valid),
            high_impact_count=sum(event.impact is EventImpact.HIGH for event in valid),
            categories=categories,
            weighted_sentiment=weighted_sentiment,
            max_relevance=max((event.relevance for event in valid), default=0.0),
            version=self.version,
        )
