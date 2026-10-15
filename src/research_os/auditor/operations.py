"""Read-only bounded operational facts, independent of successful LLM reports."""
import re

from sqlalchemy import text


def safe_error(value):
    if not value:
        return None
    # Historical DB text is untrusted. Diagnostics allow only known schema paths/codes.
    from research_os.auditor.diagnostics import safe_validation_diagnostic
    if value.startswith('ValidationError '):
        return safe_validation_diagnostic(value)
    if re.fullmatch(r'[A-Za-z]{1,48}(Error|Timeout)',value):
        return value
    return 'UnclassifiedError'


def operational_status(session, now):
    from research_os.auditor.deployment_status import read_deployment_status
    attempts = session.execute(text("""SELECT run_id,kind,period_start,period_end,status,
        error_type,created_at,attempt_number,tokens FROM intelligence.auditor_runs
        WHERE kind IN ('periodic','daily') ORDER BY created_at DESC LIMIT 12""")).mappings().all()
    decision = session.execute(text("""SELECT decision_time FROM world.market_state_vectors
        WHERE symbol='BTCUSDT' ORDER BY decision_time DESC LIMIT 1""")).scalar_one_or_none()
    candle = session.execute(text("""SELECT event_time FROM market.candles
        WHERE symbol='BTCUSDT' AND interval='1' AND source='bybit'
        ORDER BY event_time DESC LIMIT 1""")).scalar_one_or_none()
    database = session.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    return {'observed_at_utc':now.isoformat(),'latest_decision_utc':decision.isoformat() if decision else None,
            'latest_stored_minute_open_utc':candle.isoformat() if candle else None,
            'database_bytes':int(database),
            'deployment':read_deployment_status(),
            'analyst_attempts':[{**dict(row),'run_id':str(row['run_id']),
                'error_type':safe_error(row['error_type'])} for row in attempts],
            'limitations':'Database observations, not container health or actual fills. Candle is latest stored opening time, not proof of confirmation or contiguous history. Export freshness does not imply a new successful analyst report. Versions/disk reserve and complete server outage are not measured here.'}
