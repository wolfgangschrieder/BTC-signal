"""Isolated, bounded export into two pre-created private Drive files."""
import asyncio
import hashlib
import json
import logging
import os
import re
import signal
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import text

from research_os.auditor.models import AnalystReport, message
from research_os.database.session import SessionLocal

logger = logging.getLogger(__name__)
MAX_BYTES = 512_000


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,160}', value or ''):
        raise ValueError('Invalid Drive identifier')
    return value


def build_bundle(session, now):
    session.execute(text('SET TRANSACTION READ ONLY'))
    session.execute(text("SET LOCAL statement_timeout = '5s'"))
    rows = session.execute(text("""SELECT DISTINCT ON (kind) run_id,kind,period_start,period_end,report,snapshot
        FROM intelligence.auditor_runs WHERE status='completed' AND kind IN ('periodic','daily')
        ORDER BY kind,period_end DESC,created_at DESC LIMIT 2""")).mappings().all()
    reports = []
    for row in rows:
        report = AnalystReport.model_validate(row['report'])
        reports.append({'run_id':str(row['run_id']),'kind':row['kind'],
            'period_start':row['period_start'].isoformat(),'period_end':row['period_end'].isoformat(),
            'report':report.model_dump(), 'evidence':row['snapshot']['evidence'],
            'limitations':row['snapshot'].get('limitations',''),
            'full_text':message(report,row['kind'],row['period_start'],row['period_end'],row['snapshot']['evidence'])})
    tasks = session.execute(text("""SELECT task_id,kind,status,run_id,result,updated_at
        FROM intelligence.auditor_tasks ORDER BY updated_at DESC,task_id DESC LIMIT 20""")).mappings().all()
    return {'schema_version':1,'status':'ready' if reports else 'no_completed_reports',
            'exported_at_utc':now.isoformat(),'reports':reports,
            'tasks':[dict(row) for row in tasks],
            'limitations':'Saved analyst interpretations, not verified profitability. Task statuses are current reads. No market raw events, configuration secrets or account data are exported.'}


def encode_bundle(bundle):
    payload = json.dumps(bundle,ensure_ascii=False,default=str,sort_keys=True).encode()
    if len(payload)>MAX_BYTES:
        raise ValueError('Export exceeds byte budget')
    if re.search(rb'sk-[A-Za-z0-9_-]{12,}|\d{6,}:[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY',payload):
        raise ValueError('Credential-like export rejected')
    text_body = ('BTC-signal · экспорт UTC: '+bundle['exported_at_utc']+'\n'+
                 '\n\n'.join('ID: '+item['run_id']+'\n'+item['full_text'] for item in bundle['reports'])+
                 '\n\nЗАДАЧИ\n'+json.dumps(bundle['tasks'],ensure_ascii=False,default=str,indent=2)).encode()
    if 'research_inbox' in bundle:
        text_body += ('\n\nПОДТВЕРЖДЕНИЯ DRIVE\n'+json.dumps(bundle['research_inbox'],ensure_ascii=False,default=str,indent=2)).encode()
    if len(text_body)>MAX_BYTES:
        raise ValueError('Text export exceeds byte budget')
    stable = {key:value for key,value in bundle.items() if key!='exported_at_utc'}
    digest = hashlib.sha256(json.dumps(stable,ensure_ascii=False,default=str,sort_keys=True).encode()).hexdigest()
    return payload,text_body,digest


def credentials_from_file(path):
    # Fixed token origin; no domain-wide delegation or key/body logging.
    from google.oauth2 import service_account
    info = json.loads(Path(path).read_text())
    if info.get('type')!='service_account' or info.get('token_uri')!='https://oauth2.googleapis.com/token':
        raise ValueError('Expected Google service-account credentials')
    if not str(info.get('client_email','')).endswith('.iam.gserviceaccount.com'):
        raise ValueError('Invalid service account')
    return service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/drive'])


