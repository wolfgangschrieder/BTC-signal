"""Read-only threshold study with an ATR baseline and chronological holdout."""
from __future__ import annotations

import json
from bisect import bisect_left
from collections import Counter
from datetime import timedelta
from itertools import pairwise

from sqlalchemy import text

from research_os.database.session import SessionLocal
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_vector import MarketStateVector
from research_os.signals.execution import ExecutionStatus, evaluate_candle


def outcome(direction, entry_bar, bars, atr, fee_bps=5.5, slippage_bps=2.0):
    """Market entry at next eligible candle open; fees/slippage charged each side."""
    price = float(entry_bar['open'])
    long = direction == 'long'
    entry = price * (1 + slippage_bps/10000 if long else 1 - slippage_bps/10000)
    stop = price - atr if long else price + atr
    target = price + 1.5*atr if long else price - 1.5*atr
    if stop <= 0 or target <= 0:
        return 'invalid_levels', None
    for bar in bars:
        # Stop gaps execute at the worse opening price rather than at the stop.
        opening = float(bar['open'])
        effective_stop = min(stop, opening) if long else max(stop, opening)
        if (long and opening <= stop) or (not long and opening >= stop):
            gap = evaluate_candle(direction, entry_price=entry, stop_loss=effective_stop,
                                  take_profit=target, high=opening, low=opening,
                                  fee_bps=fee_bps, slippage_bps=slippage_bps, entry_filled=True)
            return gap.status.value, gap.realized_return
        result = evaluate_candle(direction, entry_price=entry, stop_loss=effective_stop,
                                 take_profit=target, high=float(bar['high']), low=float(bar['low']),
                                 fee_bps=fee_bps, slippage_bps=slippage_bps, entry_filled=True)
        if result.status in (ExecutionStatus.WIN, ExecutionStatus.LOSS, ExecutionStatus.AMBIGUOUS):
            return result.status.value, result.realized_return
    exit_price = float(bars[-1]['close']) * (1-slippage_bps/10000 if long else 1+slippage_bps/10000)
    net = ((exit_price-entry)/entry if long else (entry-exit_price)/entry) - 2*fee_bps/10000
    return 'timeout', net


def study(rows, candles, horizon=30):
    if len(rows) < 2 or not candles:
        return {'error': 'Need at least two saved states and confirmed candles'}
    rows = sorted(rows, key=lambda row: row['decision_time'])
    candles = sorted(candles, key=lambda bar: bar['event_time'])
    candle_times = [bar['event_time'] for bar in candles]
    split = rows[0]['decision_time'] + (rows[-1]['decision_time']-rows[0]['decision_time'])/2
    end = max(bar['point_in_time_available_at'] for bar in candles)
    samples = {'train': [], 'holdout': []}
    excluded = Counter()
    analyzer, model = MarketAnalyzer(), ProbabilityEngine()
    for row in rows:
        decision = row['decision_time']
        if row['point_in_time_available_at'] > decision:
            excluded['state_unavailable_at_decision'] += 1
            continue
        vector = row['vector']
        state = MarketStateVector.build(row['symbol'], row['timestamp'], decision,
                                       row['point_in_time_available_at'], vector['values'],
                                       vector['availability'], row['data_quality'])
        analysis = analyzer.analyze(state)
        prediction = model.predict(analysis)
        if analysis.direction not in (EvidenceDirection.BULLISH, EvidenceDirection.BEARISH):
            excluded['no_direction_or_conflict'] += 1
            continue
        atr = state.values.get('atr_14')
        if not state.availability.get('atr_14') or atr is None or atr <= 0:
            excluded['missing_atr'] += 1
            continue
        offset = bisect_left(candle_times, decision)
        future = candles[offset:offset+horizon]
        segment = 'train' if decision < split else 'holdout'
        boundary = split if segment == 'train' else end
        if len(future) != horizon or future[-1]['point_in_time_available_at'] > boundary:
            excluded['immature_or_crosses_split'] += 1
            continue
        if any(right['event_time']-left['event_time'] != timedelta(minutes=1)
               for left, right in pairwise(future)) or future[0]['event_time']-decision > timedelta(minutes=1):
            excluded['candle_gap'] += 1
            continue
        direction = 'long' if analysis.direction is EvidenceDirection.BULLISH else 'short'
        score = prediction.long if direction == 'long' else prediction.short
        status, net = outcome(direction, future[0], future, float(atr))
        samples[segment].append((score, status, net))
    reports = {}
    for segment, data in samples.items():
        reports[segment] = {}
        for threshold in (.4, .5, .6, .7):
            selected = [(status, net) for score, status, net in data if score >= threshold]
            known = [net for _, net in selected if net is not None]
            reports[segment][str(threshold)] = {
                'candidates': len(selected), 'statuses': dict(Counter(status for status, _ in selected)),
                'net_positive': sum(net > 0 for net in known),
                'mean_net_return_pct': 100*sum(known)/len(known) if known else None,
                'resolved_with_known_return': len(known),
            }
    eligible = [(threshold, report) for threshold, report in reports['train'].items()
                if report['resolved_with_known_return'] >= 20 and not report['statuses'].get('ambiguous')]
    chosen = max(eligible, key=lambda item: item[1]['mean_net_return_pct'])[0] if eligible else None
    return {'states': len(rows), 'split_utc': split.isoformat(), 'excluded': dict(excluded),
            'reports': reports, 'training_selected_threshold': chosen,
            'holdout_for_selected_threshold': reports['holdout'].get(chosen),
            'assumptions': 'Current model rescoring; ATR stop 1x and TP1 1.5x; market entry next candle open; 30 candle horizon; fee 5.5 bps and slippage 2 bps per side. Overlapping independent candidates, no portfolio simulation or live liquidity/latency guard. Ambiguous outcomes excluded from means. No runtime settings changed.'}


def main():
    with SessionLocal() as session:
        rows = session.execute(text("""SELECT symbol,timestamp,decision_time,point_in_time_available_at,
            vector,data_quality FROM world.market_state_vectors WHERE symbol='BTCUSDT'
            ORDER BY decision_time DESC LIMIT 10000""")).mappings().all()
        if not rows:
            print(json.dumps({'error': 'No saved BTCUSDT states'}))
            return
        candles = session.execute(text("""SELECT event_time,point_in_time_available_at,open,high,low,close
            FROM market.candles WHERE symbol='BTCUSDT' AND interval='1' AND event_time>=:start
            ORDER BY event_time"""), {'start': min(row['decision_time'] for row in rows)}).mappings().all()
        print(json.dumps(study(rows, candles), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
