import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from research_os.auditor.drive_export import DriveExporter, encode_bundle

FOLDER = 'folder_0123456789'
JSON_ID = 'json_0123456789'
TEXT_ID = 'text_0123456789'


def bundle():
    return {'schema_version':1,'exported_at_utc':datetime.now(UTC).isoformat(),
            'reports':[{'run_id':'saved','full_text':'Полный отчёт'}], 'tasks':[]}


@pytest.mark.asyncio
async def test_private_existing_targets_updated_without_creation_and_unchanged_content_skipped():
    calls = []
    def handler(request):
        calls.append(request)
        if request.method=='GET':
            identity = request.url.path.split('/')[-1]
            mime = 'application/vnd.google-apps.folder' if identity==FOLDER else ('application/json' if identity==JSON_ID else 'text/plain')
            return httpx.Response(200,json={'id':identity,'mimeType':mime,'parents':[FOLDER],
                                           'permissions':[{'type':'user','role':'owner'}]})
        assert request.method=='PATCH' and request.url.params['uploadType']=='media'
        return httpx.Response(200,json={'id':request.url.path.split('/')[-1]})
    exporter = DriveExporter(SimpleNamespace(valid=True,token='placeholder'),FOLDER,JSON_ID,TEXT_ID,
                             httpx.MockTransport(handler))
    data = bundle()
    assert await exporter.publish(data)
    assert [request.method for request in calls]==['GET','GET','GET','PATCH','PATCH']
    assert json.loads(calls[-1].content)['reports'][0]['full_text']=='Полный отчёт'
    data['exported_at_utc']='later'
    assert not await exporter.publish(data)
    assert len(calls)==5


@pytest.mark.asyncio
@pytest.mark.parametrize('permissions',[[{'type':'anyone','role':'reader'}],[],[{'type':'domain','role':'reader'}]])
async def test_public_or_unverified_permissions_block_upload(permissions):
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200,json={'mimeType':'application/vnd.google-apps.folder','permissions':permissions})
    exporter = DriveExporter(SimpleNamespace(valid=True,token='placeholder'),FOLDER,JSON_ID,TEXT_ID,httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await exporter.publish(bundle())
    assert calls==['GET']


@pytest.mark.asyncio
async def test_failed_second_upload_retries_without_marking_export_complete():
    attempts = []
    def handler(request):
        identity = request.url.path.split('/')[-1]
        if request.method=='GET':
            return httpx.Response(200,json={'mimeType':'application/vnd.google-apps.folder' if identity==FOLDER else ('application/json' if identity==JSON_ID else 'text/plain'),
                'parents':[FOLDER],'permissions':[{'type':'user','role':'owner'}]})
        attempts.append(identity)
        return httpx.Response(503 if identity==JSON_ID and len(attempts)==2 else 200,json={'id':identity})
    exporter = DriveExporter(SimpleNamespace(valid=True,token='placeholder'),FOLDER,JSON_ID,TEXT_ID,httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await exporter.publish(bundle())
    assert exporter.digest is None
    assert await exporter.publish(bundle())
    assert attempts==[TEXT_ID,JSON_ID,TEXT_ID,JSON_ID]


def test_export_is_bounded_and_rejects_credential_patterns():
    data = bundle()
    data['tasks']=[{'conclusion':'sk-'+'secretplaceholder'*3}]
    with pytest.raises(ValueError):
        encode_bundle(data)
    data['tasks']=['x'*600000]
    with pytest.raises(ValueError):
        encode_bundle(data)


def test_setup_keeps_other_configuration_and_does_not_print_or_embed_key(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('drive_setup',Path(__file__).parents[1]/'deploy/configure-drive-export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = tmp_path/'key.json'
    key.write_text(json.dumps({'type':'service_account','token_uri':'https://oauth2.googleapis.com/token',
                              'client_email':'export@project.iam.gserviceaccount.com','private_key':'private-placeholder'}))
    env = tmp_path/'.env'
    env.write_text('POSTGRES_PASSWORD=existing\n')
    monkeypatch.setattr(module.os,"chown",lambda *args:None)
    assert module.setup(key,env,FOLDER,JSON_ID,TEXT_ID)=='export@project.iam.gserviceaccount.com'
    assert 'POSTGRES_PASSWORD=existing' in env.read_text()
    assert 'private-placeholder' not in env.read_text()
    assert (tmp_path/'secrets/drive-service-account.json').stat().st_mode & 0o777 == 0o400
    assert env.stat().st_mode & 0o777 == 0o600


def test_bundle_reads_only_journal_and_tasks_and_keeps_real_report_period(monkeypatch):
    from unittest.mock import MagicMock

    from research_os.auditor.drive_export import build_bundle
    monkeypatch.setattr('research_os.auditor.operations.operational_status',lambda session,now:{'observed_at_utc':now.isoformat()})
    now = datetime.now(UTC)
    session = MagicMock()
    report = {'verdict':'insufficient_data','comment':'Нет завершённых исходов.',
              'comment_evidence_ids':['cohort.completed'],'findings':[]}
    row = {'run_id':'saved','kind':'periodic','period_start':now,'period_end':now,
           'report':report,'snapshot':{'evidence':{'cohort.completed':0},'limitations':'Uncalibrated'}}
    first, second = MagicMock(), MagicMock()
    first.mappings.return_value.all.return_value=[row]
    second.mappings.return_value.all.return_value=[]
    session.execute.side_effect=[MagicMock(),MagicMock(),first,second]
    value = build_bundle(session,now)
    sql = '\n'.join(str(call.args[0]) for call in session.execute.call_args_list)
    assert 'READ ONLY' in sql and 'raw.events' not in sql
    assert 'snapshot' in sql and 'LIMIT 20' in sql
    assert value['reports'][0]['period_end']==now.isoformat()
    assert value['reports'][0]['full_text'].endswith('cohort.completed=0')
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_moved_target_blocks_every_upload():
    calls = []
    def handler(request):
        calls.append(request.method)
        identity = request.url.path.split('/')[-1]
        return httpx.Response(200,json={'mimeType':'application/vnd.google-apps.folder' if identity==FOLDER else 'application/json',
             'parents':['different-folder'],'permissions':[{'type':'user','role':'owner'}]})
    exporter = DriveExporter(SimpleNamespace(valid=True,token='placeholder'),FOLDER,JSON_ID,TEXT_ID,httpx.MockTransport(handler))
    with pytest.raises(ValueError,match='outside configured'):
        await exporter.publish(bundle())
    assert calls==['GET','GET']
