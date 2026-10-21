"""Read-only threshold study with an ATR baseline and chronological holdout."""
from __future__ import annotations

import json
from bisect import bisect_left
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from math import isfinite

from sqlalchemy import text

from research_os.core.config import get_settings
from research_os.database.session import SessionLocal
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
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


def select_training_threshold(reports):
    eligible = [(threshold, report) for threshold, report in reports.items()
                if report['resolved_with_known_return'] >= 20
                and not report['statuses'].get('ambiguous')
                and report['mean_net_return_pct'] is not None
                and report['mean_net_return_pct'] > 0]
    return max(eligible, key=lambda item: item[1]['mean_net_return_pct'])[0] if eligible else None


def holdout_reasons(report):
    if report is None:
        return ['no_profitable_training_candidate']
    reasons = []
    if report['resolved_with_known_return'] < 20:
        reasons.append('insufficient_holdout_samples')
    if report['statuses'].get('ambiguous'):
        reasons.append('ambiguous_holdout_outcomes')
    if report['mean_net_return_pct'] is None or report['mean_net_return_pct'] <= 0:
        reasons.append('nonpositive_holdout_mean_net_return')
    return reasons


def net_target_return(direction, price, atr, fee_bps=5.5, slippage_bps=2.0):
    long = direction == 'long'
    entry = price * (1 + slippage_bps/10000 if long else 1 - slippage_bps/10000)
    target = price + 1.5*atr if long else price - 1.5*atr
    if entry <= 0 or target <= 0:
        return None
    exit_price = target * (1 - slippage_bps/10000 if long else 1 + slippage_bps/10000)
    return ((exit_price-entry)/entry if long else (entry-exit_price)/entry) - 2*fee_bps/10000


def dominant_direction_counterfactual(analysis: AnalysisResult) -> AnalysisResult:
    """Resolve a conflict to the larger evidence sum, but keep exact ties abstaining.

    Research-only counterfactual. It does not change live analysis or signal policy.
    """
    if analysis.direction is not EvidenceDirection.CONFLICTING:
        return analysis
    if analysis.bullish_score == analysis.bearish_score:
        return analysis
    direction = (
        EvidenceDirection.BULLISH
        if analysis.bullish_score > analysis.bearish_score
        else EvidenceDirection.BEARISH
    )
    return replace(
        analysis,
        direction=direction,
        reason="counterfactual dominant evidence; conflict resolved for research",
    )


def _threshold_reports(data):
    reports = {}
    for threshold in (.4, .5, .6, .7):
        selected = [(status, net, target_net) for score, status, net, target_net in data
                    if score >= threshold]
        known = [net for _, net, _ in selected if net is not None]
        winners = [net for status, net, _ in selected if status == "win" and net is not None]
        reports[str(threshold)] = {
            'candidates': len(selected),
            'statuses': dict(Counter(status for status, _, _ in selected)),
            'net_positive': sum(net > 0 for net in known),
            'tp_wins_with_nonpositive_net_return': sum(net <= 0 for net in winners),
            'mean_net_return_of_tp_wins_pct': 100*sum(winners)/len(winners) if winners else None,
            'candidates_with_nonpositive_net_tp_target': sum(
                target_net is not None and target_net <= 0
                for _, _, target_net in selected
            ),
            'mean_net_return_pct': 100*sum(known)/len(known) if known else None,
            'resolved_with_known_return': len(known),
        }
    return reports


