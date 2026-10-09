from datetime import UTC, datetime, timedelta

import pytest

from research_os.research.threshold_check import outcome, study


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


def test_split_rejects_cross_boundary_and_incomplete_horizons():
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
        candles.append(dict(bar(), event_time=time, point_in_time_available_at=time+timedelta(minutes=1)))
    result = study(rows, candles, horizon=3)
    assert result['excluded']['immature_or_crosses_split'] == 6
    assert result['reports']['train']['0.4']['candidates'] == 1
    assert result['reports']['holdout']['0.4']['candidates'] == 3
    assert result['training_selected_threshold'] is None
    assert result['reports']['train']['0.7']['candidates'] == 0
