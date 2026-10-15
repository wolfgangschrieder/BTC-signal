from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from research_os.auditor.context import project_evidence
from research_os.features.timeframes import Timeframe
from research_os.pipeline.history import history_diagnostic
from research_os.research.observation_report import build_report
from research_os.research.threshold_check import study_cost_comparison


def collect_snapshot(session, end, kind, settings):
    hours, limit = (24, 1440) if kind == 'daily' else ((1, 120) if kind == 'monitor' else (4, 240))
    report = build_report(session, now=end, hours=hours, limit=limit,
                          threshold=settings.signal_min_probability,
                          calibrated_models_configured=bool(settings.calibration_model_ids.strip()))
    sample = report['state_sample']
    cohort = report['emitted_forecast_cohort']
    evidence = {
        'window.start_utc': report['since_utc'], 'window.end_utc': end.isoformat(),
        'window.hours': hours,
        'system.supported_timeframes': [str(item) for item in Timeframe],
        'system.live_history_minutes': settings.live_history_minutes,
        'system.costs_apply_to': 'EV proxy and simulated net returns, not directional raw score',
        'system.feature_absence_interpretation': 'May be insufficient closed bars/history; does not prove source failure', 'sample.states': sample['states'],
        'sample.truncated': report['state_sample_may_be_truncated'],
        'sample.last_decision_utc': sample['last_decision'],
        'sample.raw_score_max': sample['directional_score']['max'],
        'sample.raw_score_p90': sample['directional_score']['p90'],
        'sample.direction_candidates': sample['direction_candidates_above_threshold'],
        'settings.threshold': settings.signal_min_probability,
        'settings.fee_bps_assumed': settings.execution_fee_bps,
        'settings.slippage_bps_assumed': settings.execution_slippage_bps,
        'settings.calibrated_models_configured': bool(settings.calibration_model_ids.strip()),
        'cohort.completed': cohort['completed'],
        'cohort.tp1_confirmation_fraction': cohort['confirmed_tp1_fraction_among_completed'],
    }
    evidence.update(project_evidence())
    for direction in ('bullish','bearish','conflicting','neutral'):
        evidence[f'sample.direction.{direction}'] = sample['analysis_directions'].get(direction, 0)
    for status in ('pending','win','loss','expired','ambiguous'):
        evidence[f'cohort.status.{status}'] = cohort['counts'].get(status, 0)
    for name in ('return_1','return_5','atr_14','tf_1h_return_1','tf_4h_return_1','tf_1d_return_1'):
        evidence[f'sample.feature_available.{name}'] = sample['available_feature_counts'].get(name, 0)
    freshness = session.execute(text('''SELECT event_type,max(ingestion_time) AS latest
        FROM raw.events WHERE source='bybit' AND ingestion_time>=:lower AND ingestion_time<=:end
        GROUP BY event_type'''), {'lower':end-timedelta(minutes=15),'end':end}).mappings().all()
    latest = {row['event_type']:row['latest'] for row in freshness}
    for event in ('candle','trade','ticker','orderbook_update'):
        evidence[f'data.{event}_age_seconds'] = (end-latest[event]).total_seconds() if event in latest else None
    delivery = session.execute(text('''SELECT count(*) AS pending,max(attempts) AS max_attempts
        FROM notification_outbox WHERE sent_at IS NULL''')).mappings().one()
    evidence['signals.telegram_pending'] = int(delivery['pending'])
    evidence['signals.telegram_max_attempts'] = delivery['max_attempts']
    evidence['storage.database_bytes'] = session.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    history = session.execute(text("""SELECT count(*) AS n,min(event_time) AS first,max(event_time) AS last
        FROM market.candles WHERE symbol='BTCUSDT' AND interval='1'
        AND event_time>=:lower AND event_time<=:end AND point_in_time_available_at<=:end"""),
        {'lower':end-timedelta(minutes=settings.live_history_minutes),'end':end}).mappings().one()
    evidence['history.minute_bars'] = int(history['n'])
    evidence['history.first_minute_utc'] = history['first'].isoformat() if history['first'] else None
    evidence['history.last_minute_utc'] = history['last'].isoformat() if history['last'] else None
    evidence['history.limitations'] = 'Stored PIT-available minute rows; not proof of contiguous bars or application in-memory history'
    evidence['history.restoration'] = history_diagnostic(
        session, 'BTCUSDT', end.replace(second=0,microsecond=0), end, min(settings.live_history_minutes,10080))
    memory = session.execute(text("""SELECT decision_time,data_quality
        FROM world.market_state_vectors WHERE symbol='BTCUSDT' AND decision_time<=:end
          AND decision_time>=:lower ORDER BY decision_time DESC LIMIT 1"""),
        {'end':end,'lower':end-timedelta(minutes=10)}).mappings().first()
    evidence['history.latest_recorded_memory'] = ({
        'decision_time':memory['decision_time'].isoformat(),
        **{key:memory['data_quality'].get(key) for key in (
            'price_history_minutes','price_history_first_utc','price_history_last_utc')}
    } if memory else None)
    # The daily study uses this baseline's own fixed costs and market-entry assumptions.
    if kind == 'daily':
        rows = session.execute(text('''SELECT symbol,timestamp,decision_time,point_in_time_available_at,
            vector,data_quality FROM world.market_state_vectors
            WHERE symbol='BTCUSDT' AND decision_time>=:start AND decision_time<=:end
            ORDER BY decision_time LIMIT 1441'''), {'start':end-timedelta(days=1),'end':end}).mappings().all()
        bars = session.execute(text('''SELECT event_time,point_in_time_available_at,open,high,low,close
            FROM market.candles WHERE symbol='BTCUSDT' AND interval='1'
            AND event_time>=:start AND event_time<=:end AND point_in_time_available_at<=:end
            ORDER BY event_time LIMIT 1441'''), {'start':end-timedelta(days=1),'end':end}).mappings().all()
        result = study_cost_comparison(
            rows[:1440], bars, configured_fee_bps=settings.execution_fee_bps,
            configured_slippage_bps=settings.execution_slippage_bps,
        )
        comparison = result['configured_cost_comparison']
        configured = comparison['report']
        evidence['baseline.execution_costs'] = result.get('execution_costs')
        evidence['configured_baseline.execution_costs'] = configured.get('execution_costs')
        evidence['configured_baseline.matches_reference'] = comparison['matches_reference']
        evidence['configured_baseline.warning'] = comparison['warning']
        evidence['configured_baseline.research_gate_passed'] = configured.get('research_gate_passed', False)
        evidence['baseline.states_truncated'] = len(rows)>1440
        evidence['baseline.research_gate_passed'] = result.get('research_gate_passed',False)
        evidence['baseline.selected_threshold'] = result.get('training_selected_threshold')
        for threshold in ('0.4','0.5','0.6','0.7'):
            record = result.get('reports',{}).get('holdout',{}).get(threshold,{})
            evidence[f'baseline.holdout.{threshold}.candidates'] = record.get('candidates',0)
            evidence[f'baseline.holdout.{threshold}.mean_net_return_pct'] = record.get('mean_net_return_pct')
            configured_record = configured.get('reports', {}).get('holdout', {}).get(threshold, {})
            evidence[f'configured_baseline.holdout.{threshold}.mean_net_return_pct'] = configured_record.get('mean_net_return_pct')
    return {'evidence':evidence, 'limitations': report['limitations'] +
            ' Reports every four hours; tick context is four hours, capped at 240 states; monitoring is 5 minutes; daily context is 24 hours capped at 1440 states. '
            'Telegram backlog and database size are current reads, not backdated daily measurements. '
            'The daily baseline has market entry, 30-minute horizon, ATR levels and fee/slippage '
            '5.5/2 bps per side, not live midpoint/60-minute execution. '
            'configured_baseline changes only costs to current settings on the same research candidates; '
            'zero costs are optimistic assumptions, not verified tariffs or actual profit. '
            'No repository code audit is performed.'}
