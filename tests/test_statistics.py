from datetime import datetime,timezone
from research_os.notifications.statistics import StatisticsReporter
from research_os.signals.models import SignalDirection,SignalLevels,SignalResult

def test_signal_has_stable_id():
    s=SignalResult("BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),SignalDirection.LONG,.8,.1,SignalLevels(1,2,.5,3,4,5,1,2,3),.5,2,("x",),())
    assert s.signal_id==s.signal_id and len(s.signal_id)==32

def test_statistics_report_contains_outcome_counts():
    class R:
        def summary(self,session,since): return {"total":5,"wins":3,"losses":1,"expired":1,"win_rate":.75}
    r=StatisticsReporter("Europe/Moscow"); r.repo=R()
    text=r.format_period(None,datetime(2026,1,1,tzinfo=timezone.utc),"TEST")
    assert "Подтверждён TP1: 3" in text and "Достигнут SL: 1" in text and "Доля WIN среди WIN/LOSS: 75.0%" in text


def test_expired_and_ambiguous_reduce_confirmation_fraction():
    class Repository:
        def summary(self, session, since):
            return {'total':10,'wins':3,'losses':1,'expired':4,'ambiguous':2,'win_rate':.75}
    reporter = StatisticsReporter()
    reporter.repo = Repository()
    message = reporter.format_period(None, datetime(2026,1,1,tzinfo=timezone.utc), 'TEST')
    assert 'Неоднозначных: 2' in message
    assert 'Доля WIN среди WIN/LOSS: 75.0%' in message
    assert 'Подтверждение TP1 среди всех завершённых: 30.0%' in message
    assert 'не реальные сделки' in message
