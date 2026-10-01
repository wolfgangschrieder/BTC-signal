from __future__ import annotations

from sqlalchemy import text


class ExternalEventRepository:
    def save(self, session, event) -> None:
        session.execute(
            text("""
                INSERT INTO intelligence.external_events
                (event_id,title,source,event_time,point_in_time_available_at,category,impact,
                 relevance,sentiment,confidence,payload)
                VALUES (:event_id,:title,:source,:event_time,:pit,:category,:impact,
                        :relevance,:sentiment,:confidence,CAST(:payload AS jsonb))
                ON CONFLICT (event_id, source) DO NOTHING
            """),
            {
                "event_id": event.event_id,
                "title": event.title,
                "source": event.source,
                "event_time": event.event_time,
                "pit": event.point_in_time_available_at,
                "category": event.category.value,
                "impact": event.impact.value,
                "relevance": event.relevance,
                "sentiment": event.sentiment,
                "confidence": event.confidence,
                "payload": __import__("json").dumps(event.payload or {}),
            },
        )

    def latest(self, session, decision_time, limit: int = 100):
        rows = session.execute(
            text("""
                SELECT event_id,title,source,event_time,point_in_time_available_at,
                       category,impact,relevance,sentiment,confidence,payload
                FROM intelligence.external_events
                WHERE point_in_time_available_at <= :decision_time
                  AND event_time <= :decision_time
                ORDER BY event_time DESC, point_in_time_available_at DESC, source ASC
                LIMIT :limit
            """),
            {"decision_time": decision_time, "limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]
