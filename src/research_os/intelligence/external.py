from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from .events import EventCategory, EventImpact, ExternalEvent


@dataclass(frozen=True, slots=True)
class RawExternalEvent:
    source: str
    title: str
    event_time: datetime
    point_in_time_available_at: datetime
    source_event_id: str | None = None
    category: str | None = None
    impact: str | None = None
    relevance: float | None = None
    sentiment: float | None = None
    confidence: float | None = None
    payload: dict[str, Any] | None = None


class ExternalEventProvider(Protocol):
    name: str

    def fetch(self, since: datetime, until: datetime) -> list[RawExternalEvent]:
        ...


class ExternalEventNormalizer:
    """Turns provider-specific records into immutable canonical PIT-safe events."""

    def normalize(self, raw: RawExternalEvent) -> ExternalEvent:
        event_id = raw.source_event_id or self._stable_id(raw)
        return ExternalEvent(
            event_id=event_id,
            title=raw.title.strip(),
            source=raw.source.strip(),
            event_time=raw.event_time,
            point_in_time_available_at=raw.point_in_time_available_at,
            category=self._enum(EventCategory, raw.category, EventCategory.OTHER),
            impact=self._enum(EventImpact, raw.impact, EventImpact.UNKNOWN),
            relevance=0.0 if raw.relevance is None else raw.relevance,
            sentiment=raw.sentiment,
            confidence=0.0 if raw.confidence is None else raw.confidence,
            payload=raw.payload or {},
        )

    @staticmethod
    def _enum(enum_type, value, default):
        if not value:
            return default
        try:
            return enum_type(str(value).lower())
        except ValueError:
            return default

    @staticmethod
    def _stable_id(raw: RawExternalEvent) -> str:
        material = "|".join(
            (
                raw.source.strip(),
                raw.title.strip(),
                raw.event_time.isoformat(),
                raw.point_in_time_available_at.isoformat(),
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()


class ExternalEventIngestion:
    """Cold-path ingestion coordinator; providers never run on the market hot path."""

    def __init__(self, normalizer: ExternalEventNormalizer | None = None):
        self.normalizer = normalizer or ExternalEventNormalizer()

    def collect(self, provider: ExternalEventProvider, since: datetime, until: datetime) -> list[ExternalEvent]:
        if until < since:
            raise ValueError("until must not precede since")
        raw_events = provider.fetch(since, until)
        normalized = [self.normalizer.normalize(item) for item in raw_events]
        unique: dict[tuple[str, str], ExternalEvent] = {}
        for event in normalized:
            unique[(event.source, event.event_id)] = event
        return sorted(
            unique.values(),
            key=lambda event: (
                event.event_time,
                event.point_in_time_available_at,
                event.source,
                event.event_id,
            ),
        )
