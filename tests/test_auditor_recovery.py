"""Recovery preserves failed rows and pays from the same global budget."""
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from research_os.auditor.repository import AuditorRepository, retry_allowed
from research_os.auditor.tasks import TaskRepository
from research_os.database.session import SessionLocal

NOW = datetime(2026,10,15,12,tzinfo=UTC)


def test_retry_is_bounded_delayed_and_only_for_known_failed_attempts():
    failed = {'status':'failed','created_at':NOW-timedelta(minutes=31)}
    assert retry_allowed([],NOW)
    assert retry_allowed([failed],NOW)
    assert not retry_allowed([failed,failed],NOW)
    assert not retry_allowed([failed | {'created_at':NOW}],NOW)
    for status in ('started','completed'):
        assert not retry_allowed([failed | {'status':status}],NOW)


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_retry_keeps_original_error_reservation_and_honors_budget():
    now = datetime.now(UTC)
    repo = AuditorRepository()
    args = dict(kind='daily',start=now-timedelta(days=1),end=now,snapshot={},model='test',
                tokens=100,budget_start=now-timedelta(hours=1),budget_end=now+timedelta(days=1),daily_budget=199)
    with SessionLocal() as session:
        try:
            first = repo.reserve(session,**args)
            assert first
            repo.fail(session,first,TimeoutError())
            assert repo.reserve(session,**args) is None  # cooldown
            session.execute(text("UPDATE intelligence.auditor_runs SET created_at=:old WHERE run_id=CAST(:id AS uuid)"),
                            {'id':first,'old':now-timedelta(minutes=31)})
            assert repo.reserve(session,**args) is None  # original reservation still counts
            second = repo.reserve(session,**(args | {'daily_budget':200}))
            assert second and second!=first
            repo.fail(session,second,ValueError())
            session.execute(text("UPDATE intelligence.auditor_runs SET created_at=:old WHERE run_id=CAST(:id AS uuid)"),
                            {'id':second,'old':now-timedelta(minutes=31)})
            assert repo.reserve(session,**(args | {'daily_budget':1000})) is None
            rows = session.execute(text('SELECT status,tokens,attempt_number,error_type FROM intelligence.auditor_runs WHERE kind=:kind AND period_start=:start ORDER BY attempt_number'),args).mappings().all()
            assert [r['attempt_number'] for r in rows]==[1,2]
            assert all(r['status']=='failed' and r['tokens']==100 for r in rows)
            assert rows[0]['error_type']=='TimeoutError'
        finally:
            session.rollback()


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_failed_task_gets_one_child_and_expired_drive_requests_are_not_replayed():
    now = datetime.now(UTC)
    tasks = TaskRepository()
    with SessionLocal() as session:
        try:
            session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
            original = str(tasks.enqueue(session,'costs','test:'+str(uuid4()),{'source':'operator'}))
            drive = str(tasks.enqueue(session,'costs','test:'+str(uuid4()),{'source':'drive'}))
            session.execute(text("UPDATE intelligence.auditor_tasks SET status='failed',updated_at=:old WHERE task_id IN (CAST(:id AS uuid),CAST(:drive AS uuid))"),
                            {'id':original,'drive':drive,'old':now-timedelta(minutes=31)})
            tasks.recover_failed(session,now)
            tasks.recover_failed(session,now)
            rows = session.execute(text("SELECT task_id,context FROM intelligence.auditor_tasks WHERE dedup_key=:key"),{'key':'retry:'+original}).mappings().all()
            assert len(rows)==1 and rows[0]['context']['retry_of']==original
            assert session.execute(text('SELECT 1 FROM intelligence.auditor_tasks WHERE dedup_key=:key'),{'key':'retry:'+drive}).first() is None
            child = rows[0]['task_id']
            session.execute(text("UPDATE intelligence.auditor_tasks SET status='failed',updated_at=:old WHERE task_id=:id"),{'id':child,'old':now-timedelta(minutes=31)})
            tasks.recover_failed(session,now)
            assert session.execute(text('SELECT 1 FROM intelligence.auditor_tasks WHERE dedup_key=:key'),{'key':'retry:'+str(child)}).first() is None
        finally:
            session.rollback()


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_unknown_spend_run_does_not_replay_its_crashed_task():
    now = datetime.now(UTC)
    tasks = TaskRepository()
    with SessionLocal() as session:
        try:
            session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
            identity = str(tasks.enqueue(session,'costs','test:'+str(uuid4()),{}))
            run = AuditorRepository().reserve(session,kind='periodic',start=now-timedelta(hours=4),
                end=now,snapshot={'tasks':[{'task_id':identity}]},model='test',tokens=100,
                budget_start=now-timedelta(seconds=1),budget_end=now+timedelta(days=1),daily_budget=1000)
            assert run
            tasks.prune(session,now+timedelta(minutes=11))
            tasks.recover_failed(session,now+timedelta(minutes=42))
            assert session.execute(text('SELECT 1 FROM intelligence.auditor_tasks WHERE dedup_key=:key'),
                                   {'key':'retry:'+identity}).first() is None
        finally:
            session.rollback()
