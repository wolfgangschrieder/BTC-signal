import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from research_os.auditor.client import prepare_prompt
from research_os.auditor.models import AnalystReport, message, summary_message
from research_os.auditor.repository import AuditorRepository
from research_os.auditor.runtime import windows
from research_os.auditor.tasks import TaskRepository, operational_findings
from research_os.database.session import SessionLocal


def report(task_id=None):
    data = {'verdict':'insufficient_data','comment':'Нужны данные.',
            'comment_evidence_ids':['sample.states'],'findings':[]}
    if task_id:
        data['task_results'] = [{'task_id':task_id,'status':'insufficient_data',
            'conclusion':'Нет истории запусков.','evidence_ids':['sample.states'],
            'next_check':'Сопоставить закрытые свечи и время запуска.'}]
    return AnalystReport.model_validate(data)


def test_tasks_require_exact_ids_and_existing_evidence():
    identity = str(uuid4())
    value = report(identity)
    value.validate_tasks([{'task_id':identity}]).validate_evidence({'sample.states':59})
    with pytest.raises(ValueError):
        value.validate_tasks([])
    with pytest.raises(ValueError):
        value.validate_evidence({})
    value.task_results.append(value.task_results[0])
    with pytest.raises(ValueError):
        value.validate_tasks([{'task_id':identity}])


def test_four_hour_windows_do_not_overlap_and_use_moscow_midnight():
    now = datetime(2026,10,12,22,10,tzinfo=UTC)
    tick, daily = windows(now)
    assert tick[1:] == (datetime(2026,10,12,17,tzinfo=UTC),datetime(2026,10,12,21,tzinfo=UTC))
    assert windows(now+timedelta(hours=4))[0][1] == tick[2]
    assert daily[2] == tick[2]


def test_healthy_monitor_and_stale_streams():
    now = datetime(2026,10,12,21,tzinfo=UTC)
    evidence = {'window.end_utc':now.isoformat(),'sample.last_decision_utc':now.isoformat(),
                'signals.telegram_max_attempts':0,'storage.database_bytes':2_000_000_000}
    for event in ('trade','ticker','orderbook_update','candle'):
        evidence[f'data.{event}_age_seconds'] = 1
    assert operational_findings(evidence) == []
    evidence['data.trade_age_seconds'] = None
    evidence['sample.last_decision_utc'] = (now-timedelta(minutes=4)).isoformat()
    evidence['signals.telegram_max_attempts'] = 5
    evidence['storage.database_bytes'] = 18_000_000_000
    assert {key for key,_ in operational_findings(evidence)} == {
        'data.trade_age_seconds','sample.last_decision_utc','signals.telegram_max_attempts','storage.database_bytes'}


def test_summary_is_short_but_full_report_keeps_task_details():
    now = datetime.now(UTC)
    value = report(str(uuid4()))
    short = summary_message(value,'tick',now-timedelta(hours=4),now,'saved-id')
    assert '4 ЧАСА' in short and 'saved-id' in short
    assert len(short.encode('utf-16-le'))//2 < 3500
    full = message(value,'tick',now-timedelta(hours=4),now,{'sample.states':59})
    assert value.task_results[0].next_check in full


def test_task_payload_fits_budget_and_preserves_question():
    tasks = [{'task_id':str(uuid4()),'kind':'data_quality','question':'Check history',
              'context':{'states':240}} for _ in range(3)]
    payload, size = prepare_prompt({'evidence':{'sample.states':240},'limitations':'','tasks':tasks},[])
    assert 'Check history' in payload and size<16000


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_task_assignment_result_dedup_and_summary_delivery_are_atomic():
    now = datetime.now(UTC)
    tasks, runs = TaskRepository(), AuditorRepository()
    with SessionLocal() as session:
        try:
            session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
            key = 'test:'+str(uuid4())
            identity = str(tasks.enqueue(session,'data_quality',key,{'states':59}))
            assert tasks.enqueue(session,'data_quality',key,{'states':59}) is None
            selected = tasks.pending(session)
            assert any(item['task_id']==identity for item in selected)
            args = {'kind': 'tick','start': now-timedelta(hours=4),'end': now,
                        'snapshot': {'evidence':{'sample.states':59},'tasks':[{'task_id':identity}]},
                        'model': 'test','tokens': 20,'budget_start': now-timedelta(seconds=1),
                        'budget_end': now+timedelta(days=1),'daily_budget': 1000}
            run = runs.reserve(session,**args)
            assert run
            assert runs.reserve(session,**{**args,'start':now-timedelta(hours=3)}) is None
            runs.complete(session,run,report(identity),'full body',20,'summary')
            row = session.execute(text('SELECT status,result FROM intelligence.auditor_tasks WHERE task_id=CAST(:id AS uuid)'),{'id':identity}).mappings().one()
            assert row['status']=='insufficient_data' and row['result']['next_check']
            assert runs.claim(session)['message']=='summary'
            assert session.execute(text('SELECT message FROM intelligence.auditor_runs WHERE run_id=CAST(:id AS uuid)'),{'id':run}).scalar_one()=='full body'
        finally:
            session.rollback()


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_crashed_tasks_fail_without_automatic_paid_retry():
    now = datetime.now(UTC)
    tasks, runs = TaskRepository(), AuditorRepository()
    with SessionLocal() as session:
        try:
            identity = str(tasks.enqueue(session,'costs','test:'+str(uuid4()),{}))
            run = runs.reserve(session,kind='tick',start=now-timedelta(hours=4),end=now,
                snapshot={'tasks':[{'task_id':identity}]},model='test',tokens=20,
                budget_start=now-timedelta(seconds=1),budget_end=now+timedelta(days=1),daily_budget=1000)
            tasks.prune(session,now+timedelta(minutes=11))
            assert session.execute(text('SELECT status FROM intelligence.auditor_tasks WHERE task_id=CAST(:id AS uuid)'),{'id':identity}).scalar_one()=='failed'
            assert session.execute(text('SELECT status FROM intelligence.auditor_runs WHERE run_id=CAST(:id AS uuid)'),{'id':run}).scalar_one()=='started'
        finally:
            session.rollback()


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_old_halfhour_slot_does_not_block_new_fourhour_report():
    now = datetime.now(UTC)
    repo = AuditorRepository()
    with SessionLocal() as session:
        try:
            arguments = {'start':now-timedelta(hours=4),'snapshot':{},'model':'test','tokens':10,
                         'budget_start':now-timedelta(seconds=1),'budget_end':now+timedelta(days=1),
                         'daily_budget':1000}
            assert repo.reserve(session,kind='tick',end=now-timedelta(hours=3,minutes=30),**arguments)
            assert repo.reserve(session,kind='periodic',end=now,**arguments)
        finally:
            session.rollback()
