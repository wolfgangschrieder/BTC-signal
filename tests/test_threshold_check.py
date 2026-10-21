from datetime import UTC, datetime, timedelta

import pytest

from research_os.research.threshold_check import (
    dominant_direction_counterfactual,
    outcome,
    study,
    study_cost_comparison,
)
from research_os.intelligence.models import AnalysisResult, EvidenceDirection


def bar(opening=100, high=101, low=99, close=100):
    return {'open': opening, 'high': high, 'low': low, 'close': close}


def test_costs_reduce_target_return():
    entry = bar()
    status, net = outcome('long', entry, [bar(high=104)], 2)
    assert status == 'win'
    assert net == pytest.approx((103*(1-.0002)-100*(1+.0002))/(100*(1+.0002))-.0011)


def test_both_targets_are_ambiguous():
    assert outcome('long', bar(), [bar(high=104, low=97)], 2) == ('ambiguous', None)


def test_gap_stop_executes_before_intrabar_target():
    status, net = outcome('long', bar(), [bar(opening=95, high=104, low=94)], 2)
    assert status == 'loss' and net < -.05


def test_timeout_charges_both_sides():
    status, net = outcome('short', bar(), [bar()], 2)
    assert status == 'timeout' and net < -.0011


def study_inputs():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(10):
        decision = start+timedelta(minutes=index, seconds=1)
        rows.append({'symbol': 'BTCUSDT', 'timestamp': decision-timedelta(minutes=1),
                     'decision_time': decision, 'point_in_time_available_at': decision,
                     'data_quality': {}, 'vector': {
                         'values': {'return_1': .01, 'return_5': .03, 'atr_14': 2},
                         'availability': {'return_1': True, 'return_5': True, 'atr_14': True}}})
    candles = []
    for index in range(11):
        time = start+timedelta(minutes=index)
        candles.append(dict(
            bar(),
            event_time=time,
            point_in_time_available_at=time + timedelta(minutes=1),
        ))
    return rows, candles


def test_split_rejects_cross_boundary_and_incomplete_horizons():
    rows, candles = study_inputs()
    result = study(rows, candles, horizon=3)
    assert result['excluded']['immature_or_crosses_split'] == 6
    assert result['reports']['train']['0.4']['candidates'] == 1
    assert result['reports']['holdout']['0.4']['candidates'] == 3
    assert result['training_selected_threshold'] is None
    assert result['reports']['train']['0.7']['candidates'] == 0
    assert result['conflict_policy_comparison']['reports']['train']['0.4']['candidates'] == 1


def test_cost_comparison_keeps_candidates_and_exposes_zero_cost_optimism():
    rows, candles = study_inputs()
    for row in rows:
        row['vector']['values']['atr_14'] = .01
    for candle in candles:
        candle.update(high=100.03, low=100)
    result = study_cost_comparison(rows, candles, horizon=3,
                                   configured_fee_bps=0, configured_slippage_bps=0)
    comparison = result['configured_cost_comparison']
    configured = comparison['report']
    assert not comparison['matches_reference'] and comparison['warning']
    assert result['execution_costs']['round_trip_bps'] == 15
    assert configured['execution_costs']['zero_cost_assumption']
    assert 'fee 0 bps and slippage 0 bps' in configured['assumptions']
    assert result['excluded'] == configured['excluded']
    for reports in ('reports', 'conflict_policy_comparison'):
        reference_reports = result[reports]
        configured_reports = configured[reports]
        if reports == 'conflict_policy_comparison':
            reference_reports = reference_reports['reports']
            configured_reports = configured_reports['reports']
        for segment in ('train', 'holdout'):
            charged = reference_reports[segment]['0.4']
            free = configured_reports[segment]['0.4']
            assert charged['candidates'] == free['candidates'] > 0
            assert charged['statuses'] == free['statuses']
            assert charged['mean_net_return_pct'] < 0 < free['mean_net_return_pct']
            assert charged['candidates_with_nonpositive_net_tp_target'] > 0
            assert free['candidates_with_nonpositive_net_tp_target'] == 0


