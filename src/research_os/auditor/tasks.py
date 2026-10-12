"""Tasks contain fixed research questions, never executable model instructions."""
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

QUESTIONS = {
    'data_quality': 'Explain changes in timeframe availability; distinguish missing history from source failure. State missing evidence and a falsifiable next check.',
    'signal_review': 'Review the saved hypothetical signal outcome and ambiguity reason. Do not infer execution or profitability from a TP touch.',
    'experiment': 'Design an ablation: technical analysis only, microstructure only, combined; identical costs and time splits, no holdout parameter selection. Propose a test, do not invent results.',
    'hypothesis': 'Propose at most one falsifiable research hypothesis supported by evidence. Specify baseline, out-of-sample test and rejection criterion; insufficient_data is valid.',
    'costs': 'Identify missing execution costs and propose explicit sensitivity scenarios. No actual fees are supplied; do not invent account-specific rates.',
}


class TaskRepository:
    def enqueue(self, session, kind, key, context, priority=2):
        identity = str(uuid4())
        return session.execute(text("""INSERT INTO intelligence.auditor_tasks
            (task_id,dedup_key,kind,priority,context)
            SELECT :id,:key,:kind,:priority,CAST(:context AS jsonb)
            WHERE (SELECT count(*) FROM intelligence.auditor_tasks WHERE status IN ('waiting','running'))<100
            ON CONFLICT (dedup_key) DO NOTHING RETURNING task_id"""),
            {'id':identity,'key':key,'kind':kind,'priority':priority,
             'context':json.dumps(context,ensure_ascii=False)}).scalar_one_or_none()

    def pending(self, session):
        rows = session.execute(text("""SELECT task_id,kind,context FROM intelligence.auditor_tasks
            WHERE status='waiting' ORDER BY priority,created_at LIMIT 3""")).mappings().all()
        return [{'task_id':str(row['task_id']), 'kind':row['kind'],
                 'question':QUESTIONS[row['kind']], 'context':row['context']} for row in rows]

    def finish(self, session, identity, results):
        for result in results:
            session.execute(text("""UPDATE intelligence.auditor_tasks
                SET status=:status,result=CAST(:result AS jsonb),updated_at=clock_timestamp()
                WHERE task_id=CAST(:id AS uuid) AND run_id=CAST(:run AS uuid) AND status='running'"""),
                {'id':result.task_id,'run':identity,'status':result.status,'result':result.model_dump_json()})

    def fail(self, session, identity):
        session.execute(text("""UPDATE intelligence.auditor_tasks SET status='failed',updated_at=clock_timestamp()
            WHERE run_id=CAST(:id AS uuid) AND status='running'"""), {'id':identity})

    def prune(self, session, now):
        # Crashed/unknown-spend tasks are not silently retried with a second API call.
        session.execute(text("""UPDATE intelligence.auditor_tasks SET status='failed',updated_at=:now
            WHERE status='running' AND updated_at<:stale"""), {'now':now,'stale':now-timedelta(minutes=10)})
        session.execute(text("""DELETE FROM intelligence.auditor_tasks WHERE task_id IN (
            SELECT task_id FROM intelligence.auditor_tasks WHERE updated_at<:old
            ORDER BY updated_at LIMIT 500)"""), {'old':now-timedelta(days=90)})


def discover_tasks(session, evidence, now, repo):
    day = now.date().isoformat()
    repo.enqueue(session,'experiment','initial-ablation-v1',{'goal':'Compare feature groups with realistic costs; design only.'},3)
    if evidence['settings.fee_bps_assumed']==0 or evidence['settings.slippage_bps_assumed']==0:
        repo.enqueue(session,'costs','zero-costs-v1',{'fee_bps':evidence['settings.fee_bps_assumed'],
                     'slippage_bps':evidence['settings.slippage_bps_assumed']},1)
    states = evidence['sample.states']
    if states and any(evidence[f'sample.feature_available.{tf}']==0 for tf in ('tf_1h_return_1','tf_4h_return_1')):
        repo.enqueue(session,'data_quality','timeframe-history:'+day,{'states':states,
                     'available':{tf:evidence[f'sample.feature_available.{tf}'] for tf in ('tf_1h_return_1','tf_4h_return_1')}},1)
    repo.enqueue(session,'hypothesis','hypothesis:'+day,{'scope':'Current observed data; no profitability claim'},3)
    rows = session.execute(text("""SELECT signal_id,signal_time,direction,status,reason,execution_policy,
        entry_price,stop_loss,tp1,fee_bps,slippage_bps FROM signal_outcomes
        WHERE signal_time>=:lower AND status<>'pending' ORDER BY signal_time DESC LIMIT 20"""),
        {'lower':now-timedelta(days=2)}).mappings().all()
    for row in rows:
        context = {key:str(value) if key in ('signal_id','signal_time') else value for key,value in row.items()}
        # Decimal prices are encoded without treating them as executable instructions.
        context = json.loads(json.dumps(context,default=str))
        repo.enqueue(session,'signal_review','signal:'+str(row['signal_id']),context,1)


def operational_findings(evidence):
    issues = []
    for event, maximum in (('trade',120),('ticker',120),('orderbook_update',120),('candle',180)):
        key = f'data.{event}_age_seconds'
        age = evidence[key]
        if age is None or age>maximum:
            issues.append((key,f'Поток {event}: нет свежих данных за контрольный интервал.'))
    last = evidence.get('sample.last_decision_utc')
    from datetime import datetime
    if last is None or (datetime.fromisoformat(evidence['window.end_utc'])-datetime.fromisoformat(last)).total_seconds()>180:
        issues.append(('sample.last_decision_utc','Новые расчёты состояний отсутствуют более трёх минут.'))
    if (evidence.get('signals.telegram_max_attempts') or 0)>=5:
        issues.append(('signals.telegram_max_attempts','Очередь сигналов содержит уведомления с пятью или более попытками доставки.'))
    if evidence['storage.database_bytes']>=18_000_000_000:
        issues.append(('storage.database_bytes','Размер БД достиг лимита 18 ГБ.'))
    return issues


def list_tasks(kind=None):
    from research_os.database.session import SessionLocal
    with SessionLocal() as session:
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        if kind:
            session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
            identity = TaskRepository().enqueue(session,kind,'manual:'+str(uuid4()),{'source':'operator'},2)
            session.commit()
            print('Задача создана:',identity if identity else 'очередь заполнена')
        rows = session.execute(text("""SELECT task_id,kind,status,run_id,result FROM intelligence.auditor_tasks
            ORDER BY created_at DESC LIMIT 20""")).mappings().all()
        print(json.dumps([dict(row) for row in rows],ensure_ascii=False,default=str,indent=2))
    return 0
