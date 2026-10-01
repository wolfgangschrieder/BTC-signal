from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

from .events import EventCategory, EventImpact, ExternalEvent


class ExternalEventRepository:
    def save(self, session, event: ExternalEvent) -> None:
        session.execute(
            text("""
                INSERT INTO intelligence.external_events
                (event_id,title,source,event_time,point_in_time_available_at,category,impact,
                 relevance,sentiment,confidence,payload)
                VALUES (:event_id,:title,:source,:event_time,:pit,:category,:impact,
                        :relevance,:sentiment,:confidence,CAST(:payload AS jsonb))
                ON CONFLICT (event_id, source) DO NOTHING
            """),
            {"event_id": event.event_id, "title": event.title, "source": event.source,
             "event_time": event.event_time, "pit": event.point_in_time_available_at,
             "category": event.category.value, "impact": event.impact.value,
             "relevance": event.relevance, "sentiment": event.sentiment,
             "confidence": event.confidence, "payload": json.dumps(event.payload or {})},
        )

    def latest(self, session, decision_time: datetime, *, lookback_seconds: float | None = None,
               min_relevance: float = 0.0, limit: int = 100) -> list[ExternalEvent]:
        if limit < 1:
            raise ValueError("limit must be positive")
        params = {"decision_time": decision_time, "min_relevance": min_relevance, "limit": limit}
        lookback_clause = ""
        if lookback_seconds is not None:
            if lookback_seconds < 0:
                raise ValueError("lookback_seconds must be non-negative")
            params["lower_time"] = datetime.fromtimestamp(
                decision_time.timestamp() - lookback_seconds, tz=decision_time.tzinfo)
            lookback_clause = "AND event_time >= :lower_time"
        rows = session.execute(
            text(f"""
                SELECT event_id,title,source,event_time,point_in_time_available_at,
                       category,impact,relevance,sentiment,confidence,payload
                FROM intelligence.external_events
                WHERE point_in_time_available_at <= :decision_time
                  AND event_time <= :decision_time
                  AND relevance >= :min_relevance
                  {lookback_clause}
                ORDER BY event_time DESC, point_in_time_available_at DESC, source ASC, event_id ASC
                LIMIT :limit
            """), params).mappings().all()
        return [self._to_event(row) for row in rows]

    @staticmethod
    def _to_event(row) -> ExternalEvent:
        return ExternalEvent(
            event_id=row["event_id"], title=row["title"], source=row["source"],
            event_time=row["event_time"], point_in_time_available_at=row["point_in_time_available_at"],
            category=EventCategory(row["category"]), impact=EventImpact(row["impact"]),
            relevance=float(row["relevance"]),
            sentiment=None if row["sentiment"] is None else float(row["sentiment"]),
            confidence=float(row["confidence"]), payload=row["payload"] or {},
        )
