from __future__ import annotations
from datetime import datetime
from sqlalchemy import text

class CrossMarketRepository:
    def save(self,session,observation):
        session.execute(text("""
            INSERT INTO intelligence.cross_market_observations
            (asset,event_time,point_in_time_available_at,value,source,unit,payload)
            VALUES (:asset,:event_time,:pit,:value,:source,:unit,CAST(:payload AS jsonb))
        """),{"asset":observation.asset,"event_time":observation.timestamp,
              "pit":observation.point_in_time_available_at,"value":observation.value,
              "source":observation.source,"unit":observation.unit,"payload":"{}"})

    def latest(self,session,asset,decision_time):
        row=session.execute(text("""
            SELECT asset,event_time,point_in_time_available_at,value,source,unit
            FROM intelligence.cross_market_observations
            WHERE asset=:asset AND event_time<=:decision_time
              AND point_in_time_available_at<=:decision_time
            ORDER BY event_time DESC,
                     point_in_time_available_at DESC,
                     source ASC
            LIMIT 1
        """),{"asset":asset,"decision_time":decision_time}).mappings().first()
        return dict(row) if row else None
