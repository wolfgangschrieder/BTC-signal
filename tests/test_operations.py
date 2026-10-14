from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from research_os.auditor.drive_export import encode_bundle
from research_os.auditor.operations import operational_status, safe_error


def test_safe_historical_diagnostics_do_not_export_arbitrary_database_text():
    assert safe_error('ValidationError')=='ValidationError'
    assert safe_error('ConnectTimeout')=='ConnectTimeout'
    assert safe_error('ValidationError task_results.0.status:literal_error').endswith('literal_error')
    assert safe_error('ValidationError sk-private-string:missing')=='ValidationError'
    assert safe_error('exception with private response')=='UnclassifiedError'


def test_export_recovers_safe_fields_from_historical_truncated_diagnostic():
    value = ('ValidationError findings.0.statement:string_type;'
             'findings.0.evidence_ids:list_type;findings.0.verification:string_type')[:96]
    assert safe_error(value) == (
        'ValidationError findings.0.statement:string_type;findings.0.evidence_ids:list_type')
    assert safe_error('ValidationError comment:validation_error') == (
        'ValidationError comment:validation_error')


def test_observations_include_failures_without_successful_report():
    now = datetime.now(UTC)
    session = MagicMock()
    attempts,decision,candle,database = [MagicMock() for _ in range(4)]
    attempts.mappings.return_value.all.return_value=[{'run_id':'id','kind':'periodic',
        'period_start':now,'period_end':now,'status':'failed','error_type':'ConnectTimeout','created_at':now}]
    decision.scalar_one_or_none.return_value=now
    candle.scalar_one_or_none.return_value=None
    database.scalar_one.return_value=1234
    session.execute.side_effect=[attempts,decision,candle,database]
    status = operational_status(session,now)
    assert status['analyst_attempts'][0]['status']=='failed'
    assert status['latest_decision_utc']==now.isoformat()
    assert status['latest_stored_minute_open_utc'] is None
    assert status['database_bytes']==1234
    sql = '\n'.join(str(call.args[0]) for call in session.execute.call_args_list)
    assert 'LIMIT 12' in sql and 'LIMIT 1' in sql and 'UPDATE' not in sql


def test_heartbeat_changes_digest_only_at_five_minute_boundary():
    now = datetime(2026,10,14,0,0,tzinfo=UTC)
    data = {'exported_at_utc':now.isoformat(),'reports':[],'tasks':[],
            'operations':{'observed_at_utc':now.isoformat()}}
    first = encode_bundle(data)[2]
    data['operations']['observed_at_utc']=(now+timedelta(seconds=60)).isoformat()
    assert encode_bundle(data)[2]==first
    data['operations']['observed_at_utc']=(now+timedelta(minutes=5)).isoformat()
    assert encode_bundle(data)[2]!=first
    assert 'СОСТОЯНИЕ СИСТЕМЫ' in encode_bundle(data)[1].decode()
