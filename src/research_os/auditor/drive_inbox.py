"""Bounded research requests: Drive is transport, PostgreSQL owns acceptance."""
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from research_os.auditor.tasks import TaskRepository

MAX_INBOX_BYTES = 64_000


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    task_id: UUID
    created_at_utc: datetime
    expires_at_utc: datetime
    kind: Literal['data_quality','signal_review','costs','experiment','hypothesis']
    objective: str = Field(min_length=10,max_length=300)
    evidence_refs: list[str] = Field(max_length=8)
    acceptance_criteria: str = Field(min_length=10,max_length=200)
    reject_criteria: str = Field(min_length=10,max_length=200)
    priority: Literal[2,3] = 3

    @model_validator(mode='after')
    def valid_window(self):
        for value in (self.created_at_utc,self.expires_at_utc):
            if value.utcoffset()!=timedelta(0):
                raise ValueError('UTC timestamps required')
        if not timedelta(0)<self.expires_at_utc-self.created_at_utc<=timedelta(days=7):
            raise ValueError('Request lifetime must be at most seven days')
        if any(not 1<=len(value)<=160 for value in self.evidence_refs):
            raise ValueError('Invalid evidence reference')
        if len(json.dumps(self.model_dump(mode='json'),ensure_ascii=False).encode())>2000:
            raise ValueError('Request exceeds context budget')
        return self


class ResearchInbox(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal[1]
    tasks: list[ResearchRequest] = Field(max_length=10)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({item.task_id for item in self.tasks})!=len(self.tasks):
            raise ValueError('Duplicate request IDs')
        return self


def parse_inbox(body):
    if len(body)>MAX_INBOX_BYTES:
        raise ValueError('Inbox byte budget exceeded')
    if re.search(rb'sk-[A-Za-z0-9_-]{12,}|\d{6,}:[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY',body):
        raise ValueError('Credential-like inbox rejected')
    # JSON mode parses UUID/timestamps while retaining strict scalar validation.
    return ResearchInbox.model_validate_json(body)


def request_hash(request):
    return hashlib.sha256(json.dumps(request.model_dump(mode='json'),sort_keys=True,
                                    ensure_ascii=False).encode()).hexdigest()


def accept_requests(session, inbox, now):
    session.execute(text("SET LOCAL statement_timeout = '5s'"))
    # Same lock as the operator/analyst queue; no API calls inside this transaction.
    session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
    receipts = []
    repo = TaskRepository()
    for request in inbox.tasks:
        key = 'drive:'+str(request.task_id)
        digest = request_hash(request)
        row = session.execute(text("""SELECT task_id,status,context,run_id,result
            FROM intelligence.auditor_tasks WHERE dedup_key=:key"""),{'key':key}).mappings().first()
        receipt = {'request_id':str(request.task_id)}
        if row:
            if row['context'].get('request_hash')!=digest:
                receipt.update(status='rejected',reason='id_conflict')
            else:
                receipt.update(status=row['status'],task_id=str(row['task_id']),
                               run_id=str(row['run_id']) if row['run_id'] else None,result=row['result'])
        elif request.created_at_utc>now+timedelta(minutes=5):
            receipt.update(status='rejected',reason='future_request')
        elif request.expires_at_utc<=now:
            receipt.update(status='rejected',reason='expired')
        else:
            active = session.execute(text("""SELECT count(*) FROM intelligence.auditor_tasks
                WHERE dedup_key LIKE 'drive:%' AND status IN ('waiting','running')""")).scalar_one()
            if active>=3:
                receipt.update(status='deferred',reason='external_queue_full')
            else:
                identity = repo.enqueue(session,request.kind,key,
                    {'source':'drive','request_hash':digest,'request':request.model_dump(mode='json')},
                    request.priority)
                if identity:
                    receipt.update(status='waiting',task_id=str(identity),run_id=None,result=None)
                else:
                    receipt.update(status='deferred',reason='queue_full')
        receipts.append(receipt)
    return receipts


def import_requests(inbox):
    from research_os.database.session import SessionLocal
    with SessionLocal() as session:
        receipts = accept_requests(session,inbox,datetime.now(UTC))
        session.commit()
    return receipts
