import importlib.util
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from research_os.auditor.client import DeepSeekAnalyst, prepare_prompt
from research_os.auditor.models import AnalystReport, message
from research_os.auditor.repository import AuditorRepository
from research_os.auditor.runtime import AuditorService, windows
from research_os.core.config import Settings
from research_os.database.session import SessionLocal

NOW = datetime(2026, 10, 9, 21, 2, tzinfo=UTC)


def report_data():
    return {'verdict':'insufficient_data','comment':'Недостаточно завершённых прогнозов.',
            'comment_evidence_ids':['cohort.completed'],'findings':[]}


def test_unknown_evidence_and_credentials_are_rejected():
    report = AnalystReport.model_validate(report_data())
    with pytest.raises(ValueError):
        report.validate_evidence({})
    bad = report_data()
    bad['comment'] = 'sk-'+'placeholdersecret'*3
    with pytest.raises(ValidationError):
        AnalystReport.model_validate(bad)
    bad = report_data()
    bad['findings'] = [{'kind':'hypothesis','topic':'profitability','severity':'high',
                        'statement':'Target is small','evidence_ids':['missing'],'verification':'Measure costs'}]
    with pytest.raises(ValueError):
        AnalystReport.model_validate(bad).validate_evidence({'cohort.completed':0})


def test_idle_comment_is_valid_and_telegram_is_bounded():
    report = AnalystReport.model_validate(report_data()).validate_evidence({'cohort.completed':0})
    body = message(report,'tick',NOW-timedelta(minutes=5),NOW,{'cohort.completed':0})
    assert 'cohort.completed=0' in body and 'Интерпретация' in body
    assert len(body.encode('utf-16-le'))//2 <= 3500
    assert not report.findings


def test_periods_align_to_five_minutes_and_previous_moscow_day():
    tick, daily = windows(NOW)
    assert tick == ('tick',datetime(2026,10,9,20,55,tzinfo=UTC),datetime(2026,10,9,21,tzinfo=UTC))
    assert daily == ('daily',datetime(2026,10,8,21,tzinfo=UTC),datetime(2026,10,9,21,tzinfo=UTC))


def test_input_size_and_secret_repr():
    with pytest.raises(ValueError):
        prepare_prompt({'evidence':{'huge':'x'*20000},'limitations':''},[])
    settings = Settings(deepseek_api_key='placeholder-key')
    assert 'placeholder-key' not in repr(settings)


@pytest.mark.asyncio
async def test_api_returns_validated_json_without_tools():
    def handler(request):
        assert request.url == 'https://api.deepseek.com/chat/completions'
        body = json.loads(request.content)
        assert body['response_format'] == {'type':'json_object'}
        assert 'tools' not in body
        assert 'placeholder-key' not in request.content.decode()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(report_data())}}],
                                        'usage':{'total_tokens':100}})
    client = DeepSeekAnalyst('placeholder-key','deepseek-flash',transport=httpx.MockTransport(handler))
    report, tokens = await client.analyze('{}',{'cohort.completed':0})
    assert report.verdict == 'insufficient_data' and tokens == 100


@pytest.mark.asyncio
@pytest.mark.parametrize('content,reason', [('', 'stop'),('{}','length'),('not json','stop')])
async def test_empty_truncated_or_invalid_api_output_fails(content, reason):
    transport = httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{
        'finish_reason':reason,'message':{'content':content}}]}))
    client = DeepSeekAnalyst('placeholder','deepseek-flash',transport=transport)
    with pytest.raises((ValueError,ValidationError)):
        await client.analyze('{}',{'cohort.completed':0})


@pytest.mark.asyncio
async def test_failed_analysis_keeps_budget_and_records_only_error_type(monkeypatch):
    class Analyst:
        async def analyze(self,*args):
            raise ValueError('secret-payload')
    settings = SimpleNamespace(deepseek_api_key=SecretStr(''),auditor_model='deepseek-flash',
                               auditor_max_output_tokens=2200,auditor_daily_token_budget=1000000)
    service = AuditorService(settings,analyst=Analyst())
    calls = []
    monkeypatch.setattr(service,'_exists',lambda *args:False)
    monkeypatch.setattr(service,'_snapshot',lambda *args:({'evidence':{'cohort.completed':0},'limitations':''},[]))

    def write(method,*args,**kwargs):
        calls.append((method.__name__,args,kwargs))
        return 'identity' if method.__name__=='reserve' else None

    monkeypatch.setattr(service,'_write',write)
    await service.audit('tick',NOW-timedelta(minutes=5),NOW,NOW)
    assert [name for name,_,_ in calls] == ['reserve','fail']
    assert calls[0][2]['tokens'] > settings.auditor_max_output_tokens