def study(rows, candles, horizon=30, *, fee_bps=5.5, slippage_bps=2.0, cohort_horizon=None):
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if any(not isfinite(value) or value < 0 for value in (fee_bps, slippage_bps)):
        raise ValueError("cost assumptions must be finite and non-negative")
    eligibility_horizon = horizon if cohort_horizon is None else cohort_horizon
    if eligibility_horizon < horizon:
        raise ValueError("cohort horizon must cover the evaluated horizon")
    costs = {
        'fee_bps_per_side': fee_bps,
        'slippage_bps_per_side': slippage_bps,
        'round_trip_bps': 2 * (fee_bps + slippage_bps),
        'zero_cost_assumption': fee_bps == 0 and slippage_bps == 0,
        'scope': 'Simulation assumptions; not verified account tariffs or actual fills',
    }
    if len(rows) < 2 or not candles:
        return {'error': 'Need at least two saved states and confirmed candles',
                'execution_costs': costs}
    rows = sorted(rows, key=lambda row: row['decision_time'])
    candles = sorted(candles, key=lambda bar: bar['event_time'])
    candle_times = [bar['event_time'] for bar in candles]
    split = rows[0]['decision_time'] + (rows[-1]['decision_time']-rows[0]['decision_time'])/2
    end = max(bar['point_in_time_available_at'] for bar in candles)
    samples = {
        'current_abstain_on_conflict': {'train': [], 'holdout': []},
        'dominant_direction_counterfactual': {'train': [], 'holdout': []},
    }
    excluded = Counter()
    counterfactual_excluded = Counter()
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
        counterfactual = dominant_direction_counterfactual(analysis)
        current_directional = analysis.direction in (
            EvidenceDirection.BULLISH, EvidenceDirection.BEARISH
        )
        counterfactual_directional = counterfactual.direction in (
            EvidenceDirection.BULLISH, EvidenceDirection.BEARISH
        )
        if not current_directional:
            excluded['no_direction_or_conflict'] += 1
        if not counterfactual_directional:
            counterfactual_excluded['no_direction_or_conflict'] += 1
        if not current_directional and not counterfactual_directional:
            continue
        atr = state.values.get('atr_14')
        if not state.availability.get('atr_14') or atr is None or atr <= 0:
            if current_directional:
                excluded['missing_atr'] += 1
            if counterfactual_directional:
                counterfactual_excluded['missing_atr'] += 1
            continue
        offset = bisect_left(candle_times, decision)
        future = candles[offset:offset+eligibility_horizon]
        segment = 'train' if decision < split else 'holdout'
        boundary = split if segment == 'train' else end
        if len(future) != eligibility_horizon or future[-1]['point_in_time_available_at'] > boundary:
            if current_directional:
                excluded['immature_or_crosses_split'] += 1
            if counterfactual_directional:
                counterfactual_excluded['immature_or_crosses_split'] += 1
            continue
        has_gap = any(
            right['event_time']-left['event_time'] != timedelta(minutes=1)
            for left, right in pairwise(future)
        ) or future[0]['event_time']-decision > timedelta(minutes=1)
        if has_gap:
            if current_directional:
                excluded['candle_gap'] += 1
            if counterfactual_directional:
                counterfactual_excluded['candle_gap'] += 1
            continue
        future = future[:horizon]
        for policy, candidate_analysis in (
            ('current_abstain_on_conflict', analysis),
            ('dominant_direction_counterfactual', counterfactual),
        ):
            if candidate_analysis.direction not in (EvidenceDirection.BULLISH, EvidenceDirection.BEARISH):
                continue
            prediction = model.predict(candidate_analysis)
            direction = 'long' if candidate_analysis.direction is EvidenceDirection.BULLISH else 'short'
            score = prediction.long if direction == 'long' else prediction.short
            status, net = outcome(direction, future[0], future, float(atr),
                                  fee_bps=fee_bps, slippage_bps=slippage_bps)
            target_net = net_target_return(direction, float(future[0]["open"]), float(atr),
                                           fee_bps=fee_bps, slippage_bps=slippage_bps)
            samples[policy][segment].append((score, status, net, target_net))

    reports = {
        segment: _threshold_reports(samples['current_abstain_on_conflict'][segment])
        for segment in ('train', 'holdout')
    }
    conflict_comparison = {
        'policy': 'Research-only: choose the larger bullish/bearish evidence sum on conflicts; exact ties still abstain.',
        'reports': {
            segment: _threshold_reports(samples['dominant_direction_counterfactual'][segment])
            for segment in ('train', 'holdout')
        },
        'excluded': dict(counterfactual_excluded),
        'limitations': 'Uses the same states, horizon, costs, and overlapping-candidate treatment as the baseline. It is a sensitivity check, not a proposed live rule or proof of edge.',
    }
    chosen = select_training_threshold(reports['train'])
    selected_holdout = reports['holdout'].get(chosen)
    rejection_reasons = holdout_reasons(selected_holdout)
    return {'states': len(rows), 'split_utc': split.isoformat(), 'excluded': dict(excluded),
            'reports': reports, 'conflict_policy_comparison': conflict_comparison,
            'training_selected_threshold': chosen,
            'holdout_for_selected_threshold': selected_holdout,
            'research_gate_passed': not rejection_reasons,
            'rejection_reasons': rejection_reasons,
            'execution_costs': costs,
            'selection_policy': 'Training mean net return must be positive, with >=20 known returns and no ambiguous outcomes. Freeze that choice before checking holdout with the same gates. Passing is exploratory, not validation of a live strategy or calibrated model.',
            'assumptions': f'Current model rescoring; ATR stop 1x and TP1 1.5x; market entry next candle open; {horizon} candle horizon; fee {fee_bps:g} bps and slippage {slippage_bps:g} bps per side. Overlapping candidates are not deduplicated; no portfolio simulation or live liquidity/latency guard. Ambiguous outcomes excluded from means. No runtime settings changed.'}


