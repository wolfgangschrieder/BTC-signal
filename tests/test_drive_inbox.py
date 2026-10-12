import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from research_os.auditor.drive_export import DriveExporter
from research_os.auditor.drive_inbox import accept_requests, parse_inbox, request_hash

NOW = datetime.now(UTC)


def document():
    return {'schema_version':1,'tasks':[{'task_id':str(uuid4()),'created_at_utc':NOW.isoformat(),
        'expires_at_utc':(NOW+timedelta(days=1)).isoformat(),'kind':'experiment',
        'objective':'Compare technical and microstructure features on identical data.',
        'evidence_refs':['sample.states'],'acceptance_criteria':'Specify costs and chronological splits.',
        'reject_criteria':'Reject conclusions without held-out net returns.'}]}


def parsed(value=None):
    return parse_inbox(json.dumps(value or document()).encode())


@pytest.mark.parametrize('change',[
    lambda x:x.update(schema_version=2),
    lambda x:x.update(tasks=x['tasks']*2),
    lambda x:x['tasks'][0].update(kind='shell'),
    lambda x:x['tasks'][0].update(priority=1),
    lambda x:x['tasks'][0].update(command='execute'),
    lambda x:x['tasks'][0].update(expires_at_utc=(NOW+timedelta(days=8)).isoformat()),
    lambda x:x['tasks'][0].update(created_at_utc=NOW.replace(tzinfo=None).isoformat()),
])
def test_invalid_requests_rejected(change):
    data = document()
    change(data)
    with pytest.raises(ValidationError):
        parsed(data)


def test_byte_budget_and_immutable_hash():
    with pytest.raises(ValueError):
        parse_inbox(b' '*64001)
    request = parsed().tasks[0]
    assert request_hash(request)==request_hash(request)
    assert request_hash(request)!=request_hash(request.model_copy(update={'objective':'Different question'}))


def session_for(row=None, active=0):
    session = MagicMock()
    existing = MagicMock()
    existing.mappings.return_value.first.return_value=row
    count = MagicMock()
    count.scalar_one.return_value=active
    inserted = MagicMock()
    inserted.scalar_one_or_none.return_value=uuid4()
    session.execute.side_effect=[MagicMock(),MagicMock(),existing,count,inserted]
    return session


def test_duplicate_and_conflicting_id_do_not_insert():
    inbox = parsed()
    row = {'context':{'request_hash':request_hash(inbox.tasks[0])},'task_id':uuid4(),
           'status':'completed','run_id':uuid4(),'result':{'conclusion':'Plan only'}}
    session = session_for(row)
    assert accept_requests(session,inbox,NOW)[0]['status']=='completed'
    assert session.execute.call_count==3
    row['context']['request_hash']='other'
    session = session_for(row)
    assert accept_requests(session,inbox,NOW)[0]['reason']=='id_conflict'
    assert session.execute.call_count==3


def test_capacity_defers_and_expired_rejects_without_insert():
    inbox = parsed()
    session = session_for(active=3)
    assert accept_requests(session,inbox,NOW)[0]['status']=='deferred'
    assert session.execute.call_count==4
    session = session_for()
    assert accept_requests(session,inbox,NOW+timedelta(days=2))[0]['reason']=='expired'
    assert session.execute.call_count==3


@pytest.mark.asyncio
@pytest.mark.parametrize('public,moved,huge',[(True,False,False),(False,True,False),(False,False,True),(False,False,False)])
async def test_private_bounded_read_never_writes(public,moved,huge):
    calls = []
    body = json.dumps(document()).encode() if not huge else b'x'*64001
    def handler(request):
        calls.append(request)
        assert request.method=='GET'
        if request.url.params.get('alt')=='media':
            return httpx.Response(200,content=body)
        folder = request.url.path.endswith('folder_0123456789')
        return httpx.Response(200,json={'mimeType':'application/vnd.google-apps.folder' if folder else 'application/json',
            'parents':['other' if moved else 'folder_0123456789'],
            'permissions':[{'type':'anyone' if public else 'user','role':'reader'}]})
    exporter = DriveExporter(SimpleNamespace(valid=True,token='placeholder'),'folder_0123456789',
                             'json_0123456789','text_0123456789',httpx.MockTransport(handler))
    if public or moved or huge:
        with pytest.raises(ValueError):
            await exporter.read_inbox('inbox_0123456789')
    else:
        assert len((await exporter.read_inbox('inbox_0123456789')).tasks)==1
    assert not any(request.method!='GET' for request in calls)


def test_database_acceptance_survives_replay_and_transaction_rollback():
    url = os.environ.get('DATABASE_URL')
    if not url:
        pytest.skip('PostgreSQL required')
    engine = create_engine(url)
    inbox = parsed()
    key = 'drive:'+str(inbox.tasks[0].task_id)
    try:
        with engine.connect() as connection:
            from sqlalchemy.orm import Session
            with Session(bind=connection) as session:
                initial = accept_requests(session,inbox,NOW)[0]
                assert initial['status']=='waiting'
                session.commit()
                duplicate = accept_requests(session,inbox,NOW)[0]
                assert duplicate['task_id']==initial['task_id']
                assert session.execute(text('SELECT count(*) FROM intelligence.auditor_tasks WHERE dedup_key=:key'),{'key':key}).scalar_one()==1
                session.rollback()
                changed = inbox.model_copy(deep=True)
                changed.tasks[0].objective='Different objective to demonstrate conflict.'
                assert accept_requests(session,changed,NOW)[0]['reason']=='id_conflict'
                session.rollback()
                from research_os.auditor.tasks import TaskRepository
                session.execute(text("UPDATE intelligence.auditor_tasks SET context=jsonb_set(context,'{request,expires_at_utc}',to_jsonb(CAST(:expiry AS text))) WHERE dedup_key=:key"),
                                {'key':key,'expiry':(NOW-timedelta(hours=1)).isoformat()})
                TaskRepository().pending(session)
                assert session.execute(text('SELECT status FROM intelligence.auditor_tasks WHERE dedup_key=:key'),{'key':key}).scalar_one()=='failed'
                session.rollback()
    finally:
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM intelligence.auditor_tasks WHERE dedup_key=:key'),{'key':key})
        engine.dispose()
