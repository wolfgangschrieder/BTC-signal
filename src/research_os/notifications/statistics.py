from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from research_os.signals.outcome_repository import SignalOutcomeRepository

class StatisticsReporter:
    def __init__(self,timezone_name="Europe/Moscow"): self.timezone=ZoneInfo(timezone_name); self.repo=SignalOutcomeRepository()
    def format_period(self,session:Session,since:datetime,title:str)->str:
        s=self.repo.summary(session,since)
        rate=f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "—"
        confirmation = f"{s['wins']/s['total']:.1%}" if s["total"] else "—"
        return (f"📊 {title}\n\n"
                f"Период: {since.astimezone(self.timezone):%d.%m.%Y %H:%M} — {datetime.now(self.timezone):%d.%m.%Y %H:%M}\n\n"
                f"Всего завершено: {s['total']}\n"
                f"🟢 Подтверждён TP1: {s['wins']}\n"
                f"🔴 Достигнут SL: {s['losses']}\n"
                f"⚪ Истёкших: {s['expired']}\n"
                f"❔ Неоднозначных: {s.get('ambiguous',0)}\n"
                f"Доля WIN среди WIN/LOSS: {rate}\n"
                f"Подтверждение TP1 среди всех завершённых: {confirmation}\n"
                f"\nИсходы смоделированы по минутным свечам, это не реальные сделки. "
                f"Истёкшие и неоднозначные исходы считаются неподтверждением TP1. "
                f"Незавершённые сигналы исключены; точность вероятностей и прибыльность не подтверждены.")
    def daily(self,session): return self.format_period(session,datetime.now(self.timezone)-timedelta(hours=24),"СТАТИСТИКА ЗА 24 ЧАСА")
    def weekly(self,session): return self.format_period(session,datetime.now(self.timezone)-timedelta(days=7),"СТАТИСТИКА ЗА 7 ДНЕЙ")
