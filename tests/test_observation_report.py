from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from research_os.research.observation_report import build_report, outcome_counts

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def test_target_counts_include_expired_and_ambiguous_not_pending():
    result = outcome_counts({'win': 3, 'loss': 1, 'expired': 4, 'ambiguous': 2, 'pending': 5})
    assert result['completed'] == 10
    assert result['win_fraction_among_win_loss'] == .75
    assert result['confirmed_tp1_fraction_among_completed'] == .3
    assert outcome_counts({})['confirmed_tp1_fraction_among_completed'] is None


def test_report_is_bounded_read_only_and_labels_rescoring():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    session.execute.return_value.mappings.return_value.__iter__.return_value = iter([])
    report = build_report(session, now=NOW, calibrated_models_configured=True)
    assert report['configured_calibration_models']
    assert report['state_sample']['states'] == 0
    assert report['emitted_forecast_cohort']['completed'] == 0
    assert 'not pinned calibration models' in report['limitations']
    queries = [str(call.args[0]) for call in session.execute.call_args_list]
    assert queries[0] == 'SET TRANSACTION READ ONLY'
    assert 'statement_timeout' in queries[1]
    assert 'LIMIT :limit' in queries[2]
    session.commit.assert_not_called()


@pytest.mark.parametrize('kwargs', [{'hours':0}, {'hours':169}, {'limit':0}, {'limit':5001}, {'threshold':2}])
def test_invalid_limits_rejected_before_query(kwargs):
    session = MagicMock()
    with pytest.raises(ValueError):
        build_report(session, **kwargs)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_daily_report_database_work_runs_off_event_loop(monkeypatch):
    import asyncio
    from threading import get_ident

    from research_os.pipeline.statistics_scheduler import StatisticsScheduler
    stop = asyncio.Event()
    threads = []

    class Telegram:
        async def send(self, text):
            assert text == 'daily'
            stop.set()

    scheduler = StatisticsScheduler(Telegram())
    monkeypatch.setattr(scheduler, '_next', lambda now: now)

    def reports(weekly):
        threads.append(get_ident())
        return 'daily', None

    monkeypatch.setattr(scheduler, '_build_reports', reports)
    await asyncio.wait_for(scheduler.run(stop), 1)
    assert threads and threads[0] != get_ident()


def test_postgres_report_preserves_ambiguous_denominator_and_is_read_only():
    import os
    from datetime import timedelta
    from uuid import uuid4

    from sqlalchemy import text

    from research_os.database.session import SessionLocal
    from research_os.signals.outcome_repository import SignalOutcomeRepository
    from research_os.signals.outcomes import OutcomeStatus, SignalOutcome
    if not os.getenv('DATABASE_URL'):
        pytest.skip('requires migrated PostgreSQL')
    now = datetime.now(UTC)
    symbol = 'OBSREPORT' + uuid4().hex[:10]
    ids = [uuid4().hex, uuid4().hex]
    try:
        with SessionLocal() as session:
            for identity, status in zip(ids, (OutcomeStatus.WIN, OutcomeStatus.AMBIGUOUS), strict=True):
                SignalOutcomeRepository().record_pending(session, SignalOutcome(
                    identity, symbol, 'long', now - timedelta(hours=1), 100, 95, 110, 115, 120,
                    .8, status, horizon_minutes=60, execution_policy='conservative-midpoint-v2'))
            session.commit()
        with SessionLocal() as session:
            report = build_report(session, symbol=symbol, now=now)
            cohort = report['emitted_forecast_cohort']
            assert cohort['completed'] == 2
            assert cohort['confirmed_tp1_fraction_among_completed'] == .5
            assert cohort['win_fraction_among_win_loss'] == 1
            assert len(report['cohort_status_counts']) == 2
            assert session.execute(text('SHOW transaction_read_only')).scalar_one() == 'on'
    finally:
        with SessionLocal() as session:
            session.execute(text('DELETE FROM signal_outcomes WHERE signal_id=ANY(:ids)'), {'ids':ids})
            session.commit()