def test_setup_preserves_storage_telegram_and_permissions(tmp_path):
    spec = importlib.util.spec_from_file_location('auditor_setup',Path(__file__).parents[1]/'deploy/configure-auditor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path/'.env'
    path.write_text('POSTGRES_PASSWORD=existing\nTELEGRAM_BOT_TOKEN=existing\nSTORAGE_MIN_FREE_GB=5\n')
    module.save(path,'sk-'+'testplaceholder'*3)
    assert 'POSTGRES_PASSWORD=existing' in path.read_text()
    assert 'STORAGE_MIN_FREE_GB=5' in path.read_text()
    assert 'TELEGRAM_BOT_TOKEN=existing' in path.read_text()
    assert 'AUDITOR_ENABLED=true' in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode)==0o600


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_journal_reserves_budget_deduplicates_and_leases_delivery():
    now = datetime.now(UTC)
    start, end = now-timedelta(minutes=5),now
    repository = AuditorRepository()
    with SessionLocal() as session:
        try:
            arguments = dict(  # noqa: C408 - readable keyword fixture
kind='tick',start=start,end=end,snapshot={'evidence':{}},model='test',tokens=100,
                             budget_start=now-timedelta(seconds=1),budget_end=now+timedelta(days=1),daily_budget=199)
            identity = repository.reserve(session,**arguments)
            assert identity
            assert repository.reserve(session,**arguments) is None
            assert repository.reserve(session,**{**arguments,'start':start+timedelta(seconds=1)}) is None
            report = AnalystReport.model_validate(report_data())
            repository.complete(session,identity,report,'message',40)
            assert session.execute(text('SELECT tokens FROM intelligence.auditor_runs WHERE run_id=:id'),{'id':identity}).scalar_one()==40
            item = repository.claim(session)
            assert str(item['run_id'])==identity and item['attempts']==1
            assert repository.claim(session) is None
            repository.delivered(session,item)
            assert repository.claim(session) is None
            assert session.execute(text('SELECT report FROM intelligence.auditor_runs WHERE run_id=:id'),{'id':identity}).scalar_one()['comment']==report.comment
        finally:
            session.rollback()


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_snapshot_queries_real_schema_and_has_no_secrets():
    from research_os.auditor.snapshot import collect_snapshot
    settings = Settings()
    with SessionLocal() as session:
        snapshot = collect_snapshot(session,datetime.now(UTC),'tick',settings)
        assert 'cohort.completed' in snapshot['evidence']
        assert 'storage.database_bytes' in snapshot['evidence']
        assert session.execute(text('SHOW transaction_read_only')).scalar_one()=='on'
        payload, size = prepare_prompt(snapshot,[])
        assert size<=16000
        assert 'DEEPSEEK_API_KEY' not in payload and 'TELEGRAM_BOT_TOKEN' not in payload


@pytest.mark.asyncio
async def test_telegram_failure_preserves_report_for_retry(monkeypatch):
    class Telegram:
        async def send(self,*args):
            raise ValueError('credential-like-url')
    settings = SimpleNamespace(deepseek_api_key=SecretStr(''),auditor_model='deepseek-flash')
    service = AuditorService(settings,telegram=Telegram())
    calls = []

    def write(method,*args):
        calls.append(method.__name__)
        if method.__name__=='claim':
            return {'run_id':'identity','message':'report','claim_token':'token','attempts':1}

    monkeypatch.setattr(service,'_write',write)
    await service.deliver_once()
    assert calls==['claim','retry']


def test_storage_block_prevents_journal_writes():
    class Storage:
        def check(self):
            raise RuntimeError('Storage budget exceeded')
    factory = MagicMock()
    settings = SimpleNamespace(deepseek_api_key=SecretStr(''),auditor_model='deepseek-flash')
    service = AuditorService(settings,storage=Storage(),session_factory=factory)
    with pytest.raises(RuntimeError):
        service._write(service.repository.prune,NOW)
    factory.assert_not_called()
