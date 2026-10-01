from __future__ import annotations
import asyncio
import logging
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from research_os.database.session import SessionLocal
from research_os.notifications.telegram_client import TelegramClient
from research_os.notifications.statistics import StatisticsReporter
from research_os.signals.outcome_evaluator import SignalOutcomeEvaluator

logger=logging.getLogger(__name__)

class StatisticsScheduler:
    def __init__(self,telegram:TelegramClient,timezone_name="Europe/Moscow",hour=20,minute=0):
        self.telegram=telegram; self.tz=ZoneInfo(timezone_name); self.hour=hour; self.minute=minute
        self.evaluator=SignalOutcomeEvaluator(); self.reporter=StatisticsReporter(timezone_name)
    def _next(self,now):
        target=now.replace(hour=self.hour,minute=self.minute,second=0,microsecond=0)
        return target if target>now else target+timedelta(days=1)
    async def run(self,stop:asyncio.Event|None=None):
        stop=stop or asyncio.Event()
        while not stop.is_set():
            now=datetime.now(self.tz); target=self._next(now)
            try: await asyncio.wait_for(stop.wait(),max(0,(target-now).total_seconds()))
            except asyncio.TimeoutError: pass
            if stop.is_set(): break
            weekly=datetime.now(self.tz).weekday()==6
            try:
                with SessionLocal() as session:
                    self.evaluator.resolve_pending(session,datetime.now(self.tz))
                    daily=self.reporter.daily(session)
                    weekly_text=self.reporter.weekly(session) if weekly else None
                await self.telegram.send(daily)
                if weekly_text: await self.telegram.send(weekly_text)
            except Exception:
                logger.exception("Statistics report cycle failed; scheduler will continue")