def test_matching_cost_scenario_serializes_without_a_recursive_report():
    import json

    result = study_cost_comparison(*study_inputs(), horizon=3,
                                   configured_fee_bps=5.5, configured_slippage_bps=2)
    comparison = result['configured_cost_comparison']
    assert comparison['matches_reference'] and comparison['warning'] is None
    assert comparison['report']['reports'] == result['reports']
    assert json.loads(json.dumps(result))['execution_costs']['fee_bps_per_side'] == 5.5


@pytest.mark.parametrize('cost', [-1, float('nan'), float('inf')])
@pytest.mark.parametrize('field', ['fee_bps', 'slippage_bps'])
def test_invalid_cost_assumptions_are_rejected(cost, field):
    with pytest.raises(ValueError, match='finite and non-negative'):
        study([], [], **{field: cost})


def test_conflict_counterfactual_uses_dominant_evidence_and_keeps_ties_abstaining():
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    conflict = AnalysisResult(
        'BTCUSDT', timestamp, EvidenceDirection.CONFLICTING,
        (), 1.5, 0.5, 1, True, 'conflict',
    )
    tie = AnalysisResult(
        'BTCUSDT', timestamp, EvidenceDirection.CONFLICTING,
        (), 1.0, 1.0, 1, True, 'conflict',
    )

    resolved = dominant_direction_counterfactual(conflict)
    assert resolved.direction is EvidenceDirection.BULLISH
    assert resolved.bullish_score == conflict.bullish_score
    assert dominant_direction_counterfactual(tie).direction is EvidenceDirection.CONFLICTING


def threshold_report(mean, samples=30, ambiguous=0):
    return {'mean_net_return_pct':mean,'resolved_with_known_return':samples,
            'statuses':{'ambiguous':ambiguous} if ambiguous else {}}


def test_training_cannot_select_best_of_losing_thresholds():
    from research_os.research.threshold_check import select_training_threshold
    assert select_training_threshold({'0.4':threshold_report(-.15),
                                      '0.5':threshold_report(-.10)}) is None
    assert select_training_threshold({'0.5':threshold_report(0)}) is None
    assert select_training_threshold({'0.4':threshold_report(.1),
                                      '0.5':threshold_report(.2)}) == '0.5'


def test_profitability_needs_sample_and_unambiguous_holdout():
    from research_os.research.threshold_check import holdout_reasons, select_training_threshold
    assert select_training_threshold({'0.5':threshold_report(1, samples=19)}) is None
    assert select_training_threshold({'0.5':threshold_report(1, ambiguous=1)}) is None
    assert holdout_reasons(None) == ['no_profitable_training_candidate']
    assert 'nonpositive_holdout_mean_net_return' in holdout_reasons(threshold_report(-.1))
    assert 'insufficient_holdout_samples' in holdout_reasons(threshold_report(.1, samples=19))
    assert 'ambiguous_holdout_outcomes' in holdout_reasons(threshold_report(.1, ambiguous=1))
    assert not holdout_reasons(threshold_report(.1))


@pytest.mark.parametrize('direction', ['long', 'short'])
def test_target_touch_can_lose_money_after_costs(direction):
    from research_os.research.threshold_check import net_target_return
    price, atr = 100, .01
    target = price + 1.5*atr if direction == 'long' else price - 1.5*atr
    status, net = outcome(direction, bar(), [bar(high=target, low=target)], atr)
    assert status == 'win' and net < 0
    assert net_target_return(direction, price, atr) == pytest.approx(net)

@pytest.mark.parametrize('direction', ['long', 'short'])
@pytest.mark.parametrize('horizon', [15, 30, 60, 120, 240])
def test_later_recovery_cannot_reverse_an_executed_stop(direction, horizon):
    # A longer horizon changes expiry only; it must not erase earlier exits.
    if direction == 'long':
        stopped = bar(opening=100, high=100.5, low=97.5, close=98)
        recovery = bar(opening=100, high=104, low=99, close=103)
    else:
        stopped = bar(opening=100, high=102.5, low=99.5, close=102)
        recovery = bar(opening=100, high=101, low=96, close=97)
    status, net = outcome(direction, bar(), [stopped] + [recovery]*(horizon-1), 2)
    assert status == 'loss'
    first_exit = outcome(direction, bar(), [stopped], 2)
    assert (status, net) == first_exit
    assert net < 0
