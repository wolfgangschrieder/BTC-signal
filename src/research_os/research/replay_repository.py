from __future__ import annotations
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.research.replay import ReplayCandle,ReplayEngine,ReplayReport

class ReplayRepository:
    def load_candles(self,session:Session,symbol:str,start:datetime,end:datetime,interval="1"):
        rows=session.execute(text("""SELECT event_time,open,high,low,close,volume,point_in_time_available_at
        FROM market.candles
        WHERE symbol=:symbol AND interval=:interval
          AND event_time>=:start AND event_time<=:end
        ORDER BY event_time"""),{"symbol":symbol,"interval":interval,"start":start,"end":end}).mappings()
        return [ReplayCandle(r["event_time"],float(r["open"]),float(r["high"]),float(r["low"]),float(r["close"]),float(r["volume"]),r["point_in_time_available_at"]) for r in rows]

    def run(self,session:Session,symbol,start,end,interval="1",dataset_version="db-replay-v1",**replay_kwargs):
        candles=self.load_candles(session,symbol,start,end,interval)
        return ReplayEngine(**replay_kwargs).run(symbol,candles,dataset_version)
