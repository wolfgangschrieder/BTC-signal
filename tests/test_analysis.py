from datetime import UTC, datetime

from research_os.features.engine import FeatureEngine
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.models import EvidenceDirection
from research_os.market.state_builder import MarketStateBuilder


def state(closes):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    f = FeatureEngine().build("BTCUSDT", t, closes)
    return MarketStateBuilder().build("BTCUSDT", t, t, t, f, {})


def test_analysis_is_directional_but_not_probability():
    r = MarketAnalyzer().analyze(state([100, 101, 102, 103, 104, 105]))
    assert r.direction is EvidenceDirection.BULLISH
    assert r.bullish_score > r.bearish_score
    assert not hasattr(r, "probability")


def test_conflicting_short_and_long_horizons_are_visible():
    r = MarketAnalyzer().analyze(state([100, 110, 100, 110, 94.1747572815534, 97]))
    assert r.direction is EvidenceDirection.CONFLICTING
    assert r.conflicts >= 1
    assert len(r.evidence) >= 2


def test_orderbook_imbalance_contributes_directional_evidence():
    from research_os.market.state_vector import MarketStateVector

    state = MarketStateVector.build(
        "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
        {"return_1": 0.0, "return_5": 0.0, "realized_vol": 0.005, "orderbook_imbalance": 0.6},
        {"return_1": True, "return_5": True, "realized_vol": True, "orderbook_imbalance": True},
        {},
    )
    result = MarketAnalyzer().analyze(state)
    evidence = [e for e in result.evidence if e.feature == "orderbook_imbalance"]
    assert evidence
    assert evidence[0].direction.value == "bullish"


def test_higher_timeframe_evidence_is_auditable():
    from research_os.market.state_vector import MarketStateVector

    t = datetime(2026, 1, 1, tzinfo=UTC)
    state = MarketStateVector.build(
        "BTCUSDT",
        t,
        t,
        t,
        {"return_1": 0.001, "return_5": 0.002, "tf_15m_return_1": 0.01, "tf_1h_return_1": -0.02},
        {"return_1": True, "return_5": True, "tf_15m_return_1": True, "tf_1h_return_1": True},
        {},
    )
    result = MarketAnalyzer().analyze(state)
    names = {e.feature for e in result.evidence}
    assert "tf_15m_return_1" in names and "tf_1h_return_1" in names
    assert result.direction is EvidenceDirection.CONFLICTING


def test_signal_uses_decision_time_and_keeps_evidence_event_time():
    from datetime import timedelta

    from research_os.intelligence.probability import ProbabilityEngine
    from research_os.market.state_vector import MarketStateVector
    from research_os.signals.engine import SignalEngine

    candle_time = datetime(2026, 1, 1, tzinfo=UTC)
    decision = candle_time + timedelta(minutes=5, milliseconds=100)
    market = MarketStateVector.build(
        "BTCUSDT",
        candle_time,
        decision,
        decision,
        {"return_1": 0.01, "return_5": 0.03},
        {"return_1": True, "return_5": True},
        {},
    )
    analysis = MarketAnalyzer().analyze(market)
    probability = ProbabilityEngine().predict(analysis)
    signal = SignalEngine(min_probability=0.1).build(analysis, probability, 100, atr=1)
    assert signal.direction.value == "long"
    assert signal.timestamp == decision
    assert probability.timestamp == decision
    assert analysis.timestamp == decision
    assert all(e.timestamp == candle_time for e in analysis.evidence)
