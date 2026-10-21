from dataclasses import replace
import pytest
from research_os.signals.engine import SignalEngine
from research_os.signals.models import SignalDirection
from research_os.signals.execution import evaluate_candle
from research_os.intelligence.models import EvidenceDirection
from research_os.research.replay import ReplayEngine
from test_audit_regressions import candidate

@pytest.mark.parametrize("direction", ["long", "short"])
def test_ev_matches_simulated_target_and_stop_after_costs(direction):
    analysis, probability = candidate()
    if direction == "short":
        analysis = replace(analysis, direction=EvidenceDirection.BEARISH)
        probability = replace(probability, long=.1, short=.8)
    signal = SignalEngine(fee_bps=5.5, slippage_bps=2).build(analysis, probability, 100, 2)
    assert signal.direction.value == direction
    levels = signal.levels
    target = evaluate_candle(direction, entry_price=100, stop_loss=levels.stop_loss,
        take_profit=levels.tp1, high=max(100, levels.tp1), low=min(100, levels.tp1),
        fee_bps=5.5, slippage_bps=2)
    stop = evaluate_candle(direction, entry_price=100, stop_loss=levels.stop_loss,
        take_profit=levels.tp1, high=max(100, levels.stop_loss), low=min(100, levels.stop_loss),
        fee_bps=5.5, slippage_bps=2)
    assert signal.expected_value == pytest.approx((.8*target.realized_return+.2*stop.realized_return)/.02)

def test_small_target_is_rejected_even_with_high_research_score():
    analysis, probability = candidate()
    signal = SignalEngine(fee_bps=5.5, slippage_bps=2).build(analysis, probability, 84000, 16)
    assert signal.direction is SignalDirection.NONE
    assert "costs" in signal.rationale[0]

@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_costs_are_rejected(value):
    with pytest.raises(ValueError):
        SignalEngine(fee_bps=value)
    with pytest.raises(ValueError):
        SignalEngine(slippage_bps=value)

def test_replay_signal_selection_uses_same_costs_as_outcomes():
    replay = ReplayEngine(fee_bps=5.5, slippage_bps=2)
    assert replay.signal_engine.fee_bps == replay.fee_bps == 5.5
    assert replay.signal_engine.slippage_bps == replay.slippage_bps == 2

@pytest.mark.parametrize("direction", ["long", "short"])
def test_default_settings_reject_last_long_sized_target(monkeypatch, direction):
    from research_os.core.config import Settings
    monkeypatch.delenv("EXECUTION_FEE_BPS", raising=False)
    monkeypatch.delenv("EXECUTION_SLIPPAGE_BPS", raising=False)
    settings = Settings(_env_file=None)
    assert (settings.execution_fee_bps, settings.execution_slippage_bps) == (5.5, 2)
    analysis, probability = candidate()
    if direction == "short":
        analysis = replace(analysis, direction=EvidenceDirection.BEARISH)
        probability = replace(probability, long=.1, short=.8)
    engine = SignalEngine(fee_bps=settings.execution_fee_bps,
                          slippage_bps=settings.execution_slippage_bps)
    signal = engine.build(analysis, probability, 82904.80, 26.95)
    assert signal.direction is SignalDirection.NONE
    assert "costs" in signal.rationale[0]


def test_explicit_zero_cost_scenario_remains_available(monkeypatch):
    from research_os.core.config import Settings
    monkeypatch.setenv("EXECUTION_FEE_BPS", "0")
    monkeypatch.setenv("EXECUTION_SLIPPAGE_BPS", "0")
    settings = Settings(_env_file=None)
    assert settings.execution_fee_bps == settings.execution_slippage_bps == 0
