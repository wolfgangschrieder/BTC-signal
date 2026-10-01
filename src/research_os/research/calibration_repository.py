from __future__ import annotations
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.research.calibration import CalibrationLab

class CalibrationRepository:
    def load_resolved(self,session:Session,symbol:str|None=None,start:datetime|None=None,end:datetime|None=None):
        where=["status IN ('win','loss')"]; params={}
        if symbol: where.append("symbol=:symbol"); params["symbol"]=symbol
        if start: where.append("resolved_at>=:start"); params["start"]=start
        if end: where.append("resolved_at<=:end"); params["end"]=end
        sql="SELECT symbol,probability,status,resolved_at FROM signal_outcomes WHERE "+" AND ".join(where)+" ORDER BY resolved_at"
        return session.execute(text(sql),params).mappings().all()

    def evaluate(self,session:Session,symbol=None,start=None,end=None):
        rows=self.load_resolved(session,symbol,start,end)
        return CalibrationLab().evaluate(CalibrationLab.from_outcomes(rows))
