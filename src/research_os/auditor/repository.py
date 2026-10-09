from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text


class AuditorRepository:
    def reserve(self, session, *, kind, start, end, snapshot, model, tokens,
                budget_start, budget_end, daily_budget, daily_requests=290):
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        # A global transaction lock keeps overlapping workers inside one budget.
        session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
        if session.execute(text('SELECT 1 FROM intelligence.auditor_runs WHERE kind=:kind AND period_start=:start'),
                           {'kind':kind,'start':start}).first():
            return None
        usage = session.execute(text('''SELECT count(*) AS n,coalesce(sum(tokens),0) AS tokens
            FROM intelligence.auditor_runs WHERE created_at>=:start AND created_at<:end'''),
            {'start':budget_start,'end':budget_end}).mappings().one()
        if usage['n']>=daily_requests or usage['tokens']+tokens>daily_budget:
            return None
        identity = str(uuid4())
        session.execute(text('''INSERT INTO intelligence.auditor_runs
            (run_id,kind,period_start,period_end,status,model,tokens,snapshot,delivery_until)
            VALUES (:id,:kind,:start,:end,'started',:model,:tokens,CAST(:snapshot AS jsonb),:until)'''),
            {'id':identity,'kind':kind,'start':start,'end':end,'model':model,'tokens':tokens,
             'snapshot':json.dumps(snapshot,ensure_ascii=False),
             'until':end+timedelta(hours=24) if kind=='daily' else end+timedelta(minutes=10)})
        return identity

    def previous(self, session):
        rows = session.execute(text('''SELECT report
            FROM intelligence.auditor_runs WHERE status='completed'
            ORDER BY created_at DESC LIMIT 2''')).mappings()
        return [(row['report'].get('comment','')[:300] + ' | ' +
                 '; '.join(item.get('statement','')[:140] for item in row['report'].get('findings',[])[:2]))
                for row in rows if row['report']]

    def complete(self, session, identity, report, message, usage):
        session.execute(text('''UPDATE intelligence.auditor_runs
            SET status='completed',report=CAST(:report AS jsonb),message=:message,
                tokens=coalesce(CAST(:usage AS INTEGER),tokens)
            WHERE run_id=:id AND status='started' '''),
            {'id':identity,'report':report.model_dump_json(),'message':message,'usage':usage})

    def fail(self, session, identity, error):
        session.execute(text("UPDATE intelligence.auditor_runs SET status='failed',error_type=:error WHERE run_id=:id AND status='started'"),
                        {'id':identity,'error':type(error).__name__[:96]})

    def claim(self, session):
        return session.execute(text('''WITH candidate AS (
            SELECT run_id FROM intelligence.auditor_runs
            WHERE status='completed' AND sent_at IS NULL AND message IS NOT NULL
              AND available_at<=clock_timestamp() AND delivery_until>clock_timestamp()
              AND attempts<5 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
        ) UPDATE intelligence.auditor_runs AS item
          SET claim_token=:token,attempts=attempts+1,
              available_at=clock_timestamp()+interval '60 seconds'
          FROM candidate WHERE item.run_id=candidate.run_id
          RETURNING item.run_id,item.message,item.claim_token,item.attempts'''),
          {'token':str(uuid4())}).mappings().first()

    def delivered(self, session, item):
        session.execute(text('''UPDATE intelligence.auditor_runs SET sent_at=clock_timestamp(),claim_token=NULL
            WHERE run_id=:id AND claim_token=:token AND sent_at IS NULL'''),
            {'id':item['run_id'],'token':item['claim_token']})

    def retry(self, session, item, error):
        session.execute(text('''UPDATE intelligence.auditor_runs
            SET claim_token=NULL,delivery_error=:error,available_at=clock_timestamp()+interval '60 seconds'
            WHERE run_id=:id AND claim_token=:token AND sent_at IS NULL'''),
            {'id':item['run_id'],'token':item['claim_token'],'error':type(error).__name__[:96]})

    def prune(self, session, now, days=7):
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        session.execute(text('''DELETE FROM intelligence.auditor_runs WHERE run_id IN (
            SELECT run_id FROM intelligence.auditor_runs
            WHERE (kind='tick' AND created_at<:ticks) OR (kind='daily' AND created_at<:daily)
            ORDER BY created_at LIMIT 500)'''), {'ticks':now-timedelta(days=days),'daily':now-timedelta(days=90)})
