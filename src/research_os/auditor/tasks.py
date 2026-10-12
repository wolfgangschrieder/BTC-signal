"""Tasks contain fixed research questions, never executable model instructions."""
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

QUESTIONS = {
    'data_quality': 'ASSESS observations: distinguish missing history from source failure. No cause is proven by absent features alone; specify a falsifiable next check.',
    'signal_review': 'ASSESS saved hypothetical outcome and ambiguity reason. Do not infer actual execution or profitability from a TP touch.',
    'experiment': 'DESIGN ONLY: use project.feature_groups and project.experiment_protocol to specify TA-only / microstructure-only / combined comparison, fixed costs, chronological splits and net-risk metrics. Outcomes are not required to design it. completed means plan delivered, never experiment executed.',
    'hypothesis': 'DESIGN ONLY: propose one untested, falsifiable hypothesis motivated by current evidence or project feature groups, baseline, test and rejection criterion based on net returns/risk. No outcomes are required to formulate it; never claim confirmation.',
    'costs': 'DESIGN ONLY: inventory fees, spread/slippage, funding and manual-entry delay for perpetual. Use project.cost_scenarios as explicitly hypothetical sensitivity assumptions, not account tariffs. Unknown live tariffs do not prevent a plan; never invent measured costs or spot borrow fees.',
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
            WHERE status='waiting' AND (context->>'source' IS DISTINCT FROM 'drive'
                OR (context->'request'->>'expires_at_utc')::timestamptz>clock_timestamp())
            ORDER BY priority,created_at LIMIT 3""")).mappings().all()
        return [{'task_id':str(row['task_id']), 'kind':row['kind'],
                 'question':QUESTIONS[row['kind']], 'context':row['context']} for row in rows]

    def recent(self, session):
        rows = session.execute(text("""SELECT task_id,kind,status,result,updated_at
            FROM intelligence.auditor_tasks WHERE status IN ('completed','insufficient_data','failed')
            ORDER BY updated_at DESC,task_id DESC LIMIT 3""")).mappings().all()
        return [{'task_id':str(row['task_id']),'kind':row['kind'],'status':row['status'],
                 'conclusion':(row['result'] or {}).get('conclusion','')[:180],
                 'next_check':(row['result'] or {}).get('next_check','')[:120]}
                for row in rows]

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
        session.execute(text("""UPDATE intelligence.auditor_tasks
            SET status='failed',updated_at=:now,
                result='{"reason":"request_expired_before_assignment"}'::jsonb
            WHERE status='waiting' AND context->>'source'='drive'
                AND (context->'request'->>'expires_at_utc')::timestamptz<=:now"""),{'now':now})
        # Crashed/unknown-spend tasks are not silently retried with a second API call.
        session.execute(text("""UPDATE intelligence.auditor_tasks SET status='failed',updated_at=:now
            WHERE status='running' AND updated_at<:stale"""), {'now':now,'stale':now-timedelta(minutes=10)})
        session.execute(text("""DELETE FROM intelligence.auditor_tasks WHERE task_id IN (
            SELECT task_id FROM intelligence.auditor_tasks WHERE updated_at<:old
            ORDER BY updated_at LIMIT 500)"""), {'old':now-timedelta(days=90)})


def discover_tasks(session, evidence, now, repo):
    day = now.date().isoformat()
    repo.enqueue(session,'experiment','initial-ablation-v2',{'goal':'Compare feature groups with realistic costs; design only.'},3)
    if evidence['settings.fee_bps_assumed']==0 or evidence['settings.slippage_bps_assumed']==0:
        repo.enqueue(session,'costs','zero-costs-v2',{'fee_bps':evidence['settings.fee_bps_assumed'],
                     'slippage_bps':evidence['settings.slippage_bps_assumed']},1)
    states = evidence['sample.states']
    if states and any(evidence[f'sample.feature_available.{tf}']==0 for tf in ('tf_1h_return_1','tf_4h_return_1')):
        repo.enqueue(session,'data_quality','timeframe-history:'+day,{'states':states,
                     'available':{tf:evidence[f'sample.feature_available.{tf}'] for tf in ('tf_1h_return_1','tf_4h_return_1')}},1)
    repo.enqueue(session,'hypothesis','hypothesis-v2:'+day,{'scope':'Current observed data; no profitability claim'},3)
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
