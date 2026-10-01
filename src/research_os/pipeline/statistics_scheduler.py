from __future__ import annotations
import asyncio
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from research_os.database.session import SessionLocal
from research_os.notifications.telegram_client import TelegramClient
from research_os.signals.outcome_evaluator import SignalOutcomeEvaluator
from research_os.notifications.statistics import StatisticsReporter

class StatisticsScheduler:
    def __init__(self,telegram:TelegramClient,timezone_name="Europe/Moscow",hour=20,minute=0):
        self.telegram=telegram; self.tz=ZoneInfo(timezone_name); self.hour=hour; self.minute=minute; self.evaluator=SignalOutcomeEvaluator(); self.reporter=StatisticsReporter(timezone_name)
    def _next(self,now):
        candidate=now.replace(hour=self.hour,minute=self.minute,second=0,microsecond=0)
        if candidate<=now: candidate+=timedelta(days=1)
        return candidate
    async def run(self,stop:asyncio.Event|None=None):
        stop=stop or asyncio.Event()
        while not stop.is_set():
            now=datetime.now(self.tz); target=self._next(now)
            try: await asyncio.wait_for(stop.wait(),max(0,(target-now).total_seconds()))
            except asyncio.TimeoutError: pass
            if stop.is_set(): break
            with SessionLocal() as session:
                self.evaluator.resolve_pending(session,datetime.now(self.tz))
                daily=self.reporter.daily(session)
                await self.telegram.send(daily)
                if datetime.now(self.tz).weekday()==6:
                    await self.telegram.send(self.reporter.weekly(session))
