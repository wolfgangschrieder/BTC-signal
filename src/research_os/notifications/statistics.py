from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from research_os.signals.outcome_repository import SignalOutcomeRepository

class StatisticsReporter:
    def __init__(self,timezone_name="Europe/Moscow"): self.timezone=ZoneInfo(timezone_name); self.repo=SignalOutcomeRepository()
    def format_period(self,session:Session,since:datetime,title:str)->str:
        s=self.repo.summary(session,since)
        resolved=s["wins"]+s["losses"]; rate=f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "—"
        return (f"📊 {title}\n\n"
                f"Период: {since.astimezone(self.timezone):%d.%m.%Y %H:%M} — {datetime.now(self.timezone):%d.%m.%Y %H:%M}\n\n"
                f"Всего завершено: {s['total']}\n"
                f"🟢 Успешных: {s['wins']}\n"
                f"🔴 Неудачных: {s['losses']}\n"
                f"⚪ Истёкших: {s['expired']}\n"
                f"Win rate: {rate}\n"
                f"\nУчитываются только фактически разрешённые сигналы. Незавершённые сигналы в статистику не входят.")
    def daily(self,session): return self.format_period(session,datetime.now(self.timezone)-timedelta(hours=24),"СТАТИСТИКА ЗА 24 ЧАСА")
    def weekly(self,session): return self.format_period(session,datetime.now(self.timezone)-timedelta(days=7),"СТАТИСТИКА ЗА 7 ДНЕЙ")
