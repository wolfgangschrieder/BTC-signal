from datetime import datetime, timezone
from research_os.data.models import QualityCode, QualityEvent, RawEvent

class DataQualityEngine:
    def validate_event(self, event: RawEvent, decision_time: datetime | None = None) -> list[QualityEvent]:
        now = datetime.now(timezone.utc)
        issues: list[QualityEvent] = []
        if event.event_time.tzinfo is None or event.ingestion_time.tzinfo is None:
            issues.append(QualityEvent(
                code=QualityCode.TIMESTAMP_INVALID, source=event.source,
                event_time=event.event_time, message="Event and ingestion timestamps must be timezone-aware.",
            ))
        if decision_time is not None and not event.is_pit_valid(decision_time):
            issues.append(QualityEvent(
                code=QualityCode.PIT_VIOLATION, severity="error", source=event.source,
                event_time=event.event_time,
                message="point_in_time_available_at is after decision_time.",
            ))
        if event.ingestion_time > now:
            issues.append(QualityEvent(
                code=QualityCode.TIMESTAMP_INVALID, source=event.source,
                event_time=event.event_time, message="Ingestion timestamp is in the future.",
            ))
        return issues
