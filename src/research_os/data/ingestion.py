from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from research_os.data.models import RawEvent, QualityEvent
from research_os.data.quality import DataQualityEngine
from research_os.data.raw_store import RawEventStore


class IngestionRejected(ValueError):
    """Raised when an event violates a hard ingestion invariant."""


class EventIngestionService:
    """Single ingestion boundary for normalized market-data events."""

    def __init__(
        self,
        store: RawEventStore | None = None,
        quality: DataQualityEngine | None = None,
    ) -> None:
        self.store = store or RawEventStore()
        self.quality = quality or DataQualityEngine()

    def ingest(
        self,
        session: Session,
        event: RawEvent,
        decision_time: datetime | None = None,
    ) -> tuple[int | None, list[QualityEvent]]:
        issues = self.quality.validate_event(event, decision_time=decision_time)
        hard_errors = [i for i in issues if i.severity == "error"]
        if hard_errors:
            self._store_quality_events(session, hard_errors)
            raise IngestionRejected(hard_errors[0].message)

        fingerprint = event_fingerprint(event)
        if self._exists(session, fingerprint):
            duplicate = QualityEvent(
                code="duplicate",
                source=event.source,
                event_time=event.event_time,
                message="Duplicate raw event fingerprint",
                details={"fingerprint": fingerprint},
            )
            self._store_quality_events(session, [duplicate])
            return None, issues + [duplicate]

        event_id = self.store.append(session, event)
        self._store_fingerprint(session, event_id, fingerprint)
        if issues:
            self._store_quality_events(session, issues)
        return event_id, issues

    def ingest_batch(
        self,
        session: Session,
        events: Iterable[RawEvent],
        decision_time: datetime | None = None,
    ) -> tuple[list[int], list[QualityEvent]]:
        ids: list[int] = []
        issues: list[QualityEvent] = []
        for event in events:
            event_id, event_issues = self.ingest(session, event, decision_time)
            if event_id is not None:
                ids.append(event_id)
            issues.extend(event_issues)
        return ids, issues

    @staticmethod
    def _exists(session: Session, fingerprint: str) -> bool:
        return session.execute(
            text("SELECT 1 FROM raw.event_fingerprints WHERE fingerprint = :fingerprint"),
            {"fingerprint": fingerprint},
        ).first() is not None

    @staticmethod
    def _store_fingerprint(session: Session, event_id: int, fingerprint: str) -> None:
        session.execute(
            text(
                "INSERT INTO raw.event_fingerprints (fingerprint, event_id) "
                "VALUES (:fingerprint, :event_id)"
            ),
            {"fingerprint": fingerprint, "event_id": event_id},
        )

    @staticmethod
    def _store_quality_events(session: Session, events: Iterable[QualityEvent]) -> None:
        for event in events:
            session.execute(
                text(
                    """INSERT INTO raw.quality_events
                    (code, severity, source, event_time, message, details)
                    VALUES (:code, :severity, :source, :event_time, :message, :details)"""
                ),
                {
                    "code": event.code.value if hasattr(event.code, "value") else str(event.code),
                    "severity": event.severity,
                    "source": event.source,
                    "event_time": event.event_time,
                    "message": event.message,
                    "details": event.details,
                },
            )


def event_fingerprint(event: RawEvent) -> str:
    canonical = {
        "source": event.source,
        "event_type": event.event_type.value,
        "symbol": event.symbol,
        "event_time": event.event_time.astimezone(timezone.utc).isoformat(),
        "point_in_time_available_at": event.point_in_time_available_at.astimezone(timezone.utc).isoformat(),
        "payload": event.payload,
        "schema_version": event.schema_version,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
