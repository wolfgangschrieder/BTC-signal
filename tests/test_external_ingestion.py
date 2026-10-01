from datetime import datetime, timezone

import pytest

from research_os.intelligence.events import EventCategory, EventImpact
from research_os.intelligence.external import (
    ExternalEventIngestion,
    ExternalEventNormalizer,
    RawExternalEvent,
)


class Provider:
    name = "fixture"

    def __init__(self, events):
        self.events = events

    def fetch(self, since, until):
        return self.events


def raw(event_id="1", title=" BTC event "):
    t = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    return RawExternalEvent(
        source="fixture",
        source_event_id=event_id,
        title=title,
        event_time=t,
        point_in_time_available_at=t,
        category="macro",
        impact="high",
        relevance=0.8,
        sentiment=0.4,
        confidence=0.9,
    )


def test_normalizer_maps_canonical_enums():
    e = ExternalEventNormalizer().normalize(raw())
    assert e.category is EventCategory.MACRO
    assert e.impact is EventImpact.HIGH
    assert e.title == "BTC event"


def test_normalizer_creates_stable_id_when_provider_has_none():
    a = raw(event_id=None)
    b = raw(event_id=None)
    assert ExternalEventNormalizer().normalize(a).event_id == ExternalEventNormalizer().normalize(b).event_id


def test_ingestion_deduplicates_source_event_id():
    events = ExternalEventIngestion().collect(Provider([raw(), raw()]), raw().event_time, raw().event_time)
    assert len(events) == 1


def test_ingestion_rejects_inverted_window():
    t = raw().event_time
    with pytest.raises(ValueError):
        ExternalEventIngestion().collect(Provider([]), t, t.replace(hour=11))