def study_cost_comparison(rows, candles, horizon=30, *, configured_fee_bps,
                          configured_slippage_bps):
    """Keep the fixed research reference and compare current configured costs.

    Only costs vary: both runs use the same candidate selection and market-entry
    baseline. This is not a replay of emitted live signals or their saved costs.
    """
    reference = study(rows, candles, horizon)
    matches = configured_fee_bps == 5.5 and configured_slippage_bps == 2.0
    configured = reference if matches else study(
        rows, candles, horizon, fee_bps=configured_fee_bps,
        slippage_bps=configured_slippage_bps,
    )
    return {**reference, 'configured_cost_comparison': {
        'matches_reference': matches,
        'scope': 'Current configured costs on the same research baseline; not historical live execution',
        'warning': ('Zero-cost results are optimistic assumptions, not evidence of profitability after real costs'
                    if configured_fee_bps == 0 and configured_slippage_bps == 0 else None),
        'report': configured,
    }}


def study_paired_horizons(rows, candles, horizons=(15, 30, 60, 120, 240), *,
                          fee_bps=5.5, slippage_bps=2.0):
    """Compare fixed exits on a common mature cohort, including split purging."""
    horizons = tuple(horizons)
    if not horizons or any(type(h) is not int or h < 1 for h in horizons):
        raise ValueError("horizons must be positive integers")
    maximum = max(horizons)
    reports = {}
    for horizon in horizons:
        reports[str(horizon)] = {
            name: study(rows, candles, horizon, fee_bps=fee, slippage_bps=slip,
                        cohort_horizon=maximum)
            for name, fee, slip in (
                ('zero_cost', 0.0, 0.0), ('configured_cost', fee_bps, slippage_bps)
            )
        }
    return {
        'cohort_horizon_minutes': maximum,
        'reports_by_horizon': reports,
        'limitations': 'Exploratory sensitivity study; horizons are not selected using holdout. '
                        'Zero costs are optimistic. Overlapping samples are not independent. '
                        'Stops and targets remain fixed; later recovery cannot undo an exit. '
                        'All horizons require a complete maximum-horizon window and identical split purge.',
    }


def main():
    as_of = datetime.now(UTC)
    settings = get_settings()
    with SessionLocal() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        rows = session.execute(text("""SELECT symbol,timestamp,decision_time,point_in_time_available_at,
            vector,data_quality FROM world.market_state_vectors WHERE symbol='BTCUSDT'
            AND decision_time>=:since AND decision_time<=:now
            ORDER BY decision_time DESC LIMIT 10000"""), {'since':as_of-timedelta(days=7),'now':as_of}).mappings().all()
        if not rows:
            print(json.dumps({'error': 'No saved BTCUSDT states'}))
            return
        candles = session.execute(text("""SELECT event_time,point_in_time_available_at,open,high,low,close
            FROM market.candles WHERE symbol='BTCUSDT' AND interval='1' AND event_time>=:start
            AND event_time<=:now AND point_in_time_available_at<=:now
            ORDER BY event_time LIMIT 10081"""), {'start': min(row['decision_time'] for row in rows),'now':as_of}).mappings().all()
        result = study_cost_comparison(rows, candles,
                                      configured_fee_bps=settings.execution_fee_bps,
                                      configured_slippage_bps=settings.execution_slippage_bps)
        result['paired_horizon_comparison'] = study_paired_horizons(
            rows, candles, fee_bps=settings.execution_fee_bps,
            slippage_bps=settings.execution_slippage_bps)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
