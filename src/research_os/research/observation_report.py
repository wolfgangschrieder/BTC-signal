"""Bounded read-only observation diagnostics; no historical guard replay claims."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from research_os.research.signal_diagnostics import summarize


def outcome_counts(counts):
    wins, losses = counts.get('win', 0), counts.get('loss', 0)
    completed = sum(counts.get(status, 0) for status in ('win', 'loss', 'expired', 'ambiguous'))
    return {
        'counts': counts, 'completed': completed,
        'win_fraction_among_win_loss': wins / (wins + losses) if wins + losses else None,
        'confirmed_tp1_fraction_among_completed': wins / completed if completed else None,
        'target': 'Simulator-confirmed TP1; expired and ambiguous are non-success for this target',
    }


def build_report(session, *, symbol='BTCUSDT', hours=24, limit=1000, threshold=.70,
                 now=None, calibrated_models_configured=False):
    if not 1 <= hours <= 168 or not 1 <= limit <= 5000:
        raise ValueError('hours must be 1..168 and limit 1..5000')
    if not 0 <= threshold <= 1:
        raise ValueError('threshold must be 0..1')
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    params = {'symbol': symbol, 'since': since, 'now': now, 'limit': limit}
    session.execute(text("SET TRANSACTION READ ONLY"))
    session.execute(text("SET LOCAL statement_timeout = '5s'"))
    rows = session.execute(text('''
        SELECT symbol,timestamp,decision_time,point_in_time_available_at,
               vector_version,feature_version,vector,data_quality
        FROM world.market_state_vectors
        WHERE symbol=:symbol AND timestamp>=:since AND timestamp<=:now
          AND decision_time>=:since AND decision_time<=:now
          AND point_in_time_available_at<=decision_time
        ORDER BY timestamp DESC, decision_time DESC, state_id DESC LIMIT :limit
    '''), params).mappings().all()
    diagnostics = summarize(rows, threshold=threshold)
    counts = {row['status']: int(row['n']) for row in session.execute(text('''
        SELECT status, count(*) AS n FROM signal_outcomes
        WHERE symbol=:symbol AND signal_time>=:since AND signal_time<=:now
        GROUP BY status
    '''), params).mappings()}
    cohorts = session.execute(text('''
        SELECT direction, execution_policy, (probability_model_id IS NOT NULL) AS calibrated,
               status, count(*) AS n
        FROM signal_outcomes
        WHERE symbol=:symbol AND signal_time>=:since AND signal_time<=:now
        GROUP BY direction, execution_policy, (probability_model_id IS NOT NULL), status
        ORDER BY n DESC, direction, execution_policy, calibrated, status LIMIT 51
    '''), params).mappings().all()
    return {
        'symbol': symbol, 'since_utc': since.isoformat(), 'as_of_utc': now.isoformat(),
        'sample_limit': limit, 'state_sample_may_be_truncated': len(rows) == limit,
        'state_sample': diagnostics,
        'configured_calibration_models': calibrated_models_configured,
        'emitted_forecast_cohort': outcome_counts(counts),
        'cohort_status_counts': [dict(row) for row in cohorts[:50]],
        'cohort_status_counts_truncated': len(cohorts) > 50,
        'limitations': (
            'State scores use the current heuristic engine, not pinned calibration models or '
            'historical live decisions. No cooldown, orderbook, latency or persistence guard replay. '
            'Forecast cohort is selected by emission time; statuses are current as of this read. '
            'Cohorts separate direction/execution policy/calibration presence, not individual model IDs. '
            'These are hypothetical OHLC outcomes, not executed trades or verified profitability. '
            'Absent signals do not establish a delivery failure. No data is written.'
        ),
    }