class DriveExporter:
    def __init__(self, credentials, folder_id, json_id, text_id, transport=None):
        self.credentials = credentials
        self.folder = identifier(folder_id)
        self.targets = ((identifier(json_id),'application/json'),(identifier(text_id),'text/plain'))
        if len({self.folder,json_id,text_id})!=3:
            raise ValueError('Drive targets must be distinct')
        self.transport = transport
        self.digest = None

    async def read_inbox(self, inbox_id):
        from research_os.auditor.drive_inbox import MAX_INBOX_BYTES, parse_inbox
        identity = identifier(inbox_id)
        if identity in {self.folder,*(item[0] for item in self.targets)}:
            raise ValueError('Inbox must be a separate file')
        token = await asyncio.to_thread(self.token)
        async with httpx.AsyncClient(timeout=20,transport=self.transport,follow_redirects=False) as client:
            headers = {'Authorization':'Bearer '+token}
            for target,mime in ((self.folder,'application/vnd.google-apps.folder'),(identity,'application/json')):
                response = await client.get('https://www.googleapis.com/drive/v3/files/'+target,
                    params={'fields':'mimeType,parents,trashed,permissions(type,role)','supportsAllDrives':'true'},headers=headers)
                response.raise_for_status()
                data = response.json()
                permissions = data.get('permissions',[])
                if not permissions or any(item.get('type')!='user' for item in permissions):
                    raise ValueError('Private user-only inbox required')
                if data.get('trashed') or data.get('mimeType')!=mime:
                    raise ValueError('Unexpected inbox target')
                if target==identity and data.get('parents')!=[self.folder]:
                    raise ValueError('Inbox outside configured folder')
            async with client.stream('GET','https://www.googleapis.com/drive/v3/files/'+identity,
                                     params={'alt':'media','supportsAllDrives':'true'},headers=headers) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    body.extend(chunk)
                    if len(body)>MAX_INBOX_BYTES:
                        raise ValueError('Inbox byte budget exceeded')
            return parse_inbox(bytes(body))

    def token(self):
        if not self.credentials.valid:
            from google.auth.transport.requests import Request
            request = Request()
            def bounded_request(*args, **kwargs):
                kwargs['timeout'] = 15
                return request(*args,**kwargs)
            self.credentials.refresh(bounded_request)
        return self.credentials.token

    async def publish(self, bundle):
        payload, text_body, digest = encode_bundle(bundle)
        if digest==self.digest:
            return False
        token = await asyncio.to_thread(self.token)
        async with httpx.AsyncClient(timeout=20,transport=self.transport,follow_redirects=False) as client:
            headers = {'Authorization':'Bearer '+token}
            for identity, mime in ((self.folder,'application/vnd.google-apps.folder'),*self.targets):
                response = await client.get('https://www.googleapis.com/drive/v3/files/'+identity,
                    params={'fields':'id,mimeType,parents,trashed,permissions(type,role)','supportsAllDrives':'true'},headers=headers)
                response.raise_for_status()
                metadata = response.json()
                permissions = metadata.get('permissions',[])
                if not permissions or any(item.get('type')!='user' for item in permissions):
                    raise ValueError('Private user-only Drive permissions required')
                if metadata.get('trashed') or metadata.get('mimeType')!=mime:
                    raise ValueError('Unexpected Drive target')
                if identity!=self.folder and metadata.get('parents')!=[self.folder]:
                    raise ValueError('Drive target outside configured folder')
            # Update mirrors first and canonical JSON last; readers should prefer JSON.
            for (identity,mime),body in ((self.targets[1],text_body),(self.targets[0],payload)):
                response = await client.patch('https://www.googleapis.com/upload/drive/v3/files/'+identity,
                    params={'uploadType':'media','fields':'id','supportsAllDrives':'true'},
                    headers={**headers,'Content-Type':mime},content=body)
                response.raise_for_status()
        self.digest = digest
        return True


def read_bundle():
    with SessionLocal() as session:
        return build_bundle(session,datetime.now(UTC))


async def run(once=False):
    exporter = DriveExporter(credentials_from_file(os.environ['GOOGLE_APPLICATION_CREDENTIALS']),
        os.environ['DRIVE_EXPORT_FOLDER_ID'],os.environ['DRIVE_EXPORT_JSON_ID'],os.environ['DRIVE_EXPORT_TEXT_ID'])
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM,signal.SIGINT):
        loop.add_signal_handler(name,stop.set)
    while not stop.is_set():
        inbox_receipts = None
        inbox_id = os.environ.get('DRIVE_RESEARCH_INBOX_ID','').strip()
        if inbox_id:
            try:
                from research_os.auditor.drive_inbox import import_requests
                inbox = await asyncio.wait_for(exporter.read_inbox(inbox_id),timeout=75)
                inbox_receipts = await asyncio.to_thread(import_requests,inbox)
            except Exception as error:  # noqa: BLE001 - no untrusted body or credential-bearing messages
                logger.warning('Drive inbox failed (%s)',type(error).__name__)
                inbox_receipts = {'status':'unavailable','error_type':type(error).__name__}
        try:
            bundle = await asyncio.to_thread(read_bundle)
            if inbox_receipts is not None:
                bundle['research_inbox'] = inbox_receipts
            if await asyncio.wait_for(exporter.publish(bundle),timeout=150):
                logger.info('Private Drive export completed reports=%s',len(bundle['reports']))
        except Exception as error:  # noqa: BLE001 - never emit provider body or token-bearing exceptions
            logger.warning('Drive export failed (%s)',type(error).__name__)
            if once:
                return 1
        if once:
            return 1 if isinstance(inbox_receipts,dict) and inbox_receipts.get('status')=='unavailable' else 0
        try:
            await asyncio.wait_for(stop.wait(),timeout=60)
        except TimeoutError:
            pass
    return 0


def main(once=False):
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('google.auth').setLevel(logging.WARNING)
    return asyncio.run(run(once))
