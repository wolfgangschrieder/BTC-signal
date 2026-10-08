from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from research_os.features.orderflow import OrderFlowEngine, TradeObservation
from research_os.features.timeframes import OHLCVBar, Timeframe
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.intelligence.probability import ProbabilityEngine, ProbabilityResult
from research_os.market.state_vector import MarketStateVector
from research_os.notifications.telegram import TelegramFormatter
from research_os.pipeline.live import LiveSignalService
from research_os.signals.engine import SignalEngine
from research_os.signals.execution import ExecutionStatus, evaluate_candle
from research_os.signals.guard import SignalGuard


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def candidate():
    analysis = AnalysisResult("BTCUSDT", NOW, EvidenceDirection.BULLISH, (), 3, 0, 0, True, "")
    probability = ProbabilityResult("BTCUSDT", NOW, .8, .1, .1)
    return analysis, probability


def test_cooldown_survives_changed_levels_opposite_direction_and_restoration():
    analysis, probability = candidate()
    signal = SignalEngine().build(analysis, probability, 100, 2)
    guard = SignalGuard()
    guard.mark_sent(signal)
    moved = SignalEngine().build(replace(analysis, timestamp=NOW+timedelta(minutes=1)), probability, 101, 2)
    assert not guard.allow(moved)
    guard.restore_sent("BTCUSDT", "short", NOW+timedelta(minutes=2))
    assert not guard.allow(moved)
    restarted = SignalGuard()
    restarted.restore_sent("BTCUSDT", "long", NOW)
    assert not restarted.allow(moved)
    assert restarted.allow(replace(moved, timestamp=NOW+timedelta(minutes=15)))


def test_live_configuration_reaches_both_engine_and_guard():
    service = LiveSignalService(settings=SimpleNamespace(signal_min_probability=.55, execution_fee_bps=6, execution_slippage_bps=2))
    assert service.pipeline.signal.min_probability == service.pipeline.guard.min_probability == .55
    assert service.pipeline.signal.fee_bps == 6
    assert service.pipeline.signal.slippage_bps == 2
    assert LiveSignalService(guard=SignalGuard(min_probability=.6)).pipeline.signal.min_probability == .6


def test_live_daily_return_can_become_available():
    service = LiveSignalService()
    for minute in range(3*1440):
        price = 100+minute/1000
        service.bars_1m.append(OHLCVBar(NOW+timedelta(minutes=minute), price, price+1, price-1, price, 1))
    snapshot = service.mtf.build("BTCUSDT", list(service.bars_1m), NOW+timedelta(minutes=4319), as_of=NOW+timedelta(days=3))
    daily = {f.name: f for f in snapshot.snapshots[Timeframe.D1].features}
    assert daily["return_1"].available


def test_flow_rejects_stale_and_future_trades():
    flow = OrderFlowEngine()
    old = TradeObservation(NOW-timedelta(days=1), 100, 100, "Buy")
    future = TradeObservation(NOW+timedelta(seconds=1), 100, 100, "Sell")
    assert not flow.build([old, future], NOW).available
    fresh = TradeObservation(NOW-timedelta(seconds=1), 100, 1, "Buy")
    result = flow.build([old, fresh, future], NOW, cumulative_delta_override=20, previous_price=101, previous_cumulative_delta=19)
    assert result.buy_volume == 1 and result.sell_volume == 0
    assert result.cumulative_delta == 20 and result.price_delta_divergence == 1


def test_production_blocks_heuristic_score_but_shadow_labels_it():
    analysis, probability = candidate()
    production = LiveSignalService(settings=SimpleNamespace(environment="production"))
    rejected = production.pipeline.signal.build(analysis, probability, 100, 2)
    assert rejected.direction.value == "none"
    signal = SignalEngine().build(analysis, probability, 100, 2)
    text = TelegramFormatter().format(signal).text
    assert "Research score (uncalibrated)" in text
    assert "Hypothetical EV" in text
    assert not signal.probability_is_calibrated


def test_costs_reduce_ev_in_risk_units():
    analysis, probability = candidate()
    gross = SignalEngine().build(analysis, probability, 100, 2)
    net = SignalEngine(fee_bps=10, slippage_bps=10).build(analysis, probability, 100, 2)
    assert gross.expected_value-net.expected_value == pytest.approx(.2)


@pytest.mark.parametrize("direction,stop,tp", [("long",99,101), ("short",101,99)])
def test_entry_bar_exit_is_ambiguous_only_for_new_policy(direction, stop, tp):
    args = dict(entry_price=100, stop_loss=stop, take_profit=tp, high=102, low=98, check_exit=False)
    assert evaluate_candle(direction, **args).status is ExecutionStatus.PENDING
    assert evaluate_candle(direction, **args, conservative_entry=True).status is ExecutionStatus.AMBIGUOUS


def test_minor_opposing_evidence_is_visible_without_automatic_veto():
    state = MarketStateVector.build("BTCUSDT", NOW, NOW, NOW,
        {"return_1": .01, "return_5": .03, "orderbook_imbalance": -.06},
        {"return_1": True, "return_5": True, "orderbook_imbalance": True}, {})
    result = MarketAnalyzer().analyze(state)
    assert result.direction is EvidenceDirection.BULLISH
    assert result.conflicts == 1 and result.bearish_score > 0


def test_probability_softmax_does_not_overflow():
    analysis, _ = candidate()
    result = ProbabilityEngine().predict(replace(analysis, bullish_score=10000))
    assert 0 <= result.long <= 1

