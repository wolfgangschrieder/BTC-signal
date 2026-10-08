from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from research_os.data.models import RawEvent


class RawEventStore:
    """Append-only raw event boundary. No update/delete methods by design."""

    def append(self, session: Session, event: RawEvent) -> int:
        result = session.execute(
            text("""
                INSERT INTO raw.events
                (source, event_type, symbol, event_time, ingestion_time,
                 point_in_time_available_at, payload, schema_version)
                VALUES (:source, :event_type, :symbol, :event_time, :ingestion_time,
                        :pit, :payload, :schema_version)
                RETURNING id
            """).bindparams(bindparam("payload", type_=JSONB)),
            {
                "source": event.source,
                "event_type": event.event_type.value,
                "symbol": event.symbol,
                "event_time": event.event_time,
                "ingestion_time": event.ingestion_time,
                "pit": event.point_in_time_available_at,
                "payload": event.payload,
                "schema_version": event.schema_version,
            },
        )
        return int(result.scalar_one())
